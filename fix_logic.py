import re
import os

mcp_file = "hermes_home_assistant/rootfs/usr/local/bin/ha_mcp_server.py"
agent_file = "hermes_home_assistant/rootfs/usr/local/bin/gemini_agent.py"

# --- Fix ha_mcp_server.py ---
with open(mcp_file, "r", encoding="utf-8") as f:
    mcp_content = f.read()

mcp_target = '"description": "Fetch current state and attributes of a Home Assistant entity."'
mcp_replacement = '"description": "Fetch current state of an entity. To get a comprehensive summary of all smart home devices, pass \'all\' as the entity_id."'
mcp_content = mcp_content.replace(mcp_target, mcp_replacement)

with open(mcp_file, "w", encoding="utf-8") as f:
    f.write(mcp_content)


# --- Fix gemini_agent.py ---
with open(agent_file, "r", encoding="utf-8") as f:
    agent_content = f.read()

# 1. Add off_devices = []
target1 = """    active_switches = []
    open_sensors = []
    low_batteries = []"""
replacement1 = """    active_switches = []
    open_sensors = []
    low_batteries = []
    off_devices = []"""
agent_content = agent_content.replace(target1, replacement1)

# 2. Inject area prefixing logic right after name is extracted
target2 = """        name = attrs.get("friendly_name", eid)
        unit = str(attrs.get("unit_of_measurement", "")).strip()"""
replacement2 = """        name = attrs.get("friendly_name", eid)
        _area = area_map.get(eid)
        if _area and _area.lower() not in ["none", "null", "로컬", "server"]:
            name = f"[{_area}] {name}"
            
        unit = str(attrs.get("unit_of_measurement", "")).strip()"""
agent_content = agent_content.replace(target2, replacement2)

# 3. Clean up the old area logic inside is_temp/is_hum
target3 = """                # HA 영역(Area) 등록명이 지정되어 있으면 우선 적용 (예: "작은방"), 없으면 친화적 이름 정제
                area_name = area_map.get(eid)
                if area_name and area_name.lower() not in ["none", "null", "로컬", "server"]:
                    base_room = area_name
                else:
                    base_room = name.replace("온도습도계", "").replace("온도", "").replace("습도", "").replace("  ", " ").strip()
                    if not base_room:
                        base_room = name"""
replacement3 = """                # 이름에 이미 [영역]이 포함되어 있으면 그대로 사용
                if name.startswith("[") and "] " in name:
                    base_room = name.split("] ", 1)[0][1:]
                else:
                    base_room = name.replace("온도습도계", "").replace("온도", "").replace("습도", "").replace("  ", " ").strip()
                    if not base_room:
                        base_room = name"""
agent_content = agent_content.replace(target3, replacement3)

# 4. Modify active_lights and switches to collect off_devices
pattern4 = re.compile(
    r'        # 2\. 켜진 조명\n'
    r'        elif eid_lower\.startswith\("light\."\) and st == "on":\n'
    r'            active_lights\.append\(name\)\n\n'
    r'        # 3\. 켜진 스위치/가전\n'
    r'        elif eid_lower\.startswith\("switch\."\) and st == "on":\n'
    r'            active_switches\.append\(name\)'
)

replacement4 = """        # 2. 조명
        elif eid_lower.startswith("light."):
            if st == "on":
                active_lights.append(name)
            else:
                off_devices.append(name)

        # 3. 스위치/가전
        elif eid_lower.startswith("switch."):
            if st == "on":
                active_switches.append(name)
            else:
                off_devices.append(name)"""
agent_content = pattern4.sub(replacement4, agent_content)

# 5. Append off_devices to summary
target5 = """    if low_batteries:
        lines.append(f"🪫 **배터리 교체 필요 ({len(low_batteries)}개)**:")
        lines.append(f"  • {', '.join(low_batteries)}")
        lines.append("")"""
replacement5 = """    if low_batteries:
        lines.append(f"🪫 **배터리 교체 필요 ({len(low_batteries)}개)**:")
        lines.append(f"  • {', '.join(low_batteries)}")
        lines.append("")

    if off_devices:
        lines.append(f"💤 **꺼진 기기 ({len(off_devices)}개)**: " + ", ".join(off_devices[:15]))
        lines.append("")"""
agent_content = agent_content.replace(target5, replacement5)

with open(agent_file, "w", encoding="utf-8") as f:
    f.write(agent_content)

print("Done")
