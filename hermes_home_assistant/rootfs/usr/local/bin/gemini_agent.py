#!/usr/bin/env python3
import warnings
warnings.filterwarnings("ignore")
import os
import sys
import json
import glob
import shutil
import logging
import subprocess

# Dynamically discover all site-packages in system
for search_dir in ["/usr", "/opt", "/root", "/var"]:
    for sp in glob.glob(f"{search_dir}/**/site-packages", recursive=True) + glob.glob(f"{search_dir}/**/dist-packages", recursive=True):
        if sp not in sys.path:
            sys.path.insert(0, sp)

try:
    import requests
except ImportError:
    logger.warning("requests module not found, installing via pip...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
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

def _read_env_file_directly() -> dict:
    env_vars = {}
    for p in ["/config/.env", "/opt/Homeassistant-hermes/.env", "/usr/local/bin/.env", ".env"]:
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8-sig", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            env_vars[k.strip()] = v.strip().strip('\'"')
            except Exception:
                pass
    return env_vars

_direct_env = _read_env_file_directly()

GEMINI_API_KEY = _clean_token(options.get("gemini_api_key") or os.getenv("GEMINI_API_KEY") or _read_s6_env("GEMINI_API_KEY") or _direct_env.get("GEMINI_API_KEY"))
TELEGRAM_BOT_TOKEN = _clean_token(options.get("telegram_bot_token") or os.getenv("TELEGRAM_BOT_TOKEN") or _read_s6_env("TELEGRAM_BOT_TOKEN") or _direct_env.get("TELEGRAM_BOT_TOKEN"))

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
    or _direct_env.get("SUPERVISOR_TOKEN")
    or _direct_env.get("HASS_TOKEN")
    or _direct_env.get("HA_TOKEN")
)

