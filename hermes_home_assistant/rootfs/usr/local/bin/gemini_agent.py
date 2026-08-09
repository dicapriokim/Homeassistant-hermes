#!/usr/bin/env python3
import warnings
warnings.filterwarnings("ignore")
import os
import json
import glob
import shutil
import logging
import requests
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from google import genai
from google.genai import types as genai_types

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load config from Home Assistant options.json
OPTIONS_PATH = "/data/options.json"
options = {}
if os.path.exists(OPTIONS_PATH):
    with open(OPTIONS_PATH, "r") as f:
        options = json.load(f)

def _read_s6_env(var_name: str) -> str:
    for base in ["/run/s6/container_environment", "/var/run/s6/container_environment"]:
        p = os.path.join(base, var_name)
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception:
                pass
    return ""

def _clean_token(tok: str | None) -> str:
    if not tok:
        return ""
    return str(tok).strip('\'" \t\r\n')

GEMINI_API_KEY = _clean_token(options.get("gemini_api_key") or os.getenv("GEMINI_API_KEY") or _read_s6_env("GEMINI_API_KEY"))
TELEGRAM_BOT_TOKEN = _clean_token(options.get("telegram_bot_token") or os.getenv("TELEGRAM_BOT_TOKEN") or _read_s6_env("TELEGRAM_BOT_TOKEN"))

AUTHORIZED_CHAT_IDS = options.get("authorized_chat_ids", [])
if not AUTHORIZED_CHAT_IDS:
    raw_env_chats = os.getenv("AUTHORIZED_CHAT_IDS", "")
    if raw_env_chats:
        try:
            parsed = json.loads(raw_env_chats)
            if isinstance(parsed, list):
                AUTHORIZED_CHAT_IDS = [int(x) for x in parsed]
            else:
                AUTHORIZED_CHAT_IDS = [int(raw_env_chats)]
        except Exception:
            clean_str = raw_env_chats.replace("[", "").replace("]", "")
            AUTHORIZED_CHAT_IDS = [int(x.strip()) for x in clean_str.split(",") if x.strip().isdigit()]

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SUPERVISOR_TOKEN = _clean_token(
    os.getenv("SUPERVISOR_TOKEN")
    or os.getenv("HASS_TOKEN")
    or os.getenv("HA_TOKEN")
    or options.get("supervisor_token")
    or options.get("hass_token")
    or _read_s6_env("SUPERVISOR_TOKEN")
    or _read_s6_env("HASS_TOKEN")
    or _read_s6_env("HA_TOKEN")
)

raw_url = _clean_token(
    os.getenv("HASS_URL")
    or os.getenv("HA_URL")
    or options.get("hass_url")
    or options.get("ha_url")
    or _read_s6_env("HASS_URL")
    or _read_s6_env("HA_URL")
)
if not raw_url or "supervisor" in raw_url:
    raw_url = "http://172.17.0.1:8123"

HA_API_URL = raw_url
if HA_API_URL.endswith("/"):
    HA_API_URL = HA_API_URL[:-1]
if not HA_API_URL.endswith("/api") and not HA_API_URL.endswith("/core/api"):
    HA_API_URL = f"{HA_API_URL}/api"

# Dedicated backup & history paths to prevent conflict
BACKUP_DIR = "/config/hermes/backups"
HISTORY_DIR = "/config/hermes/backups/history"

def auto_backup_yaml(file_path: str, max_keep: int = 10) -> str:
    """
    Creates a timestamped backup of the given YAML file in /config/hermes/backups/.
    Keeps only the latest max_keep (10) backups for the file, auto-deleting older ones.
    """
    if not os.path.exists(file_path):
        return f"File {file_path} does not exist. Cannot backup."
    
    os.makedirs(BACKUP_DIR, exist_ok=True)
    filename = os.path.basename(file_path)
    name, ext = os.path.splitext(filename)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"{name}_{timestamp}{ext}")
    shutil.copy2(file_path, backup_path)
    
    # Rotation: Keep max 10 backups per file pattern
    pattern = os.path.join(BACKUP_DIR, f"{name}_*{ext}")
    backups = sorted(glob.glob(pattern), key=os.path.getmtime)
    while len(backups) > max_keep:
        removed = backups.pop(0)
        try:
            os.remove(removed)
        except Exception as e:
            logger.error(f"Failed to remove old backup {removed}: {e}")
            
    return backup_path

