#!/usr/bin/env python3
import os
import json
import time
import logging
import requests
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("telegram_notifier")

# 환경변수 및 Config 읽기
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

SUPERVISOR_TOKEN = _clean_token(_read_s6_env("SUPERVISOR_TOKEN")) or _clean_token(os.getenv("SUPERVISOR_TOKEN"))
HASS_URL = os.getenv("HASS_URL", "http://supervisor/core").rstrip("/")
TELEGRAM_BOT_TOKEN = _clean_token(_read_s6_env("TELEGRAM_BOT_TOKEN")) or _clean_token(os.getenv("TELEGRAM_BOT_TOKEN"))
AUTHORIZED_CHAT_IDS_RAW = os.getenv("AUTHORIZED_CHAT_IDS", "")
AUTHORIZED_CHAT_IDS = [int(x.strip()) for x in AUTHORIZED_CHAT_IDS_RAW.split(",") if x.strip().lstrip('-').isdigit()]

# HA API 호출
def get_all_states():
    if not SUPERVISOR_TOKEN or not HASS_URL:
        return []
    url = f"{HASS_URL}/api/states"
    headers = {
        "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
        "Content-Type": "application/json"
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.error(f"Error fetching HA states: {e}")
    return []

# 텔레그램 푸시 메시지 전송
def send_telegram_alert(text: str, reply_markup: dict = None):
    if not TELEGRAM_BOT_TOKEN or not AUTHORIZED_CHAT_IDS:
        return
    for chat_id in AUTHORIZED_CHAT_IDS:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            logger.error(f"Failed to send telegram push to {chat_id}: {e}")

# 알림 중복 방지 (쿨다운 1시간)
alert_history = {}

def check_anomalies():
    states = get_all_states()
    if not states:
        return

    now = time.time()
    
    # 1. 창문 열림 중 냉난방/공기청정기 가동 검사
    windows_open = []
    active_climates = []
    
    for s in states:
        entity_id = s.get("entity_id", "")
        state_val = s.get("state", "").lower()
        friendly_name = s.get("attributes", {}).get("friendly_name", entity_id)

        # 창문/문 센서
        if ("window" in entity_id or "door" in entity_id or "창문" in friendly_name) and state_val in ["on", "open"]:
            windows_open.append(friendly_name)

        # 공기청정기/에어컨/가습기
        if entity_id.startswith(("climate.", "fan.", "humidifier.")) and state_val in ["on", "cool", "heat", "auto"]:
            active_climates.append(friendly_name)

        # 2. 온도 이상 검사
        if "temperature" in entity_id and state_val.replace('.', '', 1).isdigit():
            temp = float(state_val)
            if temp >= 32.0 or temp <= 5.0:
                key = f"temp_{entity_id}"
                if now - alert_history.get(key, 0) > 3600:
                    alert_history[key] = now
                    send_telegram_alert(f"⚠️ **실내 온·습도 이상 경고**\n\n[{friendly_name}] 현재 온도가 `{temp}°C`로 이상 범위입니다! 확인해 주세요.")

        # 3. 배터리 저하 검사
        if "battery" in entity_id and state_val.isdigit():
            bat = int(state_val)
            if bat <= 10:
                key = f"bat_{entity_id}"
                if now - alert_history.get(key, 0) > 86400:
                    alert_history[key] = now
                    send_telegram_alert(f"🪫 **기기 배터리 교체 알림**\n\n[{friendly_name}] 잔량이 `{bat}%` 남았습니다. 배터리를 교체해 주세요.")

    # 창문 열림 + 기기 작동 경고
    if windows_open and active_climates:
        key = "window_climate_conflict"
        if now - alert_history.get(key, 0) > 1800: # 30분 쿨다운
            alert_history[key] = now
            msg = (
                f"🪟 **환기 중 에어컨/공기청정기 작동 경고**\n\n"
                f"• 열린 창문/문: {', '.join(windows_open)}\n"
                f"• 작동 중인 기기: {', '.join(active_climates)}\n\n"
                f"에너지 절약을 위해 창문을 닫거나 기기를 꺼주세요!"
            )
            send_telegram_alert(msg)

def main():
    logger.info("Starting Home Assistant Smart Telegram Notifier Daemon...")
    while True:
        try:
            check_anomalies()
        except Exception as e:
            logger.error(f"Error in anomaly check loop: {e}")
        time.sleep(60) # 1분마다 점검

if __name__ == "__main__":
    main()
