# **Gemini 기반 Home Assistant 스마트 에이전트 개발 통합 계획서**

본 문서는 Proxmox 독립 도커 환경 및 Hermes Agent / Hermes Desktop 인프라 기반으로 Google Gemini API를 연동하여 Home Assistant(HA)의 YAML 설정 관리, 구문 검사, 리로드, 안전 백업/롤백 및 실시간 기기 상태 조회·제어를 수행하는 차세대 AI 에이전트 통합 구축 계획서입니다.

---

## **1. 프로젝트 개요**

> * **프로젝트명:** HA 에이전트 자동화 (Gemini Powered Hermes Agent for Home Assistant)
> * **개발 및 운용 전략:** Proxmox 도커 환경에 Hermes Agent 백엔드를 구축하고, PC 데스크톱 앱(Hermes Desktop), 텔레그램 봇 및 HA 연동 망을 구성하여 프론트엔드 직접 구축 비용 및 개발 시간 절감
> * **핵심 기반 모델 & 플랫폼:** Google Gemini API (Google AI Studio - Gemini 3.6 Flash / Pro) + Hermes Agent / Hermes Desktop + Telegram Bot
> * **주요 목적:** Hermes Agent의 백엔드 하네스(HA 연동, MCP, 세션/기억 관리)와 Gemini의 대용량 컨텍스트 창 및 저비용/고성능 API 혜택을 결합하여 안전하고 가용성 높은 스마트홈 제어 자동화 구현

---

## **2. 시스템 아키텍처 및 역할 분담**

### **가. 환경별 역할 분담 전략 (UX/UI 관점)**

| 구분 | 모바일 (스마트폰/태블릿) | PC 브라우저 / 데스크톱 (PC) |
| :---: | :--- | :--- |
| **주요 역할** | 실시간 기기 상태 조회 및 자연어 가벼운 제어 | 대용량 YAML 수정, 디버깅, 구문 검사, Hermes Desktop 통합 제어 |
| **사용자 경험(UX)** | 텔레그램 봇 / HA Assist 대화형 채팅 UI | Hermes Desktop 앱 / SSH 원격 접속 / Diff 비교 뷰어 |
| **핵심 연동 기능** | HA REST API / WebSocket `get_state`, `call_service` | Hermes MCP Server, `/config` 파일 I/O, `ha core check`, YAML 파싱 |

### **나. 시스템 격리 및 하이브리드 백엔드 구조**
> * **Proxmox 독립 도커:** Proxmox LXC/도커 내에 Hermes Agent 백엔드를 세팅하고, LLM Provider를 Google AI Studio (Gemini 3.6)로 지정하여 HA 메인 프로세스와 자원을 완전 격리.
> * **Hermes Desktop & HA 연동:** PC에서는 Hermes Desktop 앱으로 Hermes Agent 백엔드에 접속하고, Hermes Agent는 장기 액세스 토큰(Long-lived Token)과 SSH/MCP Gateway를 통해 HA `/config` 제어 및 엔티티 관리를 통합 수행.
> * **HA 애드온 호환성:** 추후 HA 공식 애드온 규격(`config.yaml`, `Dockerfile`, `s6-overlay`)으로 즉시 패키징 가능하도록 디렉토리 및 서비스 구조 유지.

---

## **3. 🛡️ [핵심] YAML 파일 안전 백업, 월별 히스토리 및 롤백 시스템**

에이전트가 Home Assistant의 모든 YAML 파일(`configuration.yaml`, `automations.yaml`, `scripts.yaml`, 대시보드 YAML 등)을 수정하기 전, 타 앱과의 충돌을 방지하는 **Hermes 전용 저장소**를 활용하여 백업 및 히스토리 관리 절차를 반드시 자동 실행합니다.

### **가. 원본 파일 사전 자동 백업 (최근 10개 유지)**
1. **수정 직전 원본 백업:**
   - 파일 수정 실행 바로 전, 원본 파일을 `/config/hermes/backups/` 디렉토리에 복사하여 저장.
   - 백업 파일명 포맷: `[원본파일명]_[YYYYMMDD_HHMMSS].yaml` (예: `automations_20260808_105000.yaml`)
2. **최신 10개 파일 자동 로테이션:**
   - 동일 원본 파일명 기준 백업 파일이 **10개를 초과할 경우 가장 오래된 백업부터 자동 삭제**.

### **나. 월별 YAML 변경 히스토리 및 정밀 Diff 누적 (최근 12개월 유지)**
1. **월별 히스토리 기록:**
   - 저장 경로: `/config/hermes/backups/history/`
   - 월별 파일명 포맷: `yaml_history_[YYYY_MM].md` (예: `yaml_history_2026_08.md`)
2. **라인 단위 정밀 Diff 항목:**
   - 변경 시각 (Timestamp) 및 파일 경로
   - 원인 (Root Cause) 및 수정 내용 (Fix Applied)
   - **변경 전 구문 (Before Change):** 수정된 시작~끝 줄 번호(Lines) 및 변경 전 코드
   - **변경 후 구문 (After Change):** 수정된 시작~끝 줄 번호(Lines) 및 변경 후 코드
   - 기대 효과 (Expected Outcome)