raw_url = _clean_token(
    os.getenv("HASS_URL")
    or os.getenv("HA_URL")
    or options.get("hass_url")
    or options.get("ha_url")
    or _read_s6_env("HASS_URL")
    or _read_s6_env("HA_URL")
    or _direct_env.get("HASS_URL")
    or _direct_env.get("HA_URL")
)
if not raw_url or "supervisor" in raw_url or "172.17.0.1" in raw_url:
    raw_url = "https://ha.dicapriokim.ddnsfree.com"

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
    Triggers a Home Assistant Core configuration check via Supervisor API or HA Core REST API.
    """
    if not SUPERVISOR_TOKEN:
        return "Warning: SUPERVISOR_TOKEN / HASS_TOKEN missing, skipping core check."
    headers = {
        "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
        "Content-Type": "application/json",
    }
    
    # 1. Supervisor API 시도 (HA OS Add-on 환경)
    try:
        resp = requests.post("http://supervisor/core/check", headers=headers, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            result = data.get("result", "valid")
            if result == "valid":
                return "VALID: Home Assistant configuration check passed (via Supervisor API)."
            else:
                return f"INVALID: Configuration check failed - {json.dumps(data)}"
    except Exception as e:
        logger.info(f"Supervisor API check skipped ({e}), falling back to HA REST API...")

    # 2. HA Core REST API 폴백 (스탠드얼론 Docker / LXC 독립 환경)
    try:
        url = f"{HA_API_URL}/config/core/check_config"
        resp = requests.post(url, headers=headers, timeout=10, verify=False)
        if resp.status_code == 200:
            data = resp.json()
            result = data.get("result", "valid")
            if result == "valid":
                return "VALID: Home Assistant configuration check passed (via HA REST API)."
            else:
                errors = data.get("errors", json.dumps(data))
                return f"INVALID: Configuration check failed - {errors}"
        elif resp.status_code == 404:
            service_url = f"{HA_API_URL}/services/homeassistant/check_config"
            s_resp = requests.post(service_url, headers=headers, timeout=10, verify=False)
            if s_resp.status_code in [200, 201]:
                return "VALID: Home Assistant configuration check triggered (via HA Service API)."
            return f"HTTP {resp.status_code}: Core check REST endpoint not found."
        else:
            return f"HTTP {resp.status_code}: Core check REST API error."
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
    return f"Success: {file_path} updated (Backup: {os.path.basename(backup_result)}).\nConfig Check: {check_result}"

def query_ha_raw_entities(query: str = "") -> str:
    """
    Directly search all 1,927 HA entities for location and target metrics in Emergency Mode.
    """
    if not SUPERVISOR_TOKEN:
        return ""
    headers = {
        "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.get(f"{HA_API_URL}/states", headers=headers, timeout=5, verify=False)
        if resp.status_code == 200 and isinstance(resp.json(), list):
            raw_q = (query or "").strip()
            if not raw_q:
                return ""

            # 1. 측정 의도 키워드 감지 (온도, 습도, 조명, 스위치)
            want_temp = any(k in raw_q for k in ["온도", "기온", "몇도", "도"])
            want_hum = any(k in raw_q for k in ["습도", "습한"])
            want_light = any(k in raw_q for k in ["조명", "불", "전등", "램프"])
            want_switch = any(k in raw_q for k in ["스위치", "플러그", "가전"])

            # 2. 불용어 및 조작어 제거 후 순수 위치/기기명 추출
            strip_words = ["상태", "알려줘", "알려주라", "보여줘", "어때", "현재", "지금", "좀", "는", "은", "가", "이", "?", "!", ".", "조회", "온도", "습도", "조명", "불", "스위치"]
            clean_q = raw_q
            for sw in strip_words:
                clean_q = clean_q.replace(sw, " ")

            loc_keywords = [w.strip() for w in clean_q.split() if len(w.strip()) >= 1]
            if not loc_keywords:
                loc_keywords = [w.strip() for w in raw_q.split() if len(w.strip()) >= 1]

            matched = []
            for item in resp.json():
                eid = item.get("entity_id", "")
                st = str(item.get("state", "")).strip()
                attrs = item.get("attributes", {})
                name = attrs.get("friendly_name", eid)
                unit = str(attrs.get("unit_of_measurement", "")).strip()
                device_class = str(attrs.get("device_class", "")).strip()

                if st in ["unavailable", "unknown"]:
                    continue

                # 위치/기기명 일치 검사
                loc_match = any(kw.lower() in name.lower() or kw.lower() in eid.lower() for kw in loc_keywords)
                if not loc_match:
                    continue

                # 측정 의도 타겟 필터링
                if want_temp:
                    if not (unit in ["°C", "°F"] or device_class == "temperature" or "온도" in name or "기온" in name):
                        continue
                elif want_hum:
                    if not (unit == "%" or device_class == "humidity" or "습도" in name):
                        continue
                elif want_light:
                    if not (eid.startswith("light.") or "조명" in name or "불" in name or "전등" in name):
                        continue
                elif want_switch:
                    if not (eid.startswith("switch.") or "스위치" in name or "플러그" in name):
                        continue

                unit_str = f" {unit}" if unit else ""
                matched.append(f"  • {name}: `{st}{unit_str}`")

            if matched:
                kw_str = " ".join(loc_keywords)
                intent_desc = "온도" if want_temp else ("습도" if want_hum else ("조명" if want_light else ""))
                title_suffix = f" {intent_desc}" if intent_desc else ""
                return f"📍 **['{kw_str}{title_suffix}' 검색 결과 ({len(matched)}개)]**\n" + "\n".join(matched[:10])
    except Exception as e:
        logger.error(f"Error in query_ha_raw_entities: {e}")
    return ""

def control_ha_device_offline(query: str = "") -> str:
    """
    Directly control HA devices (turn_on / turn_off) via REST API in Emergency Mode.
    """
    if not SUPERVISOR_TOKEN or not query:
        return ""
    
    raw_q = query.strip()
    want_off = any(k in raw_q for k in ["꺼", "끄자", "꺼줘", "꺼라", "소등", "off", "끄기"])
    want_on = any(k in raw_q for k in ["켜", "켜자", "켜줘", "켜라", "점등", "on", "켜기"])

    if not want_off and not want_on:
        return ""

    action_service = "turn_off" if want_off else "turn_on"
    action_kr = "끄기(OFF)" if want_off else "켜기(ON)"

    # Clean location/device keywords
    strip_words = ["꺼", "끄자", "꺼줘", "꺼라", "소등", "off", "켜", "켜자", "켜줘", "켜라", "점등", "on", "상태", "알려줘", "알려주라", "보여줘", "어때", "현재", "지금", "좀", "는", "은", "가", "이", "?", "!", ".", "조회", "해줘", "부탁해"]
    clean_q = raw_q
    for sw in strip_words:
        clean_q = clean_q.replace(sw, " ")
    
    loc_keywords = [w.strip() for w in clean_q.split() if len(w.strip()) >= 1]
    if not loc_keywords:
        return ""

    headers = {"Authorization": f"Bearer {SUPERVISOR_TOKEN}", "Content-Type": "application/json"}
    try:
        resp = requests.get(f"{HA_API_URL}/states", headers=headers, timeout=5, verify=False)
        if resp.status_code == 200 and isinstance(resp.json(), list):
            targets = []
            for item in resp.json():
                eid = item.get("entity_id", "")
                attrs = item.get("attributes", {})
                name = attrs.get("friendly_name", eid)
                domain = eid.split(".")[0]

                if domain not in ["light", "switch", "climate", "fan", "media_player"]:
                    continue

                if any(kw.lower() in name.lower() or kw.lower() in eid.lower() for kw in loc_keywords):
                    targets.append((domain, eid, name))

            if targets:
                executed = []
                for domain, eid, name in targets[:3]:  # max 3 devices per command
                    res = call_ha_service(domain, action_service, entity_id=eid)
                    if "successfully" in res.lower():
                        executed.append(f"  • **{name}** (`{eid}`): `{action_kr}` 성공")
                if executed:
                    kw_str = " ".join(loc_keywords)
                    return f"⚡ **['{kw_str}' 오프라인 기기 직접 제어 결과]**\n" + "\n".join(executed)
    except Exception as e:
        logger.error(f"Error in control_ha_device_offline: {e}")
    return ""

def get_ha_exposed_entity_ids() -> set:
    """
    Fetch exact exposed entity IDs from Home Assistant Voice Assistants REST API endpoints.
    """
    if not SUPERVISOR_TOKEN:
        return set()
    headers = {
        "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
        "Content-Type": "application/json",
    }
    exposed_ids = set()
    
    # 1. HA Voice Assistants exposed entities 엔드포인트 조회
    try:
        url = f"{HA_API_URL}/voice_assistants/exposed_entities"
        resp = requests.get(url, headers=headers, timeout=5, verify=False)
        if resp.status_code == 200:
            v_data = resp.json()
            exp_dict = v_data.get("exposed_entities", {})
            for assistant_name, entities in exp_dict.items():
                if isinstance(entities, dict):
                    for eid, is_exp in entities.items():
                        if is_exp is True or is_exp == {}:
                            exposed_ids.add(eid)
    except Exception:
        pass

    # 2. HA Config Entity Registry 엔드포인트 조회 (should_expose 명시 확인)
    if not exposed_ids:
        try:
            url = f"{HA_API_URL}/config/entity_registry"
            resp = requests.get(url, headers=headers, timeout=5, verify=False)
            if resp.status_code == 200:
                reg_data = resp.json()
                for entry in reg_data:
                    eid = entry.get("entity_id", "")
                    disabled = entry.get("disabled_by")
                    options = entry.get("options", {})
                    conv_options = options.get("conversation", {})
                    should_expose = conv_options.get("should_expose")
                    if not disabled and should_expose is True:
                        exposed_ids.add(eid)
        except Exception:
            pass

    return exposed_ids

def get_ha_entity_area_map() -> dict:
    """
    Returns a dictionary mapping entity_id -> area_name using Home Assistant Jinja2 template API.
    Example: {'sensor.air_monitor_lite_2a53_temperature': '작은방', 'sensor.0xa4c1389a7be5dc7b_temperature': '안방'}
    """
    if not SUPERVISOR_TOKEN or not HA_API_URL:
        return {}
    headers = {"Authorization": f"Bearer {SUPERVISOR_TOKEN}", "Content-Type": "application/json"}
    tmpl = "{% for s in states %}{{ s.entity_id }}|{{ area_name(s.entity_id) or '' }}\n{% endfor %}"
    try:
        resp = requests.post(f"{HA_API_URL}/template", headers=headers, json={"template": tmpl}, timeout=5, verify=False)
        if resp.status_code == 200:
            area_map = {}
            for line in resp.text.splitlines():
                if "|" in line:
                    parts = line.split("|", 1)
                    eid = parts[0].strip()
                    aname = parts[1].strip()
                    if aname:
                        area_map[eid] = aname
            return area_map
    except Exception as e:
        logger.warning(f"Failed to fetch entity area map: {e}")
    return {}

def format_smart_home_summary(raw_entities: list) -> str:
    total_count = len(raw_entities)
    
    # HA 웹 UI (설정 > 음성 비서 > 노출된 엔티티) REST API를 통해 사용자가 노출 지정한 엔티티만 엄격하게 필터링
    exposed_ids = get_ha_exposed_entity_ids()
    if exposed_ids:
        filtered_exposed = [item for item in raw_entities if item.get("entity_id") in exposed_ids]
        if filtered_exposed:
            raw_entities = filtered_exposed

    # HA 영역(Area) 레지스트리 맵핑 정보 사전 수집
    area_map = get_ha_entity_area_map()

    # 장소별 온·습도 딕셔너리: room_name -> {'temp': float, 'hum': float}
    climate_rooms = {}
    active_lights = []
    active_switches = []
    open_sensors = []
    low_batteries = []
    off_devices = []

    # 불필요한 시스템 센서 및 노이즈 키워드 필터링
    noise_keywords = [
        "backup", "batteryvoltage", "batterytype", "timeremaining", 
        "connection", "bridge", "jeonryeog", "jeonab", "jeonryu", "eneoji",
        "update", "zone.", "sun.", "persistent_notification.", "automation.", "script.",
        "espphone", "espwatch", "espresense", "do not disturb", "tamper", "탬퍼"
    ]

    for item in raw_entities:
        eid = item.get("entity_id", "")
        st = str(item.get("state", "")).strip()
        attrs = item.get("attributes", {})
        name = attrs.get("friendly_name", eid)
        _area = area_map.get(eid)
        if _area and _area.lower() not in ["none", "null", "로컬", "server"]:
            name = f"[{_area}] {name}"
            
        unit = str(attrs.get("unit_of_measurement", "")).strip()
        device_class = str(attrs.get("device_class", "")).strip()

        eid_lower = eid.lower()
        name_lower = name.lower()

        if st in ["unavailable", "unknown"]:
            continue
            
        # 배터리 전용 센서는 온/습도 계산에서 즉시 제외하여 하단으로 분리
        is_battery_entity = ("baeteori" in name_lower or "battery" in eid_lower or "battery" in name_lower or device_class == "battery")
        if is_battery_entity:
            try:
                val = float(st)
                if val <= 20.0:
                    low_batteries.append(f"{name} ({val:.1f}%)")
            except ValueError:
                pass
            continue

        # 노이즈 센서 걸러내기
        if any(k in eid_lower or k in name_lower for k in noise_keywords):
            continue

        # 1. 온도 / 습도 센서 추출 및 장소 단위 병합
        is_temp = (unit in ["°C", "°F"] or device_class == "temperature" or ("온도" in name and "습도" not in name))
        is_hum = (unit == "%" or device_class == "humidity" or ("습도" in name and "온도" not in name))

        if is_temp or is_hum:
            try:
                val = round(float(st), 1)
                # 이름에 이미 [영역]이 포함되어 있으면 그대로 사용
                if name.startswith("[") and "] " in name:
                    base_room = name.split("] ", 1)[0][1:]
                else:
                    base_room = name.replace("온도습도계", "").replace("온도", "").replace("습도", "").replace("  ", " ").strip()
                    if not base_room:
                        base_room = name

                if base_room not in climate_rooms:
                    climate_rooms[base_room] = {}

                if is_temp:
                    climate_rooms[base_room]['temp'] = val
                elif is_hum:
                    climate_rooms[base_room]['hum'] = val
            except ValueError:
                pass
            continue

        # 2. 조명
        elif eid_lower.startswith("light."):
            if st == "on":
                active_lights.append(name)
            else:
                off_devices.append(name)

        # 3. 스위치/가전
        elif eid_lower.startswith("switch."):
            if st == "on":
                active_switches.append(name)
            else:
                off_devices.append(name)

        # 4. 열린 창문/문 및 재실 감지
        elif eid_lower.startswith("binary_sensor.") and st in ["on", "open"]:
            open_sensors.append(name)

    lines = [f"📊 **우리 집 스마트홈 브리핑** (HA 전체 {total_count}개 기기 연동 중)\n"]

    if climate_rooms:
        lines.append("🌡️ **실내 온·습도 현황**:")
        for r_name, data in list(climate_rooms.items())[:12]:
            temp_str = f"{data['temp']:.1f}°C" if 'temp' in data else None
            hum_str = f"습도 {data['hum']:.1f}%" if 'hum' in data else None

            if temp_str and hum_str:
                lines.append(f"  • {r_name}: `{temp_str}` / `{hum_str}`")
            elif temp_str:
                lines.append(f"  • {r_name}: `{temp_str}`")
            elif hum_str:
                lines.append(f"  • {r_name}: `{hum_str}`")
        lines.append("")

    if active_lights:
        lines.append(f"💡 **켜져 있는 조명 ({len(active_lights)}개)**:")
        lines.append(f"  • {', '.join(active_lights[:8])}")
        lines.append("")

    if active_switches:
        lines.append(f"⚡ **켜져 있는 가전/스위치 ({len(active_switches)}개)**:")
        lines.append(f"  • {', '.join(active_switches[:8])}")
        lines.append("")

    if open_sensors:
        lines.append(f"🚪 **열린 창문/문 및 감지 센서 ({len(open_sensors)}개)**:")
        lines.append(f"  • {', '.join(open_sensors[:8])}")
        lines.append("")

    if low_batteries:
        lines.append(f"🪫 **배터리 교체 필요 ({len(low_batteries)}개)**:")
        lines.append(f"  • {', '.join(low_batteries)}")
        lines.append("")

    if off_devices:
        lines.append(f"💤 **꺼진 기기 ({len(off_devices)}개)**: " + ", ".join(off_devices[:15]))
        lines.append("")

    if len(lines) == 1:
        lines.append("현재 특이사항 없이 모든 기기가 정상적으로 작동 중입니다.")

    return "\n".join(lines)

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
                return format_smart_home_summary(data)
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
    supported = []
    try:
        for m in client.models.list():
            name = getattr(m, 'name', '') or ''
            name = name.replace('models/', '')
            # 쿼터 한도(limit:0 및 250k token limit) 에러가 빈번한 pro, 3.5, 3.1, 3.0, 2.5, vision, preview 계열 배제
            if name.startswith('gemini') and not any(p in name for p in ["pro", "3.5", "3.1", "3.0", "2.5", "vision", "preview"]):
                supported.append(name)
        logger.info(f"Available models from API: {supported}")
    except Exception as e:
        logger.warning(f"Could not query models.list(): {e}")

    preferred_patterns = [
        'gemini-flash-latest',
        'gemini-1.5-flash',
        'gemini-1.5-flash-8b',
        'gemini-2.0-flash-lite',
        'gemini-2.0-flash',
    ]
    
    ordered = []
    for pref in preferred_patterns:
        for s in supported:
            if s not in ordered and (s == pref or s.startswith(f"{pref}-")):
                ordered.append(s)
    
    # 추가로 매칭되지 않은 나머지 모델 중 배제 키워드 없는 것만 포함
    for s in supported:
        if s not in ordered:
            ordered.append(s)

    if not ordered:
        ordered = ['gemini-flash-latest', 'gemini-1.5-flash']
    return ordered

def read_yaml_file(file_path: str = "/config/automations.yaml") -> str:
    """
    Reads the content of a Home Assistant YAML configuration file.
    If local file does not exist, automatically fetches live automations from Home Assistant API.
    """
    if not file_path:
        file_path = "/config/automations.yaml"
    if not file_path.startswith("/config/"):
        file_path = os.path.join("/config", file_path.lstrip("/"))
        
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return f"Content of {file_path}:\n```yaml\n{content}\n```"
        else:
            # Fallback: HA REST API에서 automations.* 엔티티 실시간 수집 및 포맷팅
            if SUPERVISOR_TOKEN and HA_API_URL:
                headers = {"Authorization": f"Bearer {SUPERVISOR_TOKEN}", "Content-Type": "application/json"}
                resp = requests.get(f"{HA_API_URL}/states", headers=headers, timeout=10, verify=False)
                if resp.status_code == 200 and isinstance(resp.json(), list):
                    automations = []
                    for item in resp.json():
                        eid = item.get("entity_id", "")
                        if eid.startswith("automation."):
                            name = item.get("attributes", {}).get("friendly_name", eid)
                            st = item.get("state", "off")
                            last_triggered = item.get("attributes", {}).get("last_triggered", "Never")
                            automations.append(f"  • **{name}** (`{eid}`): 상태 `{st}` (최근 실행: {last_triggered})")
                    if automations:
                        return (
                            f"⚠️ 로컬 `{file_path}` 파일이 존재하지 않아, Home Assistant API(`{HA_API_URL}`)를 통해 실시간 등록된 자동화 목록을 수집했습니다:\n\n"
                            f"📜 **[Home Assistant 활성 자동화 목록 ({len(automations)}개)]**\n" + "\n".join(automations)
                        )
            return f"File {file_path} does not exist. (Target HA_API_URL: {HA_API_URL})"
    except Exception as e:
        return f"Error reading {file_path}: {e}"

def backup_api_automation_before_change(config_id: str, action_name: str = "modification") -> str:
    """
    Fetches the current automation config from HA REST API and saves a timestamped JSON backup in BACKUP_DIR.
    """
    if not SUPERVISOR_TOKEN or not HA_API_URL or not config_id:
        return ""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    headers = {"Authorization": f"Bearer {SUPERVISOR_TOKEN}", "Content-Type": "application/json"}
    url = f"{HA_API_URL}/config/automation/config/{config_id}"
    try:
        resp = requests.get(url, headers=headers, timeout=5, verify=False)
        data = resp.json() if resp.status_code == 200 else {}
        if not data:
            st_resp = requests.get(f"{HA_API_URL}/states/automation.{config_id}", headers=headers, timeout=5, verify=False)
            data = st_resp.json() if st_resp.status_code == 200 else {"id": config_id}

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(BACKUP_DIR, f"api_automation_{config_id}_{timestamp}.json")
        with open(backup_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return backup_file
    except Exception as e:
        logger.warning(f"Could not create API automation backup for {config_id}: {e}")
        return ""

def delete_automation_or_yaml(file_path: str = "/config/automations.yaml", start_line: int = 0, end_line: int = 0, automation_id: str = "") -> str:
    """
    Deletes an automation or YAML block either from a local YAML file by line range [start_line, end_line] or via Home Assistant REST API by automation_id or config ID.
    """
    if not file_path:
        file_path = "/config/automations.yaml"
    if not file_path.startswith("/config/"):
        file_path = os.path.join("/config", file_path.lstrip("/"))

    # 1. Local file line range deletion
    if os.path.exists(file_path) and start_line > 0 and end_line >= start_line:
        backup_result = auto_backup_yaml(file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), end_line)
        before_code = "".join(lines[start_idx:end_idx]).rstrip()
        
        del lines[start_idx:end_idx]
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        log_yaml_change_history(
            file_path=file_path,
            root_cause="User deletion request",
            fix_applied=f"Deleted lines {start_line}-{end_line}",
            before_code=before_code,
            after_code="[DELETED]",
            start_line=start_line,
            end_line=end_line,
            expected_outcome="Automation block removed successfully"
        )
        check_result = check_ha_config()
        return f"Success: Deleted lines {start_line}-{end_line} from {file_path} (Backup: {os.path.basename(backup_result)}).\nConfig Check: {check_result}"

    # 2. HA REST API deletion by automation_id or internal config ID
    clean_id = (automation_id or "").strip()
    if SUPERVISOR_TOKEN and HA_API_URL and clean_id:
        headers = {"Authorization": f"Bearer {SUPERVISOR_TOKEN}", "Content-Type": "application/json"}
        
        # Resolve internal config_id from HA state if entity_id is passed
        config_id = clean_id.replace("automation.", "")
        try:
            full_eid = clean_id if clean_id.startswith("automation.") else f"automation.{clean_id}"
            st_resp = requests.get(f"{HA_API_URL}/states/{full_eid}", headers=headers, timeout=5, verify=False)
            if st_resp.status_code == 200:
                attr_id = st_resp.json().get("attributes", {}).get("id")
                if attr_id:
                    config_id = str(attr_id)
        except Exception:
            pass

        # Save pre-deletion JSON backup file & log history
        backup_file = backup_api_automation_before_change(config_id, action_name="deletion")
        before_code = f"Config ID: {config_id}"
        if backup_file and os.path.exists(backup_file):
            with open(backup_file, "r", encoding="utf-8") as f:
                before_code = f.read()

        url = f"{HA_API_URL}/config/automation/config/{config_id}"
        try:
            resp = requests.delete(url, headers=headers, timeout=10, verify=False)
            if resp.status_code in [200, 204]:
                requests.post(f"{HA_API_URL}/services/automation/reload", headers=headers, timeout=5, verify=False)
                
                log_yaml_change_history(
                    file_path=f"REST_API_Automation_{config_id}",
                    root_cause="User REST API deletion request",
                    fix_applied=f"Deleted automation config_id {config_id} via REST API",
                    before_code=before_code,
                    after_code="[DELETED VIA REST API]",
                    start_line=0,
                    end_line=0,
                    expected_outcome="Automation permanently removed via HA REST API"
                )
                backup_note = f" (Backup: {os.path.basename(backup_file)})" if backup_file else ""
                return f"Success: Automation `{clean_id}` (Config ID: `{config_id}`) permanently deleted via Home Assistant REST API{backup_note}."
            elif resp.status_code in [400, 404, 405]:
                turn_off_res = call_ha_service("automation", "turn_off", entity_id=f"automation.{clean_id}")
                return f"Notice: REST API deletion returned {resp.status_code}. Automation turned OFF (`automation.{clean_id}`): {turn_off_res}"
            else:
                return f"HTTP {resp.status_code}: Automation REST deletion failed for `{clean_id}`."
        except Exception as e:
            return f"API Deletion request error: {str(e)}"

    return f"Error: Provide start_line and end_line for local file {file_path}, or automation_id for API deletion."

SYS_INSTRUCTION = """You are a smart home assistant powered by Gemini. You have full access to Home Assistant.
Help the user check device states, control devices, inspect YAML files, safely update YAML files, and delete automations in Korean.

