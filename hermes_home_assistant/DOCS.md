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
- **Features (중요)**: 도커를 LXC 내에서 실행하기 위해 반드시 **Nesting** 기능을 활성화해야 합니다.

### 1.2 LXC 생성 및 도커 세팅 단계
1. **Proxmox 웹 GUI 접속**: 우측 상단의 `Create CT` 버튼을 클릭합니다.
2. **General (일반)**: 컨테이너 ID와 Hostname(예: `ha-gemini-agent`)을 입력하고 비밀번호를 설정합니다. **Unprivileged container** 체크를 유지하는 것을 권장합니다.
3. **Template (템플릿)**: 미리 다운로드해 둔 Debian 12 또는 Ubuntu 22.04 템플릿을 선택합니다.
4. **Disks, CPU, Memory**: 위의 권장 스펙에 맞춰 할당합니다.
5. **Network**: 정적 IP(Static IP)를 할당하여 추후 HA나 Hermes Desktop 통신 시 IP가 변경되지 않도록 합니다.
6. **Confirm (확인)**: 생성 완료 후 **아직 시작(Start)하지 마십시오.**
7. **Nesting 활성화 및 AppArmor 차단 해제 (중요)**: 
   - 생성된 컨테이너 선택 -> `Options` -> `Features` 더블클릭 -> `keyctl` 및 `nesting` 항목을 체크하고 `OK`를 누릅니다.
   - **Proxmox AppArmor sysctl 권한 해제 (오류 방지 필수)**:
     Unprivileged LXC에서 도커 컨테이너가 `net.ipv4.ip_unprivileged_port_start` 권한 에러로 구동 실패하는 현상을 방지하기 위해 Proxmox 노드(호스트) 쉘에서 아래 명령어를 실행합니다:
     ```bash
     # Proxmox 호스트 쉘에서 실행 (<CT_ID>는 본인 컨테이너 번호, 예: 100)
     echo "lxc.apparmor.profile: unconfined" >> /etc/pve/lxc/<CT_ID>.conf
     ```
8. **컨테이너 내부 쉘에서 아래 명령어로 도커를 설치합니다**:
   - Proxmox 공식 웹 문서에 명시된 CLI 명령어로 컨테이너를 관리합니다.
   
     ```bash
     apt-get update && apt-get upgrade -y
     apt-get install -y curl
     curl -fsSL https://get.docker.com -o get-docker.sh
     sh get-docker.sh
     ```

> [!TIP] Proxmox 호스트에서 컨테이너 재시작 및 LXC 접속 방법
> 1. LXC 컨테이너 재시작 (공식 명령어: `pct reboot <CT_ID>`)
>	`pct reboot <CT_ID>`
>
> 2. LXC 컨테이너 내부 쉘 접속 (공식 명령어: `pct enter <CT_ID>`)
>	`pct enter <CT_ID>`
>
> 3. 컨테이너 내부에서 도커 상태 확인
>	`docker ps`

9. **설치 확인**: `docker --version` 및 `docker ps` 명령어를 통해 정상 동작을 확인합니다.

---

### 1.3 PC 개발 소스(`D:\Antigravity\hermes`) LXC로 수동 전송 가이드
아직 GitHub에 소스코드를 푸쉬하지 않은 개발 단계에서는 PC의 개발 폴더를 LXC의 리눅스 표준 앱 경로인 `/opt/Homeassistant-hermes`로 전송합니다.

#### 📌 [사전 필수] LXC SSH Root 로그인 및 비밀번호 인증 허용 설정
Debian/Ubuntu 기본 LXC 환경에서는 Root 로그인 및 비밀번호 인증이 차단되어 있으므로, LXC 콘솔에서 아래 명령어로 먼저 허용해야 합니다:

```bash
# 1. root 로그인 허용 설정
sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config
sed -i 's/PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config

# 2. 비밀번호 인증 허용 설정
sed -i 's/#PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
sed -i 's/PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config

# 3. SSH 서비스 재시작
systemctl restart ssh
```

