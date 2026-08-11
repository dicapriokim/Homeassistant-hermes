<p align="center">
  <h1 align="center">Hermes Agent for Home Assistant</h1>
</p>

<p align="center">
  Google Gemini 3.6 기반으로 Home Assistant 설정을 안전하게 제어하고,<br>
  PC(Hermes Desktop) 및 모바일(텔레그램 봇)을 통하여 스마트홈 기기 상태 확인 및 YAML 관리를 수행하는 스마트 에이전트입니다.
</p>

<p align="center">
  <a href="LICENSE"><img alt="License: Apache-2.0" src="https://img.shields.io/badge/license-Apache--2.0-green"></a>
  <img alt="Architecture: amd64 / aarch64" src="https://img.shields.io/badge/architecture-amd64%20%7C%20aarch64-blue">
  <img alt="Powered by: Gemini 3.6" src="https://img.shields.io/badge/LLM-Google%20Gemini%203.6-orange">
</p>

> [!NOTE]
> 본 프로젝트의 통합 개발 및 구축 계획서는 [`plan.md`](plan.md)에서 확인하실 수 있습니다.

---

## 🌟 주요 특징 (Features)

| 기능 | 주요 역할 | 핵심 기능 및 UX |
| :---: | :--- | :--- |
| **최신 GenAI SDK** | Google `google-genai` v1.x 전면 이관 | 최신 Gemini 3.6 Flash / Pro 모델 연동 및 안정적인 `GenerateContentConfig` 사양 준수 |
| **7단계 자동 폴백** | API 쿼터 초과(429) 및 오류 방지 | 429 / 503 에러 발생 시 Primary -> Secondary -> Tertiary 등 7단계 모델 자동 스위칭 |
| **스탠드얼론 REST API 폴백** | API 및 네트워크 장애 완벽 대비 | Gemini API 장애 시 의도별 핀포인트 추출 및 스탠드얼론 HA Core REST API 오프라인 직접 기기 제어 자동 전환 |
| **무제한 엔티티 수집** | Smart Home 전체 기기 상태 모니터링 | `get_device_state` 개수 제한 제거로 Home Assistant 전체 상태의 실시간 조회 및 인덱싱 |
| **도구 및 MCP 서버** | Multi-turn Function Calling & MCP | LLM Function Calling 및 자동화 수정/삭제(`ha_delete_automation`), REST API 백업 통합 MCP 서버 연동 |
| **모바일 & 알림** | 실시간 기기 상태 조회, 음성 제어 및 깔끔한 알림 | **텔레그램 봇** 연동 (`typing...` 지표, 텔레그램 URL 미리보기 배너 차단, 인라인 버튼 UI, 음성 메시지 제어, 실시간 이상 감지 알림 엔진) |
| **PC 데스크톱** | 대용량 YAML 수정, 디버깅, 구문 검사, 통합 관리 | **Hermes Desktop** 앱 및 SSH 원격 연결 (`/config` 직접 마운트 및 MCP 지원) |
| **안전 백업** | YAML 수정 전 자동 백업 및 10개 로테이션 | 타 앱 충돌 방지를 위한 `/config/hermes/backups/` 전용 경로 보관, 최신 10개 유지 |
| **월별 히스토리** | 라인 단위 Diff 누적 및 12개월(1년) 자동 로테이션 | `/config/hermes/backups/history/yaml_history_YYYY_MM.md`에 줄 번호 포함 변경 전/후 구문 기록 |
| **자동 롤백** | 구문 검사 실패 시 즉시 복구 | `ha core check` 연동을 통한 오작동 자동 롤백 시스템 |

---

## 🏗️ 시스템 아키텍처 (Architecture)

```mermaid
flowchart LR
    SubGraph1["모바일 (Mobile)"] -->|텔레그램 메세지| T["Telegram Bot Daemon"]
    SubGraph2["PC (Hermes Desktop)"] -->|SSH/SFTP (Port 2223)| S["HA /config 파일 I/O"]
    T --> G["Gemini 3.6 API (Google AI Studio)"]
    G -->|Function Calling| A["Home Assistant Core/Supervisor API"]
    G -->|안전 수정| B["/config/hermes/backups/ (백업 및 월별 히스토리)"]
```

---

## 🛡️ YAML 파일 안전 백업 & 월별 히스토리 규격

에이전트가 Home Assistant의 모든 YAML 파일(`configuration.yaml`, `automations.yaml`, `scripts.yaml`, 대시보드 YAML 등)을 수정할 때 아래 안전 수칙을 준수합니다:

1. **원본 자동 백업 (최근 10개 유지)**
   - 저장 경로: `/config/hermes/backups/[원본파일명]_[YYYYMMDD_HHMMSS].yaml`
   - 동일 파일 기준 10개 초과 시 오래된 백업부터 자동 삭제.
2. **월별 히스토리 기록 (최근 12개월 유지)**
   - 저장 경로: `/config/hermes/backups/history/yaml_history_[YYYY_MM].md`
   - 수정된 **줄 번호(Line Numbers)**, **변경 전 구문(Before Change)**, **변경 후 구문(After Change)**을 마크다운 코드 블록으로 기록.
   - 12개월(1년)이 지난 월별 파일은 자동 삭제.
3. **구문 검사 & 롤백**
   - 수정 직후 `ha core check` 검증 실패 시 최신 백업본으로 **자동 원상 복구(Rollback)**.

---

## 🚀 빠른 시작 가이드 (Quick Start)

### 1. 환경 변수 설정
본 에이전트는 `options.json` 또는 환경 변수를 통해 인증 정보를 관리합니다:
- `GEMINI_API_KEY`: Google AI Studio에서 발급받은 Gemini API 키
- `TELEGRAM_BOT_TOKEN`: Telegram BotFather를 통해 생성한 봇 토큰
- `AUTHORIZED_CHAT_IDS`: 인증된 텔레그램 사용자 Chat ID 목록

### 2. 구동 (Docker / Proxmox LXC)
Proxmox 독립 LXC 또는 도커 환경에서 컨테이너를 구동합니다:
```bash
docker run -d \
  --name hermes-agent \
  -e GEMINI_API_KEY="your-gemini-api-key" \
  -e TELEGRAM_BOT_TOKEN="your-telegram-bot-token" \
  -p 2223:22 \   # SSH 접속용 포트 (기본 예시: 2223, 필요 시 다른 포트로 변경 가능)
  -v /usr/share/hassio/homeassistant:/config \
  ghcr.io/dicapriokim/homeassistant-hermes:latest
```

> [!TIP]
> 포트 번호 `2223`은 튜토리얼용 기본 예시 포트입니다. 외부 인터넷망에 노출할 경우 보안을 위해 사용자 임의의 커스텀 포트로 변경하거나 VPN(예: Tailscale, WireGuard)을 사용하는 것을 강력히 권장합니다.

---

## 📄 라이선스 (License)

본 프로젝트는 [Apache License 2.0](LICENSE) 라이선스를 따릅니다.
