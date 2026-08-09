<p align="right">
  <strong>한국어</strong> · <a href="DOCS.en.md">English</a>
</p>

# Hermes Agent for Home Assistant 사용 설명서

본 문서는 Home Assistant 사용자가 Hermes Agent를 설치하고, Gemini 3.6 API 및 텔레그램 봇, Hermes Desktop과 연동하여 안전하게 스마트홈 기기 제어 및 YAML 설정을 관리하는 가이드를 제공합니다.

## 주요 기능

- **Google Gemini 3.6 API 기반 스마트 에이전트**: 텔레그램 봇을 통한 자연어 질의 및 기기 상태 조작
- **YAML 안전 백업 & 자동 롤백**: `/config` 내 YAML 수정 시 `/config/hermes/backups/`에 최신 10개 자동 로테이션 백업 및 구문 에러 시 롤백
- **월별 히스토리 및 12개월 관리**: `/config/hermes/backups/history/`에 월별 마크다운 변경 기록 보관 및 1년 자동 삭제
- **Hermes Desktop 통합 제어**: 포트 `2223` 전용 SSH/SFTP 제공 및 MCP(ha_mcp_server.py) 통신 지원

## 빠른 시작

1. 4가지 핵심 인증키(`GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `AUTHORIZED_CHAT_IDS`, `SUPERVISOR_TOKEN`)를 준비합니다.
2. `python3 setup.py` 마법사를 실행하거나 `.env` 파일에 직접 설정값을 입력합니다.
3. `docker run` 또는 Home Assistant App 스토어를 통해 에이전트를 구동합니다.
4. 텔레그램 봇으로 메시지를 보내 정상 동작을 검증합니다.

