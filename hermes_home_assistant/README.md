<p align="right">
  <strong>한국어</strong> · <a href="README.en.md">English</a>
</p>

# Hermes Agent for Home Assistant

Gemini 3.6 API 및 텔레그램 봇, Hermes Desktop과 연동하여 Home Assistant 설정을 스마트하게 제어하는 에이전트 서비스입니다.

## 주요 기능

- **Google Gemini 3.6 API 기반 스마트 에이전트**: 모바일 텔레그램 봇으로 기기 제어 및 상태 질의
- **YAML 안전 백업 & 자동 롤백 시스템**: `/config` 파일 조작 시 최신 백업본 자동 생성 및 오류 시 롤백
- **Hermes Desktop 통합 지원**: 포트 `2223` 전용 SSH/SFTP 및 MCP JSON-RPC 서버 제공
- **월별 변경 이력 관리**: 10개 파일 로테이션 및 12개월 월별 이력 보관

## 빠른 시작

1. `.env` 파일에 `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `AUTHORIZED_CHAT_IDS`, `SUPERVISOR_TOKEN`을 입력합니다.
2. `docker run` 또는 Home Assistant 애드온을 통해 에이전트를 구동합니다.
3. 텔레그램 봇에게 `"안녕하세요!"` 또는 `"거실 조명 켜줘"` 등의 메시지를 전송합니다.

