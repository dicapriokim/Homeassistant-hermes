import re
import os

agent_file = "hermes_home_assistant/rootfs/usr/local/bin/gemini_agent.py"
with open(agent_file, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add unavailable_devices list
target1 = """    active_switches = []
    open_sensors = []
    low_batteries = []
    off_devices = []"""
replacement1 = """    active_switches = []
    open_sensors = []
    low_batteries = []
    off_devices = []
    unavailable_devices = []"""
content = content.replace(target1, replacement1)

# 2. Collect unavailable
target2 = """        if st in ["unavailable", "unknown"]:
            continue"""
replacement2 = """        if st in ["unavailable", "unknown"]:
            unavailable_devices.append(name)
            continue"""
content = content.replace(target2, replacement2)

# 3. Output in summary
target3 = """    if off_devices:
        lines.append(f"💤 **꺼진 기기 ({len(off_devices)}개)**: " + ", ".join(off_devices[:15]))
        lines.append("")"""
replacement3 = """    if off_devices:
        lines.append(f"💤 **꺼진 기기 ({len(off_devices)}개)**: " + ", ".join(off_devices[:15]))
        lines.append("")

    if unavailable_devices:
        lines.append(f"⚠️ **연결 끊김/사용 불가 ({len(unavailable_devices)}개)**: " + ", ".join(unavailable_devices[:15]))
        lines.append("")"""
content = content.replace(target3, replacement3)

with open(agent_file, "w", encoding="utf-8") as f:
    f.write(content)
print("Updated unavailable logic.")
