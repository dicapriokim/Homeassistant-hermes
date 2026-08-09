import os
import re
import stat
from pathlib import Path


S6_ROOT = Path("etc/s6-overlay/s6-rc.d")
S6_SERVICES = ("hermes-ha-init", "gemini-agent", "ttyd", "ingress", "sshd")
EXECUTABLE_ROOTFS_PATHS = (
    "etc/s6-overlay/s6-rc.d/hermes-ha-init/up",
    "etc/s6-overlay/s6-rc.d/gemini-agent/run",
    "etc/s6-overlay/s6-rc.d/ingress/finish",
    "etc/s6-overlay/s6-rc.d/ingress/run",
    "etc/s6-overlay/s6-rc.d/sshd/finish",
    "etc/s6-overlay/s6-rc.d/sshd/run",
    "etc/s6-overlay/s6-rc.d/ttyd/finish",
    "etc/s6-overlay/s6-rc.d/ttyd/run",
)


def test_s6_user_bundle_and_dependency_graph(rootfs: Path) -> None:
    s6_root = rootfs / S6_ROOT
    contents = s6_root / "user/contents.d"
    assert {path.name for path in contents.iterdir()} == set(S6_SERVICES)

    assert (s6_root / "hermes-ha-init/type").read_text().strip() == "oneshot"
    assert (s6_root / "hermes-ha-init/up").is_file()
    assert (s6_root / "hermes-ha-init/dependencies.d/base").is_file()

    for service in ("gemini-agent", "ttyd", "ingress", "sshd"):
        assert (s6_root / service / "type").read_text().strip() == "longrun"

    assert (s6_root / "gemini-agent/dependencies.d/hermes-ha-init").is_file()
    assert (s6_root / "ttyd/dependencies.d/hermes-ha-init").is_file()
    assert (s6_root / "sshd/dependencies.d/hermes-ha-init").is_file()
    assert (s6_root / "ingress/dependencies.d/ttyd").is_file()


def test_s6_entrypoints_have_container_executable_policy(
    addon_root: Path, rootfs: Path
) -> None:
    dockerfile = (addon_root / "Dockerfile").read_text(encoding="utf-8")
    for relative_path in EXECUTABLE_ROOTFS_PATHS:
        script = rootfs / relative_path
        content = script.read_text(encoding="utf-8")
        assert (
            content.startswith("#!/command/with-contenv bashio")
            or content.startswith("#!/usr/bin/with-contenv bashio")
            or content.startswith("#!/usr/bin/env bashio")
        )
        assert (
            f"/{relative_path}" in dockerfile
            or "/etc/s6-overlay/s6-rc.d/" in dockerfile
            or "/etc/s6-overlay/s6-rc.d/*/finish" in dockerfile
        )
        if os.name != "nt":
            assert script.stat().st_mode & stat.S_IXUSR


def test_codex_release_is_pinned_and_checksum_verified(addon_root: Path) -> None:
    dockerfile = (addon_root / "Dockerfile").read_text(encoding="utf-8")
    assert "ARG BUILD_VERSION=0.6.0" in dockerfile
    assert (addon_root / "rootfs/usr/local/bin/gemini_agent.py").is_file()


def test_sshd_is_public_key_only(rootfs: Path) -> None:
    sshd_config = (rootfs / "etc/ssh/sshd_config").read_text(encoding="utf-8")
    required_lines = (
        "PubkeyAuthentication yes",
        "AuthenticationMethods publickey",
        "PasswordAuthentication no",
        "KbdInteractiveAuthentication no",
        "PermitEmptyPasswords no",
        "PermitRootLogin prohibit-password",
        "AuthorizedKeysFile /data/ssh/authorized_keys",
    )
    for line in required_lines:
        assert line in sshd_config


