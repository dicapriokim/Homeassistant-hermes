<p align="right">
  <a href="DOCS.md">한국어</a> · <strong>English</strong>
</p>

# Hermes Agent for Home Assistant User Guide

This guide provides instructions for installing and running Hermes Agent, integrating with Google Gemini 3.6 API, Telegram bot, and Hermes Desktop for smart home control and safe YAML management.

## Key Features

- **Google Gemini 3.6 API Smart Agent**: Natural language query and device control via Telegram bot
- **YAML Safe Backup & Auto-Rollback**: Automatic 10-file rotation backups under /config/hermes/backups/ and rollback on syntax error
- **Monthly History & 12-Month Rotation**: Markdown monthly change logs under /config/hermes/backups/history/ with 1-year auto-deletion
- **Hermes Desktop Integration**: Port 2223 SSH/SFTP and MCP (ha_mcp_server.py) support

## Quick Start

1. Prepare the 4 key credentials (`GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `AUTHORIZED_CHAT_IDS`, `SUPERVISOR_TOKEN`).
2. Run `python3 setup.py` or populate the `.env` file directly.
3. Launch the container via `docker run` or the Home Assistant App Store.
4. Send a message to your Telegram bot to test functionality.

---

## 3. Hermes Desktop Installation & Setup

Hermes Desktop is the official graphical desktop client for monitoring your smart home agent, mounting Home Assistant's `/config` directory, and communicating via MCP (Model Context Protocol).

### 3.1 Download and Installation
1. **GitHub Releases**: Visit the [Nous Research Hermes Agent Releases](https://github.com/nousresearch/hermes-agent/releases) page.
2. **Platform Installation**:
   - **Windows**: Download `Hermes-Desktop-Setup-x64.exe` (or `.msi`) and run the installer.
   - **macOS**: Download `Hermes-Desktop-macOS.dmg` and drag it to your `Applications` folder.
   - **Linux**: Download `Hermes-Desktop-Linux.AppImage`, make it executable (`chmod +x`), and launch it.

### 3.2 LLM Model & API Key Configuration
1. Open Hermes Desktop and go to **Settings** > **LLM Providers**.
2. Select **Google Gemini API**.
3. Enter your `GEMINI_API_KEY` from Google AI Studio and select `gemini-2.5-pro` (or `gemini-2.5-flash`) as the default model.

### 3.3 Home Assistant MCP & Remote SSH Integration
Connect Hermes Desktop with your Hermes Agent backend and Home Assistant:

1. **Generate HA Long-Lived Access Token**:
   - Go to Home Assistant ➔ Profile ➔ Scroll to the bottom and click **Create Token**.
2. **Configure MCP in Hermes Desktop**:
   - Navigate to **MCP Settings** / **Integrations**.
   - **HA Server URL**: `https://ha.dicapriokim.ddnsfree.com` (or local HA IP)
   - **Access Token**: Enter the generated Long-Lived Token
3. **Remote SSH / SFTP `/config` Mount (Port 2223)**:
   - Connect via VS Code Remote - SSH or SFTP client:
     - **Host**: `192.168.0.86` (LXC Host IP)
     - **Port**: `2223` (Hermes Agent SSH Port)
     - **Path**: `/config`