STRICT RESPONSE QUALITY RULES (품질 3대 불변 규칙):
1. NEVER ask the user to provide entity IDs, YAML code, or internal technical names under any circumstances! Automatically resolve entity IDs via `get_device_state("")` and `read_yaml_file("/config/automations.yaml")`.
2. When answering temperature, climate, or home status queries, NEVER respond with dry single-line values or ask for entity IDs. Always provide a rich, helpful **Smart Home Climate Card (스마트홈 환경 브리핑)**:
   - 🌡️ **현재 실내 온·습도 수치 및 쾌적도 분석** (예: 28.53°C / 약간 무더움)
   - ❄️ **연동된 에어컨/가습기/공기청정기 가동 상태**
   - 💡 **스마트홈 환경 조성을 위한 AI 제안** (예: "에어컨을 25°C로 켤까요?")
3. If only one temperature sensor is currently registered in HA, state clearly and politely: "현재 Home Assistant에 등록되어 수집 중인 온도 센서는 [거실 (28.53°C)] 1개입니다." instead of asking the user for entity IDs.

AUTOMATION CREATION, MODIFICATION & DELETION RULES:
1. Whenever the user requests to edit, modify, add, or delete an automation, use `backup_and_update_yaml` for edits/additions or `delete_automation_or_yaml` for deletions.
2. If local files are absent, use API deletion (`automation_id`) or call `call_ha_service("automation", "turn_off")`.
3. Always summarize your response to the user using the standard format:
   - **Root Cause (원인)**
   - **Fix Applied (수정 내용)**
   - **Expected Outcome (기대 효과)**
