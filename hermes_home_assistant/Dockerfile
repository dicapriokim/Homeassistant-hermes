# syntax=docker/dockerfile:1.7
ARG BUILD_FROM=ghcr.io/home-assistant/base:3.24
FROM ${BUILD_FROM}

ARG BUILD_ARCH=amd64
ARG BUILD_VERSION=0.6.0

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apk add --no-cache \
      bash \
      ca-certificates \
      coreutils \
      curl \
      git \
      jq \
      less \
      nano \
      nginx \
      nodejs \
      openssh \
      python3 \
      py3-pip \
      ripgrep \
      shadow \
      sqlite \
      tmux \
      ttyd \
      yamllint \
      yq \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir \
      google-genai \
      python-telegram-bot \
      requests \
      flask \
      aiohttp

ENV PATH="/opt/venv/bin:$PATH"

COPY rootfs /

RUN mkdir -p /data \
    && chmod 0755 /data \
    && find /etc/s6-overlay /usr/local /etc/profile.d -type f -exec sed -i 's/\r$//' {} + \
    && chmod 0755 /usr/local/bin/* 2>/dev/null || true \
    && chmod -R 0755 /etc/s6-overlay/s6-rc.d/ 2>/dev/null || true

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="app" \
  io.hass.arch="${BUILD_ARCH}" \
  org.opencontainers.image.title="Home Assistant App: Gemini Agent" \
  org.opencontainers.image.description="Gemini 3.6 API powered AI agent with Telegram bot and Hermes integration" \
  org.opencontainers.image.source="https://github.com/dicapriokim/Homeassistant-hermes"
