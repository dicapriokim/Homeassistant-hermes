import requests
import os

SUPERVISOR_TOKEN = None
with open("D:/Antigravity/hermes/.env", "r") as f:
    for line in f:
        if line.startswith("SUPERVISOR_TOKEN="):
            SUPERVISOR_TOKEN = line.split("=", 1)[1].strip()

headers = {
    "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
    "Content-Type": "application/json",
}

HA_API_URL = "http://192.168.0.86:8123/api"

try:
    resp = requests.get(f"{HA_API_URL}/states", headers=headers, timeout=5)
    states = resp.json()
    print(f"Total states: {len(states)}")
    for state in states:
        eid = state.get("entity_id", "").lower()
        name = state.get("attributes", {}).get("friendly_name", "").lower()
        if "무드" in name or "mood" in eid or "mood" in name or "무드" in eid:
            print(f"Found: {eid} - {name} - State: {state.get('state')}")
except Exception as e:
    print(f"Error fetching states: {e}")

try:
    url = f"{HA_API_URL}/config/entity_registry"
    resp = requests.get(url, headers=headers, timeout=5)
    print("\nExposed entities:")
    reg_data = resp.json()
    for entry in reg_data:
        eid = entry.get("entity_id", "")
        options = entry.get("options", {})
        conv_options = options.get("conversation", {})
        should_expose = conv_options.get("should_expose")
        name = entry.get("original_name") or entry.get("name") or eid
        if "무드" in name.lower() or "mood" in eid.lower():
            print(f"Entity: {eid}, Expose: {should_expose}, Disabled: {entry.get('disabled_by')}")
except Exception as e:
    print(f"Error fetching exposed entities: {e}")
