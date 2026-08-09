# Gemini 기반 Home Assistant 스마트 에이전트 사용자 설명서

본 문서는 Proxmox LXC 환경 구축부터 텔레그램 봇 생성, 헤르메스 데스크탑 연동까지 차세대 스마트홈 에이전트를 구성하기 위한 모든 단계별 가이드를 제공합니다.

---

## 1. Proxmox LXC 및 도커 환경 설계 및 구축 가이드

본 개발은 추후 Home Assistant(HA) 애드온(App)으로의 전환 가능성을 열어두고 진행되므로, 가벼우면서도 도커 컨테이너를 완벽히 지원하는 Debian/Ubuntu 기반의 LXC(Linux Container) 인스턴스를 설계합니다.

### 1.1 LXC 설계 스펙 권장사항
- **OS Template**: Debian 12 (Bookworm) 또는 Ubuntu 22.04 LTS (안정성 및 도커 호환성 확보)
- **CPU**: 2 Cores 이상 (Gemini API 통신 및 에이전트 백엔드 처리에 충분)
- **RAM**: 2GB 이상 (추후 HA 애드온 전환 시나리오 대비 여유 자원 할당)
- **Storage**: 10GB 이상
- **Network**: HA와 통신할 수 있는 동일 내부망(Subnet) 권장
- **Features (중요)**: 도커를 LXC 내에서 실행하기 위해 반드시 **Nesting** 및 **keyctl** 기능을 활성화해야 합니다.

---