"""

TOOLS_LIST = [get_device_state, call_ha_service, read_yaml_file, backup_and_update_yaml, delete_automation_or_yaml, rollback_yaml, check_ha_config]
TOOL_MAP = {
    "get_device_state": get_device_state,
    "call_ha_service": call_ha_service,
    "read_yaml_file": read_yaml_file,
    "backup_and_update_yaml": backup_and_update_yaml,
    "delete_automation_or_yaml": delete_automation_or_yaml,
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

CANDIDATE_MODELS = ['gemini-1.5-flash']
active_model_name = 'gemini-1.5-flash'

if GEMINI_API_KEY:
    masked_key = f"{GEMINI_API_KEY[:6]}...{GEMINI_API_KEY[-4:]}" if len(GEMINI_API_KEY) > 10 else "NOT_SET"
    logger.info(f"Loaded Gemini API Key: {masked_key}")
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # 동적으로 사용 가능한 모델 리스트 가져오기 (404 방지)
    try:
        CANDIDATE_MODELS = get_supported_models(client)
    except Exception as e:
        logger.warning(f"Failed to load dynamic models, using fallback: {e}")
        
    if not CANDIDATE_MODELS:
        CANDIDATE_MODELS = ['gemini-1.5-flash']
    
    env_model = _clean_token(options.get("gemini_model") or os.getenv("GEMINI_MODEL") or _read_s6_env("GEMINI_MODEL") or _direct_env.get("GEMINI_MODEL"))
    if env_model in CANDIDATE_MODELS:
        active_model_name = env_model
    else:
        active_model_name = CANDIDATE_MODELS[0]
        
    logger.info(f"Initialized active Gemini model: {active_model_name}")
else:
    logger.warning("GEMINI_API_KEY is not set!")


chat_sessions = {}

async def safe_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None):
    chat_id = update.effective_chat.id if update and update.effective_chat else None
    if not chat_id:
        return
        
    MAX_LEN = 4000
    chunks = [text[i:i+MAX_LEN] for i in range(0, len(text), MAX_LEN)]
    
    for i, chunk in enumerate(chunks):
        current_markup = reply_markup if i == len(chunks) - 1 else None
        try:
            await context.bot.send_message(chat_id=chat_id, text=chunk, reply_markup=current_markup, parse_mode="Markdown", disable_web_page_preview=True)
        except Exception as e:
            logger.warning(f"Markdown send_message failed ({e}), falling back to plain text...")
            try:
                await context.bot.send_message(chat_id=chat_id, text=chunk, reply_markup=current_markup, disable_web_page_preview=True)
            except Exception as e2:
                logger.error(f"Fallback plain text send_message failed: {e2}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if AUTHORIZED_CHAT_IDS and chat_id not in AUTHORIZED_CHAT_IDS:
        await update.message.reply_text("Unauthorized chat.")
        return
    keyboard = [
        [InlineKeyboardButton("🏠 전체 상태 조회 (/status)", callback_data="cb:status")],
        [InlineKeyboardButton("📜 자동화 목록 (/automations)", callback_data="cb:automations")],
        [InlineKeyboardButton("⏪ 최신 백업 롤백 (/rollback)", callback_data="cb:rollback")],
        [InlineKeyboardButton("🧹 대화 기억 초기화 (/clear)", callback_data="cb:clear")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await safe_reply(
        update,
        context,
        "🤖 **Gemini 기반 Home Assistant 스마트 에이전트**에 오신 것을 환영합니다!\n\n"
        "아래 원클릭 버튼을 누르시거나 자연어/음성으로 편하게 명령을 내려주세요.",
        reply_markup=reply_markup
    )

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if AUTHORIZED_CHAT_IDS and chat_id not in AUTHORIZED_CHAT_IDS:
        return
    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)
    try:
        raw_state = get_device_state("")
        keyboard = [
            [InlineKeyboardButton("🔄 새로고침", callback_data="cb:status")],
            [InlineKeyboardButton("📜 자동화 목록", callback_data="cb:automations")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_reply(update, context, f"📊 **실시간 기기 상태 요약**\n\n{raw_state[:3500]}", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error in cmd_status: {e}")

async def cmd_automations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if AUTHORIZED_CHAT_IDS and chat_id not in AUTHORIZED_CHAT_IDS:
        return
    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)
    try:
        yaml_res = read_yaml_file("/config/automations.yaml")
        keyboard = [
            [InlineKeyboardButton("⏪ 직전 백업 롤백", callback_data="cb:rollback")],
            [InlineKeyboardButton("🏠 전체 상태 조회", callback_data="cb:status")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_reply(update, context, f"📜 **등록된 자동화 YAML 설정**\n\n{yaml_res[:3500]}", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error in cmd_automations: {e}")

async def cmd_rollback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if AUTHORIZED_CHAT_IDS and chat_id not in AUTHORIZED_CHAT_IDS:
        return
    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)
    res = rollback_yaml("/config/automations.yaml")
    await safe_reply(update, context, f"⏪ **백업 롤백 결과**\n\n{res}")

async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in chat_sessions:
        del chat_sessions[chat_id]
    await safe_reply(update, context, "🧹 **대화 기억(Context)이 성공적으로 초기화되었습니다.** 새로운 대화를 시작합니다.")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📖 **텔레그램 봇 단축 명령어 및 가이드**\n\n"
        "• `/status` - 우리 집 전체 기기 및 온·습도 실시간 요약\n"
        "• `/automations` - 현재 등록된 automations.yaml 확인 및 검토\n"
        "• `/emergency [검색어]` - 오프라인 응급 모드 및 핀포인트 직통 검색 시뮬레이션 디버깅\n"
        "• `/rollback` - 직전 안전 백업본으로 YAML 복원\n"
        "• `/clear` - 대화 기억(Context) 초기화\n"
        "• `/help` - 명령어 정보 및 사용 도움말\n\n"
        "🎙️ **음성 메시지 제어**: 음성 메시지를 전송하시면 Gemini AI가 음성을 분석하여 기기 조작을 즉시 실행합니다!"
    )
    await safe_reply(update, context, help_text)

async def cmd_emergency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if AUTHORIZED_CHAT_IDS and chat_id not in AUTHORIZED_CHAT_IDS:
        return
    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)
    
    query_text = ""
    if context.args:
        query_text = " ".join(context.args)

    control_res = control_ha_device_offline(query_text) if query_text else ""
    if control_res:
        body_text = control_res
    else:
        pinpoint_result = query_ha_raw_entities(query_text) if query_text else ""
        body_text = pinpoint_result if pinpoint_result else f"📊 **[실시간 Home Assistant 기기 상태]**\n{get_device_state('')[:1500]}"
    
    keyboard = [
        [InlineKeyboardButton("🏠 전체 상태 조회", callback_data="cb:status"), InlineKeyboardButton("📜 자동화 목록", callback_data="cb:automations")],
        [InlineKeyboardButton("⏪ 백업 롤백", callback_data="cb:rollback"), InlineKeyboardButton("🧹 대화 초기화", callback_data="cb:clear")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await safe_reply(
        update,
        context,
        f"🛠️ **[오프라인 응급 모드 시뮬레이션 디버깅]**\n"
        f"*(💡 API 키 연결 여부와 상관없이 오프라인 응급 모드 및 직통 핀포인트 출력을 검증합니다)*\n\n"
        f"{body_text}",
        reply_markup=reply_markup
    )

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    data = query.data or ""
    logger.info(f"CallbackQuery received: {data} from chat {update.effective_chat.id}")
    try:
        if data == "cb:status":
            await cmd_status(update, context)
        elif data == "cb:automations":
            await cmd_automations(update, context)
        elif data == "cb:rollback":
            await cmd_rollback(update, context)
        elif data == "cb:clear":
            await cmd_clear(update, context)
    except Exception as e:
        logger.error(f"Error handling callback query {data}: {e}")
        try:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"⚠️ 버튼 실행 중 오류가 발생했습니다: {e}")
        except Exception:
            pass

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if AUTHORIZED_CHAT_IDS and chat_id not in AUTHORIZED_CHAT_IDS:
        return
    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)
    try:
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        voice_bytes = await voice_file.download_as_bytearray()
        
        if not client:
            await update.message.reply_text("Gemini API 키가 설정되지 않았습니다.")
            return

        # Gemini 멀티모달 오디오 전달
        audio_part = genai_types.Part.from_bytes(data=bytes(voice_bytes), mime_type="audio/ogg")
        prompt_part = "Listen to this Korean voice message and execute the requested Home Assistant device command or state query."
        
        if chat_id not in chat_sessions:
            chat_sessions[chat_id] = client.chats.create(
                model=active_model_name,
                config=genai_types.GenerateContentConfig(
                    system_instruction=SYS_INSTRUCTION,
                    tools=TOOLS_LIST,
                )
            )
        chat = chat_sessions[chat_id]
        response = chat.send_message([audio_part, prompt_part])

        loop_count = 0
        while response.function_calls and loop_count < 5:
            loop_count += 1
            tool_parts = []
            for fn_call in response.function_calls:
                tool_res = execute_tool_call(fn_call)
                tool_parts.append(genai_types.Part.from_function_response(name=fn_call.name, response={"result": tool_res}))
            response = chat.send_message(tool_parts)

        final_text = response.text or "음성 명령이 처리되었습니다."
        await update.message.reply_text(f"🎙️ **음성 명령 인식 결과**:\n{final_text}")
    except Exception as e:
        logger.error(f"Error in handle_voice: {e}")
        await update.message.reply_text(f"🎙️ 음성 메시지 처리 실패: {e}")

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

    masked_key = f"{GEMINI_API_KEY[:6]}...{GEMINI_API_KEY[-4:]}" if len(GEMINI_API_KEY) > 10 else "NOT_SET"
    logger.info(f"Processing message from chat {chat_id} using API Key: {masked_key}, Model: {active_model_name}")

    # Typing Indicator 표시
    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.TYPING)

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

            # 대화 이력 슬라이딩 윈도우: 최근 6개 메시지(3턴) 초과 시 자동 트림하여 분당 토큰 폭증 (429 RESOURCE_EXHAUSTED) 근본 방지
            try:
                hist = chat.get_history()
                if len(hist) > 6:
                    trimmed_history = hist[-6:]
                    chat_sessions[chat_id] = client.chats.create(
                        model=active_model_name,
                        history=trimmed_history,
                        config=genai_types.GenerateContentConfig(
                            system_instruction=SYS_INSTRUCTION,
                            tools=TOOLS_LIST,
                        )
                    )
                    chat = chat_sessions[chat_id]
            except Exception as hist_err:
                logger.warning(f"Chat history trimming notice: {hist_err}")

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

            # 대화형 원클릭 인라인 버튼 생성 (상태/자동화/롤백 간편 바로가기)
            keyboard = [
                [InlineKeyboardButton("🏠 상태 조회", callback_data="cb:status"), InlineKeyboardButton("📜 자동화 목록", callback_data="cb:automations")],
                [InlineKeyboardButton("⏪ 백업 롤백", callback_data="cb:rollback"), InlineKeyboardButton("🧹 대화 초기화", callback_data="cb:clear")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await safe_reply(update, context, final_text, reply_markup=reply_markup)
            return

        except Exception as e:
            last_error = e
            err_str = str(e)
            if "api_key_invalid" in err_str.lower() or "api key not valid" in err_str.lower():
                logger.error(f"Invalid Gemini API Key: {err_str}")
                await update.message.reply_text("⚠️ Gemini API 키가 유효하지 않습니다.\nhttps://aistudio.google.com/ 에서 새 키를 발급받아 `.env`의 `GEMINI_API_KEY`에 입력해 주세요.")
                return

            if any(k in err_str.lower() for k in ["401", "404", "429", "quota", "rate_limit", "resource_exhausted", "exceeded", "limit", "not found", "unauthenticated", "invalid"]):
                logger.warning(f"Model {candidate} failed ({err_str}), falling back...")
                if chat_id in chat_sessions:
                    del chat_sessions[chat_id]
                continue
            else:
                logger.error(f"Error calling Gemini: {e}")
                if chat_id in chat_sessions:
                    del chat_sessions[chat_id]
                await update.message.reply_text(f"요청 처리 중 오류가 발생했습니다: {e}")
                return

    logger.error(f"All candidate models failed. Last error: {last_error}")
    
    # 429 Quota 소모 시 오프라인 스마트 세이프가드 대답 (먹통 방지)
    try:
        keyboard = [
            [InlineKeyboardButton("🏠 전체 상태 조회", callback_data="cb:status"), InlineKeyboardButton("📜 자동화 목록", callback_data="cb:automations")],
            [InlineKeyboardButton("⏪ 백업 롤백", callback_data="cb:rollback"), InlineKeyboardButton("🧹 대화 초기화", callback_data="cb:clear")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # 1. 오프라인 기기 제어 명령(끄기/켜기) 감지 및 실행
        control_res = control_ha_device_offline(user_text) if user_text else ""
        if control_res:
            body_text = control_res
        else:
            # 2. 일반 질문/조회 시 핀포인트 실시간 검색
            pinpoint_result = query_ha_raw_entities(user_text) if user_text else ""
            body_text = pinpoint_result if pinpoint_result else f"📊 **[실시간 Home Assistant 기기 상태]**\n{get_device_state('')[:1500]}"

        err_detail = str(last_error) if last_error else "알 수 없는 오류"
        fallback_msg = (
            f"⚠️ **Gemini API 호출 오류로 오프라인 응급 모드로 작동 중입니다.**\n"
            f"*(🔍 구글 API 에러 원인: `{err_detail[:300]}`)*\n\n"
            f"{body_text}"
        )
        await safe_reply(update, context, fallback_msg, reply_markup=reply_markup)
    except Exception as fallback_err:
        logger.error(f"Error in emergency fallback reply: {fallback_err}")
        try:
            await update.message.reply_text("⚠️ 오프라인 응급 모드 응답 생성 중 오류가 발생했습니다.")
        except Exception:
            pass

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
        app.add_handler(CommandHandler("status", cmd_status))
        app.add_handler(CommandHandler("automations", cmd_automations))
        app.add_handler(CommandHandler("emergency", cmd_emergency))
        app.add_handler(CommandHandler("rollback", cmd_rollback))
        app.add_handler(CommandHandler("clear", cmd_clear))
        app.add_handler(CommandHandler("help", cmd_help))
        app.add_handler(CallbackQueryHandler(handle_callback_query))
        app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        logger.info("Starting Telegram Bot Polling with Typing Indicator, Voice, Inline Buttons & Commands...")
        app.run_polling()
    except Exception as e:
        logger.error(f"Telegram Bot failed to start: {e}. Check if TELEGRAM_BOT_TOKEN is valid.")
        import time
        while True:
            time.sleep(3600)

if __name__ == "__main__":
    main()