def log_yaml_change_history(file_path: str, root_cause: str, fix_applied: str, before_code: str, after_code: str, start_line: int, end_line: int, expected_outcome: str, max_months_keep: int = 12):
    """
    Appends the change log to the current month's log file (yaml_history_YYYY_MM.md).
    Rotates monthly log files, retaining only the latest 12 months (max 12 files).
    """
    os.makedirs(HISTORY_DIR, exist_ok=True)
    now = datetime.now()
    month_str = now.strftime("%Y_%M")
    timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")
    
    history_file = os.path.join(HISTORY_DIR, f"yaml_history_{month_str}.md")
    
    log_entry = f"""
### [{timestamp_str}] {os.path.basename(file_path)}
- **Path**: `{file_path}`
- **Root Cause**: {root_cause}
- **Fix Applied**: {fix_applied}
- **Lines Changed**: Lines {start_line} - {end_line}
- **변경 전 구문 (Before Change)**:
```yaml
{before_code}
```
- **변경 후 구문 (After Change)**:
```yaml
{after_code}
```
- **Expected Outcome**: {expected_outcome}

---
"""
    with open(history_file, "a", encoding="utf-8") as f:
        f.write(log_entry)
        
    # Rotate monthly files: Keep at most max_months_keep (12)
    pattern = os.path.join(HISTORY_DIR, "yaml_history_*.md")
    month_files = sorted(glob.glob(pattern))
    while len(month_files) > max_months_keep:
        removed = month_files.pop(0)
        try:
            os.remove(removed)
        except Exception as e:
            logger.error(f"Failed to remove old monthly history {removed}: {e}")

def rollback_yaml(file_path: str) -> str:
    """
    Restores the given YAML file from its most recent backup in /config/hermes/backups/.
    """
    filename = os.path.basename(file_path)
    name, ext = os.path.splitext(filename)
    pattern = os.path.join(BACKUP_DIR, f"{name}_*{ext}")
    backups = sorted(glob.glob(pattern), key=os.path.getmtime)
    
    if not backups:
        return f"No backup found for {filename}."
    
    latest_backup = backups[-1]
    shutil.copy2(latest_backup, file_path)
    return f"Successfully rolled back {filename} from {os.path.basename(latest_backup)}."