### 1.2 LXC 생성 및 도커 세팅 단계
1. **Proxmox 웹 GUI 접속**: 우측 상단의 `Create CT` 버튼을 클릭합니다.
2. **General (일반)**: 컨테이너 ID와 Hostname(예: `ha-gemini-agent`)을 입력하고 비밀번호를 설정합니다. **Unprivileged container** 체크를 유지합니다.
3. **Template (템플릿)**: 미리 다운로드해 둔 Debian 12 또는 Ubuntu 22.04 템플릿을 선택합니다.
4. **Disks, CPU, Memory**: 위의 권장 스펙에 맞춰 할당합니다.
5. **Network**: 정적 IP(Static IP)를 할당하여 추후 HA나 Hermes Desktop 통신 시 IP가 변경되지 않도록 합니다.
6. **Confirm (확인)**: 생성 완료 후 **아직 시작(Start)하지 마십시오.**
7. **Nesting 활성화 및 AppArmor 설정 (중요)**: 
   - 생성된 컨테이너 선택 ➔ `Options` ➔ `Features` 더블클릭 ➔ `keyctl` 및 `nesting` 체크 후 `OK`.
   - Proxmox 호스트 쉘에서 AppArmor 권한 해제 명령어 실행 (`echo "lxc.apparmor.profile: unconfined" >> /etc/pve/lxc/<CT_ID>.conf`)
   > [!TIP]
   > 💡 상세한 AppArmor 차단 해제 방법은 문서 맨 아래 [5.2 Proxmox LXC 권한 에러 해결](#52-proxmox-lxc-apparmor-sysctl-권한-에러-해결)을 참고하세요.

8. **컨테이너 내부 쉘 접속 및 도커 설치**:
   - Proxmox 노드 쉘에서 `pct start <CT_ID>` 및 `pct enter <CT_ID>`로 컨테이너 진입 후 실행:
     ```bash
     apt-get update && apt-get upgrade -y
     apt-get install -y curl
     curl -fsSL https://get.docker.com -o get-docker.sh
     sh get-docker.sh
     ```
9. **설치 확인**: `docker --version` 및 `docker ps` 명령어로 정상 동작을 확인합니다.

---

### 1.3 PC 개발 소스(`D:\Antigravity\hermes`) LXC로 전송 가이드
PC의 개발 폴더를 LXC의 리눅스 표준 앱 경로인 `/opt/Homeassistant-hermes`로 전송합니다.

#### 📌 [사전 필수] LXC SSH Root 로그인 및 비밀번호 인증 허용 설정
LXC 콘솔에서 아래 명령어로 SSH 접속을 허용합니다:
```bash
sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
sed -i 's/PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
sed -i 's/#PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
sed -i 's/PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
systemctl restart ssh
```

#### 📌 LXC로 전송 실행
- **방법 A: Windows PowerShell `scp` 명령어 전송 (권장)**:
  PC PowerShell에서 실행 (`-F NUL`을 추가하여 Windows SSH Config 간섭 방지):
  ```powershell
  scp -F NUL -r D:\Antigravity\hermes root@<LXC_HOST_IP>:/opt/Homeassistant-hermes
  ```
- **방법 B: WinSCP / FileZilla GUI 프로그램 사용**:
  `Host: <LXC_HOST_IP>`, `Port: 22`, `User: root`로 접속 후 `/opt/Homeassistant-hermes` 경로로 드래그 전송.
- **방법 C: Proxmox 호스트 `pct push` 명령어 활용**:
  ```bash
  pct push <CT_ID> D:\Antigravity\hermes /opt/Homeassistant-hermes
  ```
> [!NOTE]
> 💡 SCP 전송 시 폴더 이중 생성 방지 노하우는 [5.5 SCP 중복 폴더 자동 정리 노하우](#55-scp-전송-시-중복-폴더-자동-정리-노하우)를 참고하세요.

---

## 2. 필수 인증키 4가지 발급 및 준비 가이드

Hermes Agent 구동을 위해 필요한 **4가지 핵심 인증키/정보**의 발급 가이드입니다.

### 2.1 Google Gemini API Key 발급 (`GEMINI_API_KEY`)
1. [Google AI Studio 공식 웹사이트](https://aistudio.google.com/) 접속 ➔ 구글 계정 로그인.
2. 화면 상단 **[Get API key]** ➔ **[Create API key]** 클릭.
3. 생성된 `AIzaSy...` 문자열 복사.

### 2.2 텔레그램 봇 생성 (`TELEGRAM_BOT_TOKEN`)
1. 텔레그램 앱 검색창에서 `@BotFather` 검색 ➔ 대화 시작 (`/start`).
2. `/newbot` 명령 전송 ➔ 봇 이름(Name) 및 유저네임(Username, `bot`으로 끝남) 입력.
3. 생성된 **HTTP API Token** (예: `123456789:ABCdef...`) 복사.

### 2.3 사용자 Chat ID 확인 (`AUTHORIZED_CHAT_IDS`)
1. 텔레그램 검색창에서 `@userinfobot` 또는 `@RawDataBot` 검색 ➔ `/start`.
2. 메시지의 `Id` 필드 숫자(예: `123456789`) 복사.

### 2.4 Home Assistant 장기 사용 토큰 & URL (`SUPERVISOR_TOKEN` / `HASS_TOKEN`, `HASS_URL`)
1. **`HASS_URL`**: Home Assistant 내부 접속 주소 (예: `http://192.168.x.x:8123`)
2. **`SUPERVISOR_TOKEN`**: Home Assistant 프로필 ➔ 화면 하단 **[장기 사용 토큰 만들기]** ➔ 발급받은 JWT 문자열 복사.

---

### 2.5 대화형 설정 마법사 (`python3 setup.py`) 실행
LXC 터미널에서 소스 디렉토리(`/opt/Homeassistant-hermes`)로 이동 후 실행합니다:
```bash
cd /opt/Homeassistant-hermes
python3 setup.py
```
- **`A` (🚀 전체 설정 마법사)**: Step 1~4 안내에 따라 4개 키를 순차적으로 입력합니다.
- **`5` (🔍 상태 조회)**: 비밀키 마스킹(`🔒 설정 완료 (AIz***...)`) 조회 및 저장(`0`).

---

### 2.6 백엔드 에이전트 도커 컨테이너 구동 및 확인 (필수)

> [!IMPORTANT]
> **`setup.py` 실행으로 `.env` 환경변수가 최초 생성되거나 수정(API 키/토큰 변경 등)된 직후에는 반드시 아래 구동 명령어를 실행하여 변경된 `.env` 정보를 도커 컨테이너로 새로 로드해야 에이전트에 정상 반영됩니다.**

LXC 터미널에서 아래 한 줄 명령어를 전송하여 에이전트를 구동(또는 재시동)합니다:
```bash
docker rm -f hermes-agent 2>/dev/null; docker run -d --name hermes-agent --security-opt apparmor=unconfined --env-file .env -p 2223:22 -v /usr/share/hassio/homeassistant:/config hermes-agent:local
```
- **동작 검증**: `docker logs --tail 30 -f hermes-agent` 실행 후 텔레그램 봇에게 *"우리집 전체 온도 알 수 있을까"* 전송하여 대답 확인.

---

### 2.7 개발 단계 코드 1초 초고속 반영 배포 (pkill 방식)
PC에서 코드를 수정 후 재배포할 때, 도커 재빌드 없이 1초 만에 반영하는 일상 개발용 명령어입니다:

- **PC PowerShell 한 줄 배포 명령어**:
  ```powershell
  scp -F NUL -r D:\Antigravity\hermes root@<LXC_HOST_IP>:/opt/Homeassistant-hermes; ssh -F NUL root@<LXC_HOST_IP> "cp -rf /opt/Homeassistant-hermes/hermes/* /opt/Homeassistant-hermes/ 2>/dev/null; rm -rf /opt/Homeassistant-hermes/hermes; chmod -R 0755 /opt/Homeassistant-hermes/hermes_home_assistant/rootfs/usr/local/bin/ /opt/Homeassistant-hermes/hermes_home_assistant/rootfs/etc/s6-overlay/s6-rc.d/; docker start hermes-agent 2>/dev/null || docker run -d --name hermes-agent --security-opt apparmor=unconfined --env-file /opt/Homeassistant-hermes/.env -p 2223:22 -v /usr/share/hassio/homeassistant:/config -v /opt/Homeassistant-hermes/hermes_home_assistant/rootfs/usr/local/bin:/usr/local/bin hermes-agent:local; docker exec hermes-agent pkill -f python3 2>/dev/null || true; docker logs --tail 20 -f hermes-agent"
  ```
> [!TIP]
> 💡 pkill 방식의 0.1초 원격 자동 재시동 원리는 [5.3 pkill 방식의 0.1초 즉시 재시동 원리](#53-pkill-방식의-01초-즉시-재시동-원리)를 참고하세요.

---

## 3. 헤르메스 데스크탑(Hermes Desktop) 설치 및 설정

PC 환경에서 시각적 GUI 워크벤치를 통해 에이전트를 관제하고, 대시보드 리포트 및 자동화 코드 검토를 수행합니다.

### 3.1 다운로드 및 설치
1. **공식 웹사이트 접속**: [Nous Research Hermes Agent 공식 다운로드 사이트](https://hermes-agent.nousresearch.com/) (또는 [GitHub Releases](https://github.com/nousresearch/hermes-agent/releases)) 접속.
2. **OS별 패키지 설치**:
   - **Windows**: `Hermes-Desktop-Setup-x64.exe` 다운로드 ➔ 마법사에 따라 기본 설치.
   - **macOS**: `Hermes-Desktop-macOS.dmg` 다운로드 ➔ `Applications` 드래그.

> [!WARNING]
> 💡 Node.js 버전 이슈가 발생할 경우 [5.1 Node.js 홀수 버전 불일치 에러](#51-nodejs-홀수-버전-불일치-에러-트러블슈팅)를 참고하여 짝수 LTS(v24 LTS)로 재설치하세요.

---

### 3.2 LLM 모델 및 API 키 연동 설정

1. **Google Gemini API 키 등록 (`Providers` 탭)**:
   - 앱 우측 상단 **⚙️ (Settings)** 클릭 ➔ 좌측 메뉴 하단 **`Providers`** 선택.
   - 목록 중 **`Google AI Studio`** 선택 후 발급받은 `GEMINI_API_KEY` 입력 후 저장.

2. **기본 사용 모델 설정 (`Model` 탭)**:
   - 좌측 메뉴 맨 위 **`Model`** 선택.
   - 첫 번째 드롭다운: **`Google AI Studio`** 선택.
   - 두 번째 드롭다운: 사용할 기본 모델(예: `gemini-flash-lite-latest`) 선택 후 **`Apply`** 버튼 클릭.

3. **추천 모델 선택**:
   - **`gemini-flash-lite-latest`** (또는 `gemini-2.0-flash-lite`): 초경량·초고속 모델로 daily 쿼터 한도가 가장 넉넉하며, 자동화 종합 분석 및 대시보드 리포트를 완벽하게 출력 (**실전 1순위 강력 추천!**).
   - **`gemini-2.0-flash` / `gemini-flash-latest`**: 일상적인 기기 조작 및 상태 조회 표준 모델.
   - **`gemini-2.5-pro`**: 대용량 YAML 대시보드 정밀 수정 시 선택.

---

### 3.3 Home Assistant 도구(Tools) 및 백엔드 MCP (포트 2223) 연동

Hermes Desktop에서 Home Assistant를 제어하고 백엔드의 구문 검사/백업/롤백 도구를 사용하기 위한 설정입니다.

#### 📌 UI 메뉴 위치 안내
1. 앱 좌측 메인 메뉴에서 **`Capabilities`** 선택.
2. 화면 중앙 상단에서 **`Tools`** 탭 또는 **`MCP`** 탭 선택.

---

#### 1. `Tools` 탭 설정 (스마트홈 최적화 핵심 세팅 ⭐)
- **메뉴 위치**: `Capabilities` ➔ **`Tools`** 탭 선택
- **스위치 토글 설정 (필수!)**:
  - ✅ **`Home Assistant`**: **ON (켜기)** ➔ 발급받은 `HASS_TOKEN` 및 `HASS_URL` 입력 (실시간 온·습도, 조명, 스위치 0.1초 조회/제어)
  - ✅ **`File Operations`**: **ON (켜기)** ➔ 원격/마운트된 YAML 파일 직접 열기 및 분석 필수
  - ❌ **나머지 모든 항목 (`Terminal & Processes`, `Code Execution`, `Browser Automation` 등)**: **OFF (전부 끄기)**

> [!IMPORTANT]
> **💡 필수 도구만 남기고 끄는 이유 (속도 및 팝업 최적화)**
> - PC용 도구(`Terminal & Processes`, `Code Execution` 등)가 켜져 있으면, AI가 질문을 받고 PC 내 디스크 파일 검색이나 파이썬 코드를 직접 작성하는 등 불필요한 딴짓을 시도합니다.
> - **`Home Assistant`와 `File Operations` 2개만 ON으로 남기고 싹 꺼두셔야** 코드 실행 승인 팝업(Run/Reject) 없이 **0.5초 만에 홈어시스턴트 API 및 YAML 분석으로 즉시 직행하여 초고속 답변**을 출력합니다.

---

#### 2. `MCP` 탭 설정 (고급 에이전트 검토/백업/롤백용)
- **설정 이유**: LXC 서버 내부의 파이썬 엔진(`ha_mcp_server.py`)을 SSH로 연결하여, `/config/automations.yaml` 원문 자동 열기(`ha_read_yaml`), 구문 검사(`ha core check`), 안전 백업 및 롤백(`ha_rollback_yaml`) 도구를 활성화하기 위함.
- **방법**: `Capabilities` ➔ **`MCP`** 탭 선택 ➔ 우측 편집창(`mcp.json`)에 아래 JSON 코드를 입력 후 **`Save`** 클릭.

```json
{
  "mcpServers": {
    "hermes-ha-agent": {
      "command": "ssh",
      "args": [
        "-F",
        "NUL",
        "-p",
        "2223",
        "root@<LXC_HOST_IP>",
        "docker exec -i hermes-agent python3 /usr/local/bin/ha_mcp_server.py"
      ]
    }
  }
}
```

---

## 4. YAML 파일 안전 자동 백업 및 월별 히스토리 관리 시스템

Hermes Agent는 YAML 파일 수정 시 예기치 않은 오작동이나 구문 에러로부터 시스템을 안전하게 보호합니다.

### 4.1 원본 파일 자동 백업 및 10개 로테이션
- **저장 경로**: `/config/hermes/backups/`
- **파일명 지정**: `[원본파일명]_[YYYYMMDD_HHMMSS].yaml` (예: `automations_20260808_110500.yaml`)
- **로테이션 규칙**: 원본 파일명 기준 **최신 10개 유지** (초과 시 가장 오래된 파일 자동 삭제).
- **긴급 롤백(Rollback)**: 요청 시 최신 백업본으로 복원되며, 구문 검사(`ha core check`) 실패 시에도 자동 롤백됩니다.

### 4.2 월별 히스토리 기록 및 12개월(1년) 자동 로테이션
- **저장 경로**: `/config/hermes/backups/history/`
- **파일명 지정**: `yaml_history_[YYYY_MM].md` (예: `yaml_history_2026_08.md`)
- **기록 항목**: 변경 시각, 원인(Root Cause), 수정 내용(Fix Applied), 줄 번호 포함 정밀 Diff 코드, 기대 효과(Expected Outcome).
- **12개월 로테이션**: **최근 12개월(1년) 유지** 후 이전 파일 자동 삭제.

---

## 5. 🛠️ 종합 트러블슈팅 및 자주 묻는 질문 (Troubleshooting & FAQ)

설치 및 가동 중 자주 발생하는 질문과 오류 해결책을 일괄 모아 정리한 단원입니다.

### 5.1 Node.js 홀수 버전 불일치 에러 트러블슈팅
- **증상**: Hermes Desktop 또는 MCP 서버 실행 시 모듈 버전 불일치(Version Mismatch Error) 발생.
- **원인**: Node.js의 홀수 버전(v23, v25 등)은 개발용 최신 버전으로 네이티브 바이너리 모듈 불일치가 자주 일어납니다.
- **해결책**: [Node.js 공식 다운로드 사이트](https://nodejs.org/en/download)에서 홀수 버전을 삭제하고, **안정적인 짝수 LTS 버전(Node.js v24 LTS 등)**으로 재설치합니다.

### 5.2 Proxmox LXC AppArmor sysctl 권한 에러 해결
- **증상**: Unprivileged LXC 내 도커 실행 시 `open sysctl net.ipv4.ip_unprivileged_port_start file: permission denied` 차단 에러 발생.
- **해결책**: Proxmox 노드(호스트) 쉘에서 해당 LXC 설정에 아래 구문을 주입하고 컨테이너를 재시작합니다:
  ```bash
  echo "lxc.apparmor.profile: unconfined" >> /etc/pve/lxc/<CT_ID>.conf
  pct reboot <CT_ID>
  ```

### 5.3 pkill 방식의 0.1초 즉시 재시동 원리
- **원인**: Unprivileged LXC에서 `docker restart` 실행 시 AppArmor 권한 에러로 튕기는 문제 방지.
- **원리**: `docker exec hermes-agent pkill -f python3`를 실행하면, 백그라운드의 s6-overlay 데몬 프로세스 관리자가 멈춘 파이썬 프로세스를 즉시 감지하여 **0.1초 만에 도커 재부팅 없이 자동으로 재시동**합니다.

### 5.4 SSH Root 로그인 및 비밀번호 인증 허용
- **증상**: `scp`나 `ssh` 접속 시 `Permission denied (publickey,password)` 거부 에러.
- **해결책**: LXC 내부 `/etc/ssh/sshd_config`에서 `PermitRootLogin yes` 및 `PasswordAuthentication yes`를 설정하고 `systemctl restart ssh`를 실행합니다.

### 5.5 SCP 전송 시 중복 폴더 자동 정리 노하우
- **원인**: `scp -r` 전송 전 타깃 폴더(`/opt/Homeassistant-hermes`)를 미리 만들어두면 `/opt/Homeassistant-hermes/hermes` 폴더가 이중 생성되는 현상.
- **해결책**: 타깃 폴더를 미리 생성하지 않고 바로 `scp -r`을 실행하거나, 배포 스크립트의 `cp -rf /opt/Homeassistant-hermes/hermes/* /opt/Homeassistant-hermes/` 자동 정리 구문을 사용합니다.

### 5.6 Gemini API 429 Quota 한도 초과 및 자동 모델 폴백
- **증상**: `Gemini HTTP 429 RESOURCE_EXHAUSTED` 또는 `404 NOT_FOUND` 에러.
- **해결책**: 백엔드 파이썬 엔진(`gemini_agent.py`)이 `gemini-2.0-flash` ➔ `gemini-2.0-flash-lite` ➔ `gemini-1.5-flash` 순으로 자동 스위칭하므로 잠시 후 재시도하거나, Hermes Desktop Settings에서 모델을 **`gemini-2.0-flash-lite`**로 지정합니다.

### 5.7 한글 자동화 질문 시 영문 엔티티 ID 자동 맵핑 방식
- **증상**: *"공기청정기 자동화 검토해 줘"* 질문 시 복잡한 영문 엔티티 ID(`automation.geosil_gaseubgi...`)를 물어보는 현상.
- **해결책**: 백엔드의 2단계 자동 추적 알고리즘이 `get_device_state("")`로 한글 표시 이름(Friendly Name)과 영문 ID를 자동 맵핑한 뒤 `/config/automations.yaml`을 직접 읽어오도록 개선되었습니다.

---
*(본 설명서는 개발 단계에 따라 지속적으로 업데이트됩니다.)*

