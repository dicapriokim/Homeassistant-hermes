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

1. Prepare the 4 key credentials (GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, AUTHORIZED_CHAT_IDS, SUPERVISOR_TOKEN).
2. Run python3 setup.py or populate the .env file directly.
3. Launch the container via docker run or the Home Assistant App Store.
4. Send a message to your Telegram bot to test functionality.