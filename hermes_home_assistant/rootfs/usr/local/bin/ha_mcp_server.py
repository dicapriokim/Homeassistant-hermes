#!/usr/bin/env python3
"""
Hermes Agent MCP (Model Context Protocol) Server for Home Assistant
Provides PC clients (Hermes Desktop / Antigravity IDE) with direct access to
YAML validation, safe auto-backup file updates, rollback, and entity state inspection.
"""

import sys
import os
import glob
import json
import logging

# Dynamically discover all site-packages in system
for search_dir in ["/usr", "/opt", "/root", "/var"]:
    for sp in glob.glob(f"{search_dir}/**/site-packages", recursive=True) + glob.glob(f"{search_dir}/**/dist-packages", recursive=True):
        if sp not in sys.path:
            sys.path.insert(0, sp)

from gemini_agent import auto_backup_yaml, log_yaml_change_history, rollback_yaml, check_ha_config, get_device_state, read_yaml_file, backup_and_update_yaml, delete_automation_or_yaml

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("HermesMCP")

def send_json(data):
    sys.stdout.write(json.dumps(data) + "\n")
    sys.stdout.flush()

def handle_mcp_request(request):
    req_id = request.get("id")
    method = request.get("method")
    params = request.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "hermes-ha-mcp-server",
                    "version": "1.0.0"
                }
            }
        }

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "ha_core_check",
                        "description": "Run Home Assistant configuration syntax check (ha core check).",
                        "inputSchema": {
                            "type": "object",
                            "properties": {}
                        }
                    },
                    {
                        "name": "ha_get_device_state",
                        "description": "Fetch current state of an entity. To get a comprehensive summary of all smart home devices, pass 'all' as the entity_id.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "entity_id": {"type": "string", "description": "Entity ID (e.g. light.living_room)"}
                            },
                            "required": ["entity_id"]
                        }
                    },
                    {
                        "name": "ha_read_yaml",
                        "description": "Read content of a Home Assistant YAML configuration file (e.g. /config/automations.yaml, /config/configuration.yaml).",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "file_path": {"type": "string", "description": "Path to YAML file (e.g. /config/automations.yaml, automations.yaml, configuration.yaml)"}
                            },
                            "required": []
                        }
                    },
                    {
                        "name": "ha_update_yaml",
                        "description": "Safely update, modify, or create a YAML configuration or automation block with auto-backup and syntax check.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "file_path": {"type": "string", "description": "Path to YAML file (e.g. /config/automations.yaml)"},
                                "new_content": {"type": "string", "description": "New YAML code content to apply"},
                                "start_line": {"type": "integer", "description": "Starting line number (1-indexed)"},
                                "end_line": {"type": "integer", "description": "Ending line number (1-indexed)"},
                                "root_cause": {"type": "string", "description": "Reason for change"},
                                "fix_applied": {"type": "string", "description": "Fix or change description"},
                                "expected_outcome": {"type": "string", "description": "Expected outcome"}
                            },
                            "required": ["new_content", "start_line", "end_line"]
                        }
                    },
                    {
                        "name": "ha_delete_automation",
                        "description": "Delete an automation or YAML block by line range [start_line, end_line] or by automation_id via Home Assistant REST API.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "file_path": {"type": "string", "description": "Path to YAML file (e.g. /config/automations.yaml)"},
                                "start_line": {"type": "integer", "description": "Starting line number"},
                                "end_line": {"type": "integer", "description": "Ending line number"},
                                "automation_id": {"type": "string", "description": "Automation entity ID or ID string (e.g. geosil_gaseubgi)"}
                            },
                            "required": []
                        }
                    },
                    {
                        "name": "ha_rollback_yaml",
                        "description": "Restore the specified YAML file from its latest backup in /config/hermes/backups/.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "file_path": {"type": "string", "description": "Path to YAML file (e.g. /config/automations.yaml)"}
                            },
                            "required": ["file_path"]
                        }
                    }
                ]
            }
        }

    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if tool_name == "ha_core_check":
            res = check_ha_config()
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": res}]}}

        elif tool_name == "ha_get_device_state":
            entity_id = arguments.get("entity_id")
            res = get_device_state(entity_id)
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": res}]}}

        elif tool_name == "ha_read_yaml":
            file_path = arguments.get("file_path") or "/config/automations.yaml"
            res = read_yaml_file(file_path)
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": res}]}}

        elif tool_name == "ha_update_yaml":
            file_path = arguments.get("file_path") or "/config/automations.yaml"
            new_content = arguments.get("new_content", "")
            start_line = arguments.get("start_line", 0)
            end_line = arguments.get("end_line", 0)
            root_cause = arguments.get("root_cause", "Natural language user edit request")
            fix_applied = arguments.get("fix_applied", "Updated YAML content")
            expected_outcome = arguments.get("expected_outcome", "YAML updated successfully")
            res = backup_and_update_yaml(file_path, new_content, start_line, end_line, root_cause, fix_applied, expected_outcome)
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": res}]}}

        elif tool_name == "ha_delete_automation":
            file_path = arguments.get("file_path") or "/config/automations.yaml"
            start_line = arguments.get("start_line", 0)
            end_line = arguments.get("end_line", 0)
            automation_id = arguments.get("automation_id", "")
            res = delete_automation_or_yaml(file_path, start_line, end_line, automation_id)
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": res}]}}

        elif tool_name == "ha_rollback_yaml":
            file_path = arguments.get("file_path")
            res = rollback_yaml(file_path)
            return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": res}]}}

        else:
            return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown tool {tool_name}"}}

    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": "Method not found"}}

def main():
    logger.info("Hermes MCP Server listening on stdio...")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = handle_mcp_request(req)
            if resp:
                send_json(resp)
        except Exception as e:
            logger.error(f"Error handling MCP request: {e}")

if __name__ == "__main__":
    main()
