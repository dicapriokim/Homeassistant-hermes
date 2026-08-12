import os
import shutil

def deploy():
    print("Deploying Home Assistant Add-on files...")
    
    # 윈도우 PowerShell의 UTF-8 BOM 인코딩 문제 해결을 위해 utf-8-sig로 읽고 utf-8(No BOM)로 저장
    if os.path.exists("sshd_config"):
        with open("sshd_config", "r", encoding="utf-8-sig") as f:
            sshd_content = f.read()
        # UTF-8 No BOM 으로 작성
        with open("sshd_config", "w", encoding="utf-8") as f:
            f.write(sshd_content)
        shutil.copy("sshd_config", "hermes_home_assistant/rootfs/etc/ssh/sshd_config")
        print("- sshd_config deployed successfully (UTF8NoBOM).")
        
    if os.path.exists("options.json"):
        with open("options.json", "r", encoding="utf-8-sig") as f:
            options_content = f.read()
        # UTF-8 No BOM 으로 작성
        with open("options.json", "w", encoding="utf-8") as f:
            f.write(options_content)
        shutil.copy("options.json", "hermes_home_assistant/rootfs/data/options.json")
        print("- options.json deployed successfully (UTF8NoBOM).")

    print("Deployment complete!")

if __name__ == "__main__":
    deploy()