def check_ha_config() -> str:
    """
    Triggers a Home Assistant Core configuration check via Supervisor API.
    """
    if not SUPERVISOR_TOKEN:
        return "Warning: SUPERVISOR_TOKEN missing, skipping core check."
    headers = {
        "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
        "Content-Type": "application/json",
    }
    url = "http://supervisor/core/check"
    try:
        resp = requests.post(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            result = data.get("result", "valid")
            if result == "valid":
                return "VALID: Home Assistant configuration check passed."
            else:
                return f"INVALID: Configuration check failed - {json.dumps(data)}"
        else:
            return f"HTTP {resp.status_code}: Core check API error."
    except Exception as e:
        return f"Core check request error: {str(e)}"

def backup_and_update_yaml(file_path: str, new_content: str, start_line: int, end_line: int, root_cause: str, fix_applied: str, expected_outcome: str) -> str:
    """
    Safely updates a specified range of lines [start_line, end_line] in a YAML file.
    Automatically creates a timestamped backup before modification, logs before/after diffs in monthly history,
    and runs a Home Assistant core syntax check. Rolls back automatically if syntax check fails.
    """
    if not os.path.exists(file_path):
        return f"Error: Target file {file_path} does not exist."

    # 1. Backup before editing
    backup_result = auto_backup_yaml(file_path)
    
    # 2. Read existing content & extract before_code
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    start_idx = max(0, start_line - 1)
    end_idx = min(len(lines), end_line)
    before_lines = lines[start_idx:end_idx]
    before_code = "".join(before_lines).rstrip()

    # 3. Modify content
    new_lines = new_content.splitlines(keepends=True)
    if new_lines and not new_lines[-1].endswith('\n'):
        new_lines[-1] += '\n'
        
    lines[start_idx:end_idx] = new_lines
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
        
    after_code = new_content.rstrip()

    # 4. Log monthly change history
    log_yaml_change_history(
        file_path=file_path,
        root_cause=root_cause,
        fix_applied=fix_applied,
        before_code=before_code,
        after_code=after_code,
        start_line=start_line,
        end_line=end_line,
        expected_outcome=expected_outcome
    )
    
    # 5. Core check validation
    check_result = check_ha_config()
    if "INVALID" in check_result:
        rollback_msg = rollback_yaml(file_path)
        return f"CRITICAL: Syntax error detected! Modification rolled back.\nDetails: {check_result}\n{rollback_msg}"
        
    return f"Success: {file_path} updated (Backup: {os.path.basename(backup_result)}).\nConfig Check: {check_result}"

def get_device_state(entity_id: str = "") -> str:
    """
    Fetch the current state and attributes of a Home Assistant entity, or all entities if entity_id is empty or 'all'.
    """
    if not SUPERVISOR_TOKEN:
        return "Error: SUPERVISOR_TOKEN / HASS_TOKEN is missing. Please set SUPERVISOR_TOKEN in .env with your Home Assistant Long-Lived Access Token."
    
    headers = {
        "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
        "Content-Type": "application/json",
    }
    
    clean_id = (entity_id or "").strip()
    if not clean_id or clean_id.lower() in ["all", "all_devices", "all_states", "our_house", "우리집"]:
        url = f"{HA_API_URL}/states"
    else:
        url = f"{HA_API_URL}/states/{clean_id}"

    try:
        resp = requests.get(url, headers=headers, timeout=10, verify=False)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                summary = []
                for item in data:
                    eid = item.get("entity_id", "")
                    st = item.get("state", "")
                    name = item.get("attributes", {}).get("friendly_name", eid)
                    if st not in ["unavailable", "unknown"]:
                        summary.append(f"- {name} ({eid}): {st}")
                if not summary:
                    return "Home Assistant is connected, but no active devices were found."
                # 불필요한 시스템 기기(update, zone 등)를 뒤로 보내고, 중요한 기기(light, switch, sensor, climate, media_player)를 우선 정렬
                important_domains = ("light.", "switch.", "sensor.", "climate.", "media_player.", "cover.", "lock.", "fan.", "vacuum.")
                summary.sort(key=lambda x: 0 if any(dom in x for dom in important_domains) else 1)
                return f"Total Entities: {len(data)}\nActive Summary:\n" + "\n".join(summary)
            else:
                return f"State: {data.get('state')}, Attributes: {json.dumps(data.get('attributes', {}), ensure_ascii=False)}"
        elif resp.status_code == 404:
            return f"Entity {entity_id} not found."
        else:
            return f"Error fetching state: HTTP {resp.status_code} (Target URL: {url})"
    except Exception as e:
        return f"Request failed: {str(e)}. Target HA_API_URL: {HA_API_URL}"

def call_ha_service(domain: str, service: str, entity_id: str = None, service_data: dict = None) -> str:
    """
    Call a Home Assistant service to control a device.
    """
    if not SUPERVISOR_TOKEN:
        return "Error: SUPERVISOR_TOKEN is missing."

    headers = {
        "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
        "Content-Type": "application/json",
    }
    url = f"{HA_API_URL}/services/{domain}/{service}"
    payload = service_data or {}
    if entity_id:
        payload["entity_id"] = entity_id

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=5, verify=False)
        if resp.status_code == 200:
            return "Service called successfully."
        else:
            return f"Error calling service: HTTP {resp.status_code}"
    except Exception as e:
        return f"Request failed: {str(e)}"