3. **12개월 로테이션 규칙:**
   - `yaml_history_*.md` 파일 목록 중 **12개를 초과하는 1년이 지난 이전 월별 히스토리 파일은 자동 삭제**.

### **다. 구문 오류 검사 및 즉시 롤백**
- 파일 수정 직후 `ha core check` (Supervisor API)를 자동 실행.
- 구문 검사 실패(INVALID) 또는 사용자 복구 요청 시, 가장 최신의 백업 파일(`/config/hermes/backups/`)을 덮어씌워 **즉시 원상 복구(Rollback)**.

---

## **4. ⚙️ Home Assistant YAML 및 코드 작성 원칙**

1. **엔티티 ID 및 기존 논리 보존:**
   - 기존 구동 중인 Entity ID, 상태값, 자동화 논리 구조, YAML 계층 구조를 임의로 변경하거나 삭제하지 않음.
   - 사용자가 명시적으로 요청하지 않은 코드 최적화나 리팩토링 금지.
2. **가독성 및 표준 상태 검사 우선:**
   - 복잡한 Jinja2 템플릿 연산 대신 Standard State Verification(표준 상태 검사)을 우선 적용.
3. **수정 설명 표준 서식 준수 (Structured Output):**
   - **Root Cause (원인):** 문제 발생 원인 설명
   - **Fix Applied (수정 내용):** 변경된 코드 및 가동 위치 설명
   - **Expected Outcome (기대 효과):** 수정 후 동작 및 시스템 영향
4. **코드 출력 최소화:**
   - 전체 코드를 덤프하지 않고, 변경된 해당 줄 번호 및 정밀한 부분 코드 블록만 제시.

---

## **5. 🚀 단계별 개발 및 구축 로드맵**

* **[1단계] Proxmox LXC/도커 내 Hermes Agent 구축 및 Gemini API 연동**
  - Proxmox LXC 컨테이너(Debian/Ubuntu, Nesting 활성화) 세팅 및 Docker 설치
  - LLM Provider를 Google AI Studio (Gemini 3.6)로 지정하고 HA Long-lived Token 연동
* **[2단계] 백엔드(Gemini Agent) 파이썬 데몬 및 HA API 연동**
  - `codex-cli` 제거 후 `google-generativeai` 기반 `gemini_agent.py` 구축
  - HA 상태 조회(`get_device_state`) 및 서비스 제어(`call_ha_service`) Tool 연동
* **[3단계] 텔레그램 봇 모듈 개발 및 문서화**
  - 텔레그램 봇 Polling 데몬 및 Chat ID 인증 구축
  - `사용자 설명서.md`에 초보자용 봇 생성/인증 절차 수록
* **[4단계] PC 환경 (Hermes Desktop) 연동 및 연동 가이드 작성**
  - SSH(포트 2223) 원격 접속 및 Samba 마운트 가이드 작성
  - MCP 서버 호환 인터페이스 구성
* **[5단계] YAML 안전 자동 백업(10개), 월별 히스토리(12개월) 및 롤백 모듈 연동**
  - `/config/hermes/backups/` 내 10개 원본 백업/로테이션 구현
  - `/config/hermes/backups/history/` 내 줄 번호 포함 월별 Diff 히스토리 누적/12개월 로테이션 구현
* **[6단계] 트러블슈팅 및 HA 애드온 패키징 릴리즈 준비**
  - `troubleshooting_history.md` 누적 이력 관리 및 비밀 키 격리 준수
  - HA 공식 애드온 구조 검증 및 워크스루 갱신

---

## **6. 💬 프롬프트 및 사용 예시 (Examples)**

### 예시 1: automations.yaml 수정 및 자동 백업/히스토리 기록
> **사용자 입력:**
> `거실 조명 자동화 문법 에러 수정해 줘.`
>
> **에이전트 동작 순서:**
> 1. `/config/hermes/backups/automations_20260808_110500.yaml` 백업 생성 (10개 초과 시 최선 순 삭제).
> 2. `automations.yaml` 수정 적용.
> 3. `/config/hermes/backups/history/yaml_history_2026_08.md` 파일에 변경 시각, 줄 번호(Lines 34-38), 변경 전/후 코드 블록 누적 기록. (12개월 초과 시 이전 파일 삭제)
> 4. `ha core check` 구문 검사 실행.
> 5. 결과 서식 출력:
>    - **Root Cause:** 34번째 줄 `condition` 블록의 들여쓰기 오류.
>    - **Fix Applied:** `automations.yaml` 34~38번째 줄 재정렬.
>    - **Expected Outcome:** HA 재시작 시 오류 없이 정상 로드.

### 예시 2: 문제가 발생해 직전 상태로 롤백 요청 시
> **사용자 입력:**
> `방금 수정한 ui-lovelace.yaml 배치가 깨졌어. 직전 백업본으로 롤백해 줘.`
>
> **에이전트 동작 순서:**
> 1. `/config/hermes/backups/`에서 가장 최신 `ui-lovelace_[TIMESTAMP].yaml` 탐색.
> 2. 원본 `ui-lovelace.yaml` 위치에 덮어쓰기 롤백 수행.
> 3. 결과 보고: 가장 최신 백업본으로 복원 완료 안내.