#### 📌 LXC로 전송 실행
> [!TIP]
> LXC 내부에 `/opt/Homeassistant-hermes` 폴더를 미리 생성(`mkdir`)해 두고 `scp -r`을 실행하면 불필요한 하위 폴더(`/opt/Homeassistant-hermes/hermes`)가 이중으로 생기게 됩니다.
> **타깃 폴더를 미리 만들지 말고** 아래 `scp` 명령어를 바로 실행하면 SCP가 `/opt/Homeassistant-hermes` 폴더를 새로 만들면서 깔끔하게 전송됩니다.

1. **방법 A: Windows PowerShell `scp` 명령어 전송 (추천, `-F NUL` 옵션 포함)**:
   PC의 PowerShell을 열고 아래 명령어로 `D:\Antigravity\hermes` 전체를 LXC로 직접 전송합니다. (`-F NUL`을 통해 Windows SSH Config 간섭 방지)
   ```powershell
   scp -F NUL -r D:\Antigravity\hermes root@<LXC_HOST_IP>:/opt/Homeassistant-hermes
   ```
2. **방법 B: WinSCP / FileZilla GUI 프로그램 사용**:
   - Host: `<LXC_HOST_IP>`, Port: `22`, User: `root`, Password 입력 접속.
   - PC의 `D:\Antigravity\hermes` 폴더를 LXC의 `/opt/Homeassistant-hermes` 경로로 드래그 앤 드롭 전송.
3. **방법 C: Proxmox 호스트 `pct push` 명령어 활용**:
   - Proxmox 노드 쉘에서 명령어를 통해 LXC로 전송합니다:
   ```bash
   pct push <CT_ID> D:\Antigravity\hermes /opt/Homeassistant-hermes
   ```

---

## 2. 필수 인증키 4가지 발급 및 준비 가이드

Hermes Agent 구동 및 연동을 위해 필요한 **4가지 핵심 인증키/정보**의 발급 및 확인 가이드입니다.