def get_supported_models(client):
    # 무료 한도 최우선 순서: 2.0-flash → 2.5-flash → 1.5-flash (limit:0 모델은 자동 제외)
    supported = []
    try:
        for m in client.models.list():
            name = getattr(m, 'name', '') or ''
            name = name.replace('models/', '')
            if name.startswith('gemini'):
                supported.append(name)
        logger.info(f"Available models from API: {supported}")
    except Exception as e:
        logger.warning(f"Could not query models.list(): {e}")

    # 우선순위: 복잡한 YAML/코드 완벽 처리를 위한 Pro 모델 최우선 ➔ 3.6 Flash / 2.5 Flash 순차 폴백
    preferred = [
        'gemini-2.5-pro',        # 1순위: 최신 2.5 Pro (YAML/코드 작성 및 복잡한 추론 최상위 성능)
        'gemini-3.6-flash',      # 2순위: 최신 3.6 Flash
        'gemini-2.5-flash',      # 3순위: 2.5 Flash (속도 및 쿼터 한도 넉넉함)
        'gemini-2.0-flash',      # 4순위: 2.0 Flash
        'gemini-2.0-flash-lite', # 5순위: 2.0 Flash-Lite
        'gemini-1.5-pro',        # 6순위: 1.5 Pro
        'gemini-1.5-flash',      # 7순위: 1.5 Flash
    ]
    ordered = [m for m in preferred if m in supported]
    if not ordered:
        ordered = supported if supported else ['gemini-2.5-pro', 'gemini-3.6-flash', 'gemini-2.5-flash']
    return ordered

SYS_INSTRUCTION = """You are a smart home assistant powered by Gemini. You have full access to Home Assistant.
Help the user check device states, control devices, and safely update YAML files in Korean.

DEVICE STATUS & QUERY RULES:
1. When the user asks about device states, room temperatures, lights, or overall home status (e.g., "우리집 전체 온도", "거실 상태", "집안 상태"), ALWAYS invoke `get_device_state(entity_id="")` first to retrieve the real-time states of all Home Assistant entities.
2. Search through the returned device list for relevant entity names (e.g., matching "온도", "temp", "거실", "안방", etc.) and answer concisely in Korean with the exact status/values.

IMPORTANT RULES FOR YAML MODIFICATIONS:
1. ALWAYS use the `backup_and_update_yaml` tool whenever editing any YAML files. Never overwrite files directly.
2. Provide precise parameters: `file_path`, `new_content`, `start_line`, `end_line`, `root_cause`, `fix_applied`, and `expected_outcome`.
3. Preserve existing Entity IDs and core logic structure.
4. If a syntax check fails or user requests undo, use `rollback_yaml`.
5. Always summarize your response to the user using the standard format:
   - **Root Cause (원인)**
   - **Fix Applied (수정 내용)**
   - **Expected Outcome (기대 효과)**
"""

TOOLS_LIST = [get_device_state, call_ha_service, backup_and_update_yaml, rollback_yaml, check_ha_config]
TOOL_MAP = {
    "get_device_state": get_device_state,
    "call_ha_service": call_ha_service,
    "backup_and_update_yaml": backup_and_update_yaml,
    "rollback_yaml": rollback_yaml,
    "check_ha_config": check_ha_config,
}

def execute_tool_call(fn_call):
    name = getattr(fn_call, 'name', '') or ''
    raw_args = getattr(fn_call, 'args', {}) or {}
    clean_args = dict(raw_args) if hasattr(raw_args, 'items') else {}
    if name in TOOL_MAP:
        try:
            logger.info(f"Executing tool '{name}' with args: {clean_args}")
            res = TOOL_MAP[name](**clean_args)
            return str(res)
        except Exception as e:
            logger.error(f"Error executing tool '{name}': {e}")
            return f"Error executing tool {name}: {e}"
    return f"Unknown tool: {name}"

active_model_name = "gemini-2.0-flash"
client = None
CANDIDATE_MODELS = ['gemini-2.0-flash', 'gemini-1.5-flash']

if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
    CANDIDATE_MODELS = get_supported_models(client)
    logger.info(f"Discovered supported Gemini models: {CANDIDATE_MODELS}")
    active_model_name = options.get("gemini_model") or os.getenv("GEMINI_MODEL") or (CANDIDATE_MODELS[0] if CANDIDATE_MODELS else "gemini-2.0-flash")
    logger.info(f"Initialized Gemini model: {active_model_name}")
else:
    logger.warning("GEMINI_API_KEY is not set!")


