import requests

SUPERVISOR_TOKEN = None
with open("/opt/Homeassistant-hermes/.env", "r") as f:
    for line in f:
        if line.startswith("SUPERVISOR_TOKEN="):
            SUPERVISOR_TOKEN = line.split("=", 1)[1].strip()

headers = {
    "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
    "Content-Type": "application/json",
}
HA_API_URL = "http://192.168.0.86:8123/api"

tmpl = "{% for s in states.light %}{{ s.entity_id }} | {{ area_name(s.entity_id) }} | {{ area_id(s.entity_id) }}\n{% endfor %}"
resp = requests.post(f"{HA_API_URL}/template", headers=headers, json={"template": tmpl}, timeout=5)
print(resp.text)
