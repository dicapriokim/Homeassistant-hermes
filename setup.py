#!/usr/bin/env python3
"""
Hermes Agent for Home Assistant - .env 설정 대화형 마법사 (setup.py)
참고: D:\\Antigravity\\Workspace\\Mail-Automator_gemma4\\setup.js 구조 준수
"""

import os
import sys
import re

ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")

# ANSI 컬러 코드
RESET = "\033[0m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
RED = "\033[31m"
CYAN = "\033[36m"

DEFAULT_ENV_TEMPLATE = """# ==========================================
# Hermes Agent for Home Assistant 환경 설정 (.env)
# ==========================================

# 1. Google Gemini API 키 (Google AI Studio에서 발급)
GEMINI_API_KEY=""

# 2. 텔레그램 봇 토큰 (BotFather 발급)
TELEGRAM_BOT_TOKEN=""

# 3. 텔레그램 허용 Chat ID (숫자, 쉼표 또는 [123, 456] 포맷)
AUTHORIZED_CHAT_IDS=""

# 4. Home Assistant 연동 설정 (장기 사용 토큰 & URL)
SUPERVISOR_TOKEN=""
HASS_URL="http://homeassistant.local:8123"
"""

def clear_console():
    os.system('cls' if os.name == 'nt' else 'clear')

def mask_value(val):
    if not val or not val.strip():
        return "(미설정)"
    val = val.strip().strip('"').strip("'")
    if len(val) <= 6:
        return "******"
    return f"{val[:3]}******{val[-3:]}"

def get_sensitive_status(val):
    if not val or not val.strip():
        return f"{RED}⚠️ 미설정 (입력 필요){RESET}"
    return f"{GREEN}🔒 설정 완료 ({mask_value(val)}){RESET}"

def read_env(silent=False):
    if not silent:
        print("[진행 내용] 기존 .env 파일 분석 시작...")
    config = {}
    lines = []
    
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
    else:
        if not silent:
            print("[진행 내용] 기존 .env 파일이 존재하지 않아 신규 템플릿으로 구성을 준비합니다.")
        lines = DEFAULT_ENV_TEMPLATE.splitlines(keepends=True)

    for line in lines:
        trimmed = line.strip()
        if trimmed and not trimmed.startswith("#") and "=" in trimmed:
            parts = trimmed.split("=", 1)
            key = parts[0].strip()
            val = parts[1].strip().strip('"').strip("'")
            config[key] = val

    return config, lines

def write_env(updated_config):
    config, lines = read_env(silent=True)
    final_config = {**config, **updated_config}
    
    output_lines = []
    keys_written = set()

    for line in lines:
        trimmed = line.strip()
        if trimmed and not trimmed.startswith("#") and "=" in trimmed:
            key = trimmed.split("=", 1)[0].strip()
            if key in final_config:
                output_lines.append(f'{key}="{final_config[key]}"\n')
                keys_written.add(key)
                continue
        output_lines.append(line)

    for key, val in final_config.items():
        if key not in keys_written:
            output_lines.append(f'{key}="{val}"\n')

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(output_lines)

def show_help_menu():
    while True:
        clear_console()
        print("==================================================")
        print("   🔑 주요 연동 토큰/비밀키 발급처 가이드 도움말")
        print("==================================================")
        print("[1] Google Gemini API Key 발급처 (GEMINI_API_KEY)")
        print("[2] 텔레그램 Bot Token 및 Chat ID 발급/확인처")
        print("[3] Home Assistant 장기 사용 토큰 (SUPERVISOR_TOKEN)")
        print("[0] 메인 메뉴로 돌아가기")
        print("==================================================")

        select = input("조회할 항목을 선택하세요: ").strip()
        if select in ["0", ""]:
            break

        clear_console()
        if select == "1":
            print("--------------------------------------------------")
            print("📌 Google Gemini API Key (GEMINI_API_KEY)")
            print("--------------------------------------------------")
            print("1. 발급처: Google AI Studio (https://aistudio.google.com/) 접속")
            print("2. [Get API key] 버튼 클릭 후 신규 API Key 생성")
            print("3. 생성된 'AIzaSy...' 문자열을 입력합니다.")
        elif select == "2":
            print("--------------------------------------------------")
            print("📌 Telegram Bot Token 및 Chat ID")
            print("--------------------------------------------------")
            print("1. Bot Token 발급: 텔레그램에서 @BotFather 검색 -> /newbot 명령 실행 후 받은 HTTP API Token")
            print("2. Chat ID 확인: 텔레그램에서 @userinfobot 검색 -> /start 실행 시 나오는 본인 Id 숫자 (예: 123456789)")
        elif select == "3":
            print("--------------------------------------------------")
            print("📌 Home Assistant Long-Lived Token (SUPERVISOR_TOKEN)")
            print("--------------------------------------------------")
            print("1. Home Assistant 웹 GUI 대시보드 로그인")
            print("2. 좌측 하단 사용자 프로필 아이콘 클릭 -> 페이지 맨 아래로 스크롤")
            print("3. [장기 사용 토큰] -> [토큰 만들기] 클릭 후 생성된 긴 JWT 문자열 복사")
        else:
            print("⚠️ 올바른 번호를 선택하세요.")
        
        input("\n도움말 목록으로 돌아가려면 엔터(Enter) 키를 누르세요...")