chat_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if AUTHORIZED_CHAT_IDS and chat_id not in AUTHORIZED_CHAT_IDS:
        await update.message.reply_text("Unauthorized chat.")
        return
    await update.message.reply_text("안녕하세요! 저는 Gemini 기반 Home Assistant 에이전트입니다. 기기 제어 및 안전한 YAML 설정 관리를 도와드립니다.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global model, active_model_name
    chat_id = update.effective_chat.id
    if AUTHORIZED_CHAT_IDS and chat_id not in AUTHORIZED_CHAT_IDS:
        logger.warning(f"Unauthorized chat_id attempt: {chat_id} (Allowed: {AUTHORIZED_CHAT_IDS})")
        await update.message.reply_text(f"⚠️ 인증되지 않은 계정입니다.\n사용자님의 Telegram Chat ID: `{chat_id}`\n`.env` 파일의 `AUTHORIZED_CHAT_IDS`에 등록해 주세요.")
        return
    
    user_text = update.message.text
    if not client:
        await update.message.reply_text("Gemini API 키가 설정되지 않았습니다.")
        return

    # 모델 폴백 순회 (404/429 자동 스위칭)
    models_to_try = [active_model_name] + [m for m in CANDIDATE_MODELS if m != active_model_name]
    last_error = None

    for candidate in models_to_try:
        try:
            if active_model_name != candidate:
                logger.info(f"Switching Gemini model to: {candidate}")
                active_model_name = candidate
                if chat_id in chat_sessions:
                    del chat_sessions[chat_id]

            if chat_id not in chat_sessions:
                chat_sessions[chat_id] = client.chats.create(
                    model=active_model_name,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=SYS_INSTRUCTION,
                        tools=TOOLS_LIST,
                    )
                )

            chat = chat_sessions[chat_id]
            response = chat.send_message(user_text)

            # 도구(Tool) 자동 실행 루프
            loop_count = 0
            while response.function_calls and loop_count < 5:
                loop_count += 1
                logger.info(f"Tool execution loop #{loop_count}: requested {len(response.function_calls)} calls")
                tool_parts = []
                for fn_call in response.function_calls:
                    tool_res = execute_tool_call(fn_call)
                    tool_parts.append(
                        genai_types.Part.from_function_response(
                            name=fn_call.name,
                            response={"result": tool_res}
                        )
                    )
                response = chat.send_message(tool_parts)

            final_text = response.text or "요청이 처리되었습니다."
            await update.message.reply_text(final_text)
            return

        except Exception as e:
            last_error = e
            err_str = str(e)
            if "api_key_invalid" in err_str.lower() or "api key not valid" in err_str.lower():
                logger.error(f"Invalid Gemini API Key: {err_str}")
                await update.message.reply_text("⚠️ Gemini API 키가 유효하지 않습니다.\nhttps://aistudio.google.com/ 에서 새 키를 발급받아 `.env`의 `GEMINI_API_KEY`에 입력해 주세요.")
                return

            if any(k in err_str.lower() for k in ["404", "429", "quota", "rate_limit", "resource_exhausted", "exceeded", "limit", "not found"]):
                logger.warning(f"Model {candidate} failed ({err_str}), falling back...")
                continue
            else:
                logger.error(f"Error calling Gemini: {e}")
                await update.message.reply_text(f"요청 처리 중 오류가 발생했습니다: {e}")
                return

    logger.error(f"All candidate models failed. Last error: {last_error}")
    await update.message.reply_text(f"⚠️ Gemini API 호출 실패:\n{last_error}\nAPI 키 한도(Quota) 또는 Google API 상태를 확인해 주세요.")

def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not provided. Telegram bot will not start.")
        import time
        while True:
            time.sleep(3600)
        return

    try:
        app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        logger.info("Starting Telegram Bot Polling with Auto-Backup & Rotation Tools...")
        app.run_polling()
    except Exception as e:
        logger.error(f"Telegram Bot failed to start: {e}. Check if TELEGRAM_BOT_TOKEN is valid.")
        import time
        while True:
            time.sleep(3600)

if __name__ == "__main__":
    main()