### 2.1 Google Gemini API Key 발급 (`GEMINI_API_KEY`)
Google Gemini 모델을 호출하기 위한 API 키입니다.
1. [Google AI Studio](https://aistudio.google.com/) 웹사이트에 접속하여 구글 계정으로 로그인합니다.
2. 화면 상단의 **[Get API key]** 버튼을 클릭합니다.
3. **[Create API key]**를 누르고 프로젝트를 선택하여 새로운 API 키를 생성합니다.
4. 생성된 `AIzaSy...`로 시작하는 긴 문자열을 복사합니다.

### 2.2 텔레그램 봇 생성 (`TELEGRAM_BOT_TOKEN`)
모바일에서 실시간 기기 상태 조회 및 조정을 수행할 텔레그램 봇 토큰입니다.
1. 텔레그램 앱 검색창에서 `@BotFather`를 검색하여 대화를 시작합니다.
2. `/newbot` 명령어를 전송합니다.
3. 봇의 표시 이름(Name)을 입력합니다. (예: `우리집 스마트홈 에이전트`)
4. 봇의 유저네임(Username)을 입력합니다. (반드시 `bot`으로 끝나야 함. 예: `my_ha_gemini_bot`)
5. 생성 완료 후 출력되는 **HTTP API Token** (예: `123456789:ABCdef...`)을 복사합니다. (외부 노출 엄금)

### 2.3 사용자 인증 (`AUTHORIZED_CHAT_IDS`)
허가되지 않은 타인이 텔레그램 봇을 사용하지 못하도록 본인의 Chat ID만 수신 허용합니다.
1. 텔레그램 검색창에서 `@userinfobot` 또는 `@RawDataBot`을 검색하여 `/start`를 누릅니다.
2. 봇이 응답하는 메시지 중 `Id` 필드에 적힌 숫자(예: `123456789`)가 본인의 Chat ID입니다.

### 2.4 Home Assistant 장기 사용 토큰 & URL (`SUPERVISOR_TOKEN` / `HASS_TOKEN`, `HASS_URL`)
에이전트가 Home Assistant API에 안전하게 접근하기 위한 인증 토큰과 접속 주소입니다.
1. **`HASS_URL`**: Home Assistant 내부 접속 주소 (예: `http://192.168.x.x:8123` 또는 `http://homeassistant.local:8123`)
2. **`SUPERVISOR_TOKEN` (HASS_TOKEN)**:
   - Home Assistant 대시보드 로그인 -> 좌측 하단 **사용자 프로필 아이콘** 클릭
   - 화면 가장 아래로 스크롤하여 **[장기 사용 토큰]** 항목으로 이동
   - **[토큰 만들기]** 버튼 클릭 후 이름(예: `Hermes Agent`) 입력
   - 발급되는 긴 JWT 문자열 토큰을 복사합니다.

### 2.5 대화형 설정 마법사 (`python3 setup.py`) 상세 사용법

준비된 4가지 인증키를 `.env` 파일에 손쉽게 입력하고 관리할 수 있도록 대화형 터미널 시스템이 제공됩니다. LXC 콘솔에서 소스 디렉토리(`/opt/Homeassistant-hermes`)로 이동한 후 실행합니다.

```bash
cd /opt/Homeassistant-hermes
python3 setup.py
```

#### 📌 메뉴 구성 및 세부 실행 단계
1. **메인 메뉴 선택**:
   - **`A` (🚀 전체 설정 마법사)**: 키 입력을 Step 1부터 Step 4까지 안내에 따라 순차적으로 진행합니다.
   - **`1` ~ `3` (개별 설정)**: 특정 키(Gemini Key, Telegram Token/Chat ID, HA Token/URL)만 선택하여 수정합니다.
   - **`4` (📖 발급처 도움말)**: 각 키별 발급처 URL 및 가이드를 확인합니다.
   - **`5` (🔍 상태 조회)**: 기존 입력된 비밀키를 마스킹(`🔒 설정 완료 (AIz***...)`) 처리하여 안전하게 확인합니다.

### 2.6 setup.py로 `.env` 설정 및 수정 이후

LXC 터미널(`/opt/Homeassistant-hermes`)에서 `setup.py` 실행 완료 후, 아래 명령어를 순서대로(또는 한 줄로) 실행하시면 변경된 `.env` 설정이 즉시 반영되어 컨테이너가 새로 끕니다.

1. 단축 명령어 (복사해서 붙여넣기용)

```bash
# 기존 컨테이너 강제 삭제 및 수정된 .env로 새 컨테이너 구동
docker rm -f hermes-agent 2>/dev/null; docker run -d --name hermes-agent --security-opt apparmor=unconfined --env-file .env -p 2223:22 -v /usr/share/hassio/homeassistant:/config hermes-agent:local
```

2. 정상 반영 확인

재실행 후 아래 명령어로 로그를 확인했을 때 에러 없이 텔레그램/Gemini 연결 메시지가 뜨는지 확인하시면 완료됩니다.

```bash
docker logs --tail 30 -f hermes-agent
```

### 2.7 Hermes Agent 초고속 개발 및 동작 검증 (1초 즉시 반영 방식)

개발 단계에서 소스코드를 수정할 때마다 `docker build --no-cache`를 매번 실행하면 파이썬 패키지와 알파인 인프라 재다운로드로 인해 수십 초 이상의 시간이 소요됩니다. 

이를 해결하기 위해 **소스코드 볼륨 바인드 마운트(-v)** 및 **중복 폴더 자동 청소 한 줄 스크립트**를 사용하여 **1초 만에 코드를 전송하고 즉시 가동**합니다.

#### 📌 코드 수정 후 바인드 마운트 기반 컨테이너 구동

PC에서 코드나 스크립트를 수정한 후, 호스트 스크립트 폴더 마운트(`-v .../usr/local/bin`) 옵션까지 챙겨서 **PC 파워셸을 통해 원격(SSH)으로 배포할 때** 아래 명령어로 소스 폴더(`/usr/local/bin`)가 컨테이너 내부로 직접 연결되도록 실행해 둡니다:

```powershell
ssh -F NUL root@<LXC_HOST_IP> "docker rm -f hermes-agent 2>/dev/null; docker run -d --name hermes-agent --security-opt apparmor=unconfined --env-file /opt/Homeassistant-hermes/.env -p 2223:22 -v /usr/share/hassio/homeassistant:/config -v /opt/Homeassistant-hermes/hermes_home_assistant/rootfs/usr/local/bin:/usr/local/bin hermes-agent:local"
```

다음과 같은 작업 단계에서 실행하시면 됩니다:
1. **PC에서 소스 코드를 수정한 후 반영할 때**
2. **도커 이미지를 다시 빌드했을 때**
3. **에이전트가 멈추거나 에러가 나서 강제 초기화(Clean Reset)가 필요할 때**

#### 📌 [PC PowerShell 명령어] 일상적인 코드 개발용
```powershell
scp -F NUL -r D:\Antigravity\hermes root@<LXC_HOST_IP>:/opt/Homeassistant-hermes; ssh -F NUL root@<LXC_HOST_IP> "cp -rf /opt/Homeassistant-hermes/hermes/* /opt/Homeassistant-hermes/ 2>/dev/null; rm -rf /opt/Homeassistant-hermes/hermes; chmod -R 0755 /opt/Homeassistant-hermes/hermes_home_assistant/rootfs/usr/local/bin/ /opt/Homeassistant-hermes/hermes_home_assistant/rootfs/etc/s6-overlay/s6-rc.d/; docker start hermes-agent 2>/dev/null || docker run -d --name hermes-agent --security-opt apparmor=unconfined --env-file /opt/Homeassistant-hermes/.env -p 2223:22 -v /usr/share/hassio/homeassistant:/config -v /opt/Homeassistant-hermes/hermes_home_assistant/rootfs/usr/local/bin:/usr/local/bin hermes-agent:local; docker exec hermes-agent pkill -f python3 2>/dev/null || true; docker logs --tail 20 -f hermes-agent"
```

#### 📌 [LXC 터미널 CLI 명령어] 컨테이너 구조/설정 변경용
```bash
cp -rf /opt/Homeassistant-hermes/hermes/* /opt/Homeassistant-hermes/ 2>/dev/null; rm -rf /opt/Homeassistant-hermes/hermes; chmod -R 0755 /opt/Homeassistant-hermes/hermes_home_assistant/rootfs/usr/local/bin/ /opt/Homeassistant-hermes/hermes_home_assistant/rootfs/etc/s6-overlay/s6-rc.d/; docker start hermes-agent 2>/dev/null || docker run -d --name hermes-agent --security-opt apparmor=unconfined --env-file /opt/Homeassistant-hermes/.env -p 2223:22 -v /usr/share/hassio/homeassistant:/config -v /opt/Homeassistant-hermes/hermes_home_assistant/rootfs/usr/local/bin:/usr/local/bin hermes-agent:local; docker exec hermes-agent pkill -f python3 2>/dev/null || true; docker logs --tail 20 -f hermes-agent
```

> [!TIP]
> **💡 pkill 방식의 신의 한 수**
> - Unprivileged LXC에서 `docker restart` 시 발생하는 AppArmor 프로필 권한 오류(`permission denied`)를 완전 우회합니다.
> - s6-overlay 데몬 관리자가 파이썬 에이전트를 **0.1초 만에 즉시 자동 재시동**하므로 도커 데몬을 껐다 켤 필요가 전혀 없습니다.

> [!NOTE]
> **💡 이 동작의 장점**
> 1. **대기시간 0초 (도커 빌드 생략)**: `docker build` 과정을 거치지 않고 파일 복사 후 `docker restart`만 수행되므로 1초 만에 변경 코드가 가동됩니다.
> 2. **중복 폴더 자동 정리**: `scp` 전송 과정에서 생길 수 있는 하위 중복 폴더(`/opt/Homeassistant-hermes/hermes/`)를 최상위 폴더로 자동 동기화하고 중복 폴더를 즉시 영구 삭제합니다.

#### 📌 동작 검증 단계
1. **구동 상태 확인**: `docker ps` 명령어로 `hermes-agent` 컨테이너가 `Up` 상태인지 확인합니다.
2. **텔레그램 동작 테스트**: 텔레그램 앱에서 봇에게 `"우리집 전체 온도 알 수 있을까"` 등 메시지를 전송하여 답변을 확인합니다.

---

## 3. 헤르메스 데스크탑(Hermes Desktop) 설치 및 설정

헤르메스 데스크탑은 PC 환경에서 시각적 GUI를 통해 에이전트를 관제하고, 복잡한 YAML 수정, 구문 검사, 디버깅을 통합 처리하는 강력한 클라이언트 애플리케이션입니다.

### 3.1 다운로드 및 운영체제별 설치 가이드
1. **공식 웹사이트 접속**: [Nous Research Hermes Agent 공식 다운로드 사이트](https://hermes-agent.nousresearch.com/) (또는 [GitHub Releases](https://github.com/nousresearch/hermes-agent/releases))에 접속합니다.
2. **OS별 패키지 설치**:
   - **Windows**: `Hermes-Desktop-Setup-x64.exe` (또는 `.msi`) 다운로드 ➔ 마법사에 따라 기본 설치.
   - **macOS**: `Hermes-Desktop-macOS.dmg` 다운로드 ➔ `Applications` 폴더로 드래그 배치.
> [!WARNING]
> **💡 Node.js 버전 이슈 및 트러블슈팅 (필수 확인)**
> - Node.js의 홀수 버전(v23, v25 등)은 개발용 최신 버전으로, 네이티브 모듈 및 MCP 통신 시 **버전 불일치 에러(Version Mismatch Error)**가 발생할 수 있습니다.
> - 에러 발생 시 [Node.js 공식 다운로드](https://nodejs.org/en/download)에서 홀수 버전을 삭제하고, **안정적인 짝수 LTS 버전(Node.js v24 LTS 등)**으로 재설치하여 해결해야 합니다.

---

### 3.2 LLM 모델 및 API 키 연동 설정
1. 앱 실행 후 화면 좌측 하단 **Settings** > **LLM Providers** 선택.
2. **Google Gemini API Key** 항목에 발급받은 `GEMINI_API_KEY` 입력.
3. **추천 모델 선택**:
   - **`gemini-2.0-flash-lite`**: 초경량·초고속 모델로 daily 쿼터 한도가 가장 넉넉하며, 자동화 종합 분석 및 대시보드 리포트를 완벽하게 출력 (실전 강력 추천!).
   - **`gemini-2.0-flash` / `gemini-flash-latest`**: 일상적인 기기 조작 및 상태 조회 표준 모델.
   - **`gemini-2.5-pro`**: 복잡한 YAML 대용량 코드 정밀 수정 시 선택.

---

### 3.3 Home Assistant MCP (Model Context Protocol) 및 포트 2223 연동
Home Assistant 백엔드 및 Hermes Agent 인스턴스와 원격 제어망을 구축합니다:

1. **HA 장기 사용 토큰 발급**:
   - Home Assistant 대시보드 -> 프로필 -> 화면 하단 **[장기 사용 토큰 만들기]** ➔ 발급된 JWT 토큰 복사.
2. **Hermes Desktop MCP 설정**:
   - 앱 내 **MCP Settings** / **Integrations** 메뉴 이동.
   - **HA URL**: `http://<YOUR_HA_IP>:8123` (또는 본인의 HA 접속 주소)
   - **Access Token**: 발급받은 장기 사용 토큰 입력
3. **SSH / SFTP 원격 `/config` 마운트 (포트 2223)**:
   - Hermes Agent 내장 전용 SSH 데몬(포트 `2223`)을 사용하여 별도 Samba 설정 없이 마운트:
     - **Host**: `<LXC_HOST_IP>` (LXC 호스트 IP)
     - **Port**: `2223` (Hermes Agent SSH 포트)
     - **Target Directory**: `/config`

---

### 3.4 Samba Share (네트워크 드라이브 `\\<HA_IP>\config`) 연동
Home Assistant 공식 `Samba share` 애드온을 활성화하여 PC에서 로컬 폴더처럼 마운트하는 방식입니다.

1. **연동 방법**:
   - Home Assistant 웹 GUI -> App Store -> `Samba share` 설치 및 시작 (비밀번호 설정).
   - Windows 탐색기 주소창에 `\\<HA_IP>\config` 입력 또는 네트워크 드라이브(예: `Z:\`)로 연결.
   - Hermes Desktop 앱에서 `Open Folder`를 눌러 마운트된 네트워크 드라이브(`Z:\`)를 엽니다.

---

### 3.5 PC용 MCP (Model Context Protocol) 서버 연동 (`ha_mcp_server.py`)
Hermes Desktop에서 백엔드의 검증 및 롤백 도구를 직접 호출할 수 있도록 **MCP Server**가 포함되어 있습니다.

1. **제공 MCP Tools**:
   - `ha_core_check`: Home Assistant 구문 검사(`ha core check`) 실행 및 결과 반환.
   - `ha_get_device_state`: 엔티티 상태 조회.
   - `ha_rollback_yaml`: 오작동 발생 시 `/config/hermes/backups/`의 최신 백업본으로 롤백.
2. **MCP 서버 구동 경로**:
   - `/usr/local/bin/ha_mcp_server.py` (Stdio JSON-RPC 방식)

---

## 4. YAML 파일 안전 자동 백업 및 월별 히스토리 관리 시스템

Hermes Agent는 YAML 파일 수정 시 예기치 않은 오작동이나 구문 에러로부터 시스템을 안전하게 보호하고, 변경 이력을 투명하게 추적할 수 있는 자동화 시스템을 갖추고 있습니다.

### 4.1 원본 파일 자동 백업 및 10개 로테이션
- **전용 저장 경로**: `/config/hermes/backups/` (타 앱과의 충돌 완전 차단)
- **파일명 지정**: `[원본파일명]_[YYYYMMDD_HHMMSS].yaml` (예: `automations_20260808_110500.yaml`)
- **로테이션 규칙**: 개별 파일명 단위로 백업본이 **10개를 초과하는 경우, 가장 오래된 백업 파일부터 자동 삭제**됩니다.
- **긴급 롤백(Rollback)**: 텔레그램이나 데스크탑에서 "이전 백업으로 원상복구해 줘" 요청 시 최신 백업본이 즉시 원본 위치로 덮어씌워집니다. 구문 검사(`ha core check`) 실패 시에도 자동으로 롤백이 실행됩니다.

### 4.2 월별 히스토리 기록 및 12개월(1년) 자동 로테이션
- **전용 저장 경로**: `/config/hermes/backups/history/`
- **월별 히스토리 파일**: `yaml_history_[YYYY_MM].md` (예: `yaml_history_2026_08.md`)
- **기록 내용**:
  - 변경 시각, 파일 경로, 원인(Root Cause), 수정 내용(Fix Applied), 기대 효과(Expected Outcome)
  - **정밀 Diff 기록**: 몇 번째 줄(Line Numbers)이 수정되었는지 변경 전 구문과 변경 후 구문이 마크다운 코드로 함께 보관됩니다.
- **12개월 로테이션 규칙**: 월별 히스토리 파일이 **12개를 초과(1년 도달)하면 1년이 지난 이전 월별 히스토리 파일은 자동 삭제**됩니다.

---
*(본 설명서는 개발 단계에 따라 지속적으로 업데이트됩니다.)*
