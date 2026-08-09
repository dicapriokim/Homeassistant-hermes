#!/usr/bin/env python3
"""
Hermes Agent MCP (Model Context Protocol) Server for Home Assistant
Provides PC clients (Hermes Desktop / Antigravity IDE) with direct access to
YAML validation, safe auto-backup file updates, rollback, and entity state inspection.
"""

import sys
import os
import json
import logging
from gemini_agent import auto_backup_yaml, log_yaml_change_history, rollback_yaml, check_ha_config, get_device_state

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
                        "description": "Fetch current state and attributes of a Home Assistant entity.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "entity_id": {"type": "string", "description": "Entity ID (e.g. light.living_room)"}
                            },
                            "required": ["entity_id"]
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