def view_current_settings(config):
    clear_console()
    print("=========================================")
    print("       🔍 현재 적용된 환경 설정 상태")
    print("=========================================")
    print(f"[Gemini]   GEMINI_API_KEY       : {get_sensitive_status(config.get('GEMINI_API_KEY'))}")
    print("-----------------------------------------")
    print(f"[Telegram] TELEGRAM_BOT_TOKEN   : {get_sensitive_status(config.get('TELEGRAM_BOT_TOKEN'))}")
    print(f"[Telegram] AUTHORIZED_CHAT_IDS  : {get_sensitive_status(config.get('AUTHORIZED_CHAT_IDS'))}")
    print("-----------------------------------------")
    print(f"[HA]       SUPERVISOR_TOKEN     : {get_sensitive_status(config.get('SUPERVISOR_TOKEN'))}")
    print(f"[HA]       HASS_URL             : {config.get('HASS_URL', 'http://homeassistant.local:8123')}")
    print("=========================================")
    input("메인 메뉴로 돌아가려면 엔터(Enter) 키를 누르세요...")

def run_wizard_mode(config):
    clear_console()
    print("==================================================")
    print("   🚀 Hermes Agent 전체 설정 마법사")
    print("   Step 1부터 Step 4까지 순차적으로 진행합니다.")
    print("   (기존값을 유지하시려면 그냥 엔터(Enter)를 누르세요)")
    print("==================================================")
    input("시작하시려면 엔터(Enter) 키를 누르세요...")

    # Step 1: Gemini API Key
    clear_console()
    print("--- [Step 1] Google Gemini API Key ---")
    val1 = input(f"🔑 Gemini API Key 입력 (현재: {mask_value(config.get('GEMINI_API_KEY'))}): ").strip()
    if val1:
        config["GEMINI_API_KEY"] = val1

    # Step 2: Telegram Bot Token
    clear_console()
    print("--- [Step 2] Telegram Bot Token ---")
    val2 = input(f"🔑 Telegram Bot Token 입력 (현재: {mask_value(config.get('TELEGRAM_BOT_TOKEN'))}): ").strip()
    if val2:
        config["TELEGRAM_BOT_TOKEN"] = val2

    # Step 3: Telegram Chat ID
    clear_console()
    print("--- [Step 3] Telegram Chat ID ---")
    val3 = input(f"🔑 Telegram Chat ID 입력 (현재: {mask_value(config.get('AUTHORIZED_CHAT_IDS'))}, 예: 123456789): ").strip()
    if val3:
        config["AUTHORIZED_CHAT_IDS"] = val3

    # Step 4: Home Assistant Token & URL
    clear_console()
    print("--- [Step 4] Home Assistant Token & URL ---")
    val4 = input(f"🔑 HA Long-lived Token 입력 (현재: {mask_value(config.get('SUPERVISOR_TOKEN'))}): ").strip()
    if val4:
        config["SUPERVISOR_TOKEN"] = val4

    url_val = input(f"🌐 HA URL 주소 입력 (현재: {config.get('HASS_URL', 'http://homeassistant.local:8123')}): ").strip()
    if url_val:
        config["HASS_URL"] = url_val

    clear_console()
    print(f"{GREEN}=================================================={RESET}")
    print(f"{GREEN}🎉 전체 설정 마법사 완료! 메인 메뉴에서 저장(0번)을 선택하세요.{RESET}")
    print(f"{GREEN}=================================================={RESET}")
    input("메인 메뉴로 돌아가려면 엔터(Enter) 키를 누르세요...")