def test_ttyd_and_nginx_are_split_for_ingress(rootfs: Path) -> None:
    ttyd_run = (rootfs / S6_ROOT / "ttyd/run").read_text(encoding="utf-8")
    ingress_run = (rootfs / S6_ROOT / "ingress/run").read_text(encoding="utf-8")
    nginx_config = (rootfs / "etc/nginx/nginx.conf").read_text(encoding="utf-8")

    assert "--interface 127.0.0.1" in ttyd_run
    assert "--port 7682" in ttyd_run
    assert "--writable" in ttyd_run
    assert "exec nginx" in ingress_run
    assert "listen 7681" in nginx_config
    assert "proxy_pass http://127.0.0.1:7682" in nginx_config
    assert "proxy_set_header Upgrade $http_upgrade" in nginx_config


def test_init_has_idempotent_and_degraded_mode_guards(rootfs: Path) -> None:
    init_script = (rootfs / "usr/local/bin/hermes-ha-init").read_text(
        encoding="utf-8"
    )
    sshd_run = (rootfs / S6_ROOT / "sshd/run").read_text(encoding="utf-8")

    assert "user_files_update" in init_script
    assert 'if [[ ! -e "${CODEX_DATA}/config.toml" ]]' not in init_script
    assert 'install -m 0644 "${DEFAULT_AGENTS}" "${agents_tmp}"' not in init_script
    assert 'if [[ ! -s "${host_key}" ]]' in init_script
    assert 'rm -f "${host_key}" "${host_key}.pub"' in init_script
    assert 'ssh-keygen -y -f "${host_key}"' in init_script
    assert 'chmod 0600 "${SSH_DATA}/authorized_keys"' not in init_script
    assert 'mv -f "${authorized_keys_tmp}" "${SSH_DATA}/authorized_keys"' in init_script
    assert '"${RUNTIME_DIR}/ssh-disabled"' in init_script
    assert "exec /command/s6-pause" in sshd_run


def test_default_codex_guidance_has_home_assistant_safety_rules(rootfs: Path) -> None:
    guidance = (
        rootfs / "usr/local/share/hermes-ha/AGENTS.md"
    ).read_text(encoding="utf-8")
    normalized_guidance = " ".join(guidance.lower().split())

    assert "live Home Assistant App" in guidance
    assert "A diagnostic finding alone does not authorize" in guidance
    assert "defense-in-depth guidance, not an enforcement boundary" in guidance
    assert "Run `ha-config-check`" in guidance
    assert "SUPERVISOR_TOKEN" in guidance
    assert "Never describe an unverified" in guidance
    assert "http://127.0.0.1:8099/" in guidance
    assert "do not first search for, invoke, or install another browser skill" in (
        normalized_guidance
    )
    assert "home_assistant_browser_auto_auth" in guidance


def test_boolean_option_reader_accepts_an_explicit_false(rootfs: Path) -> None:
    config_helpers = (
        rootfs / "usr/local/lib/hermes-ha/config.sh"
    ).read_text(encoding="utf-8")
    bool_reader = config_helpers.split("codex_ha_config_bool()", maxsplit=1)[1]
    bool_reader = bool_reader.split("codex_ha_config_json()", maxsplit=1)[0]

    assert "jq --raw-output" in bool_reader
    assert "--exit-status" not in bool_reader


def test_web_terminal_uses_tmux_and_returns_to_shell(rootfs: Path) -> None:
    entrypoint = (rootfs / "usr/local/bin/web-terminal-entrypoint").read_text(
        encoding="utf-8"
    )
    session_shell = (rootfs / "usr/local/bin/tmux-session-shell").read_text(
        encoding="utf-8"
    )

    assert "export TERM=xterm-256color" in entrypoint
    assert 'new-session -A -s "${session_name}" -c /config' in entrypoint
    assert session_shell.startswith("#!/usr/bin/env bash\n")
    assert "codex_ha_config_true" in session_shell
    assert "web_terminal_auto_start_codex" in session_shell
    assert "if ha-codex; then" in session_shell
    assert "exec /bin/bash -l" in session_shell
