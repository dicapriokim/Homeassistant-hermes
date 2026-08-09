<p align="right">
  <a href="README.md">한국어</a> · <strong>English</strong>
</p>

# Hermes Agent for Home Assistant

A smart home agent service for Home Assistant powered by Google Gemini 3.6 API, Telegram bot, and Hermes Desktop.

## Key Features

- **Google Gemini 3.6 API Smart Agent**: Control devices and query states via mobile Telegram bot
- **YAML Safe Backup & Auto-Rollback**: Automatic 10-file rotation backups under /config/hermes/backups/ and rollback on syntax error
- **Hermes Desktop Integration**: Dedicated SSH/SFTP on port 2223 and MCP JSON-RPC server support
- **Monthly History & 12-Month Rotation**: Markdown monthly change logs under /config/hermes/backups/history/ with 1-year auto-deletion

## Quick Start

1. Provide GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, AUTHORIZED_CHAT_IDS, and SUPERVISOR_TOKEN in your .env file.
2. Launch the agent container via docker run or the Home Assistant App Store.
3. Send a message like "Hello!" or "Turn on living room light" to your Telegram bot.