def main():
    config, _ = read_env()
    
    while True:
        missing_keys = []
        if not config.get("GEMINI_API_KEY"): missing_keys.append("GEMINI_API_KEY")
        if not config.get("TELEGRAM_BOT_TOKEN"): missing_keys.append("TELEGRAM_BOT_TOKEN")
        if not config.get("AUTHORIZED_CHAT_IDS"): missing_keys.append("AUTHORIZED_CHAT_IDS")
        if not config.get("SUPERVISOR_TOKEN"): missing_keys.append("SUPERVISOR_TOKEN")

        clear_console()
        print("=========================================")
        print("   Hermes Agent v1.0 대화형 설정 메뉴")
        print("=========================================")
        if missing_keys:
            print(f"{YELLOW}💡 필수 정보를 입력해주세요 (.env 직접 편집도 가능){RESET}")
            print(f"{CYAN}     ({', '.join(missing_keys)}){RESET}")
            print("-----------------------------------------")
        else:
            print(f"{GREEN}✅ 모든 필수 보안 키 및 설정이 완료된 상태입니다.{RESET}")
            print("-----------------------------------------")

        print(f"{CYAN}[A] 🚀 전체 설정 마법사 (Wizard Mode){RESET}")
        print("-----------------------------------------")
        print("[1] 🔑 Gemini API Key 설정")
        print("[2] 🔑 Telegram Bot Token 및 Chat ID 설정")
        print("[3] 🔑 Home Assistant Token 및 URL 설정")
        print("[4] 📖 키 발급처 도움말 가이드")
        print("[5] 🔍 현재 전체 설정 상태 조회 (마스킹 보기)")
        print("-----------------------------------------")
        print(f"{GREEN}[0] 💾 저장 및 종료 (Save & Exit){RESET}")
        print("=========================================")

        select = input("메뉴 번호를 선택하세요: ").strip().upper()

        if select == "A":
            run_wizard_mode(config)
        elif select == "1":
            clear_console()
            val = input(f"🔑 Gemini API Key 입력 (현재: {mask_value(config.get('GEMINI_API_KEY'))}): ").strip()
            if val: config["GEMINI_API_KEY"] = val
        elif select == "2":
            clear_console()
            tok = input(f"🔑 Telegram Bot Token (현재: {mask_value(config.get('TELEGRAM_BOT_TOKEN'))}): ").strip()
            if tok: config["TELEGRAM_BOT_TOKEN"] = tok
            cid = input(f"🔑 Telegram Chat ID (현재: {mask_value(config.get('AUTHORIZED_CHAT_IDS'))}): ").strip()
            if cid: config["AUTHORIZED_CHAT_IDS"] = cid
        elif select == "3":
            clear_console()
            tok = input(f"🔑 HA Long-lived Token (현재: {mask_value(config.get('SUPERVISOR_TOKEN'))}): ").strip()
            if tok: config["SUPERVISOR_TOKEN"] = tok
            url = input(f"🌐 HA URL (현재: {config.get('HASS_URL', 'http://homeassistant.local:8123')}): ").strip()
            if url: config["HASS_URL"] = url
        elif select == "4":
            show_help_menu()
        elif select == "5":
            view_current_settings(config)
        elif select == "0":
            confirm = input("\n변경 사항을 저장하고 종료하시겠습니까? (Y/N): ").strip().lower()
            if confirm == "y":
                write_env(config)
                print(f"{GREEN}[진행 내용] 설정 변경 사항이 .env에 성공적으로 저장되었습니다.{RESET}")
            else:
                print("[진행 내용] 변경 사항이 저장되지 않고 종료되었습니다.")
            break
        else:
            print("⚠️ 잘못된 입력값입니다.")
            input("엔터를 누르면 계속합니다...")

if __name__ == "__main__":
    main()
