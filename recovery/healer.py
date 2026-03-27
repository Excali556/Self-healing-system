import subprocess
import time

TARGET = "app-service"

def check_container():
    try:
        # We use --filter and --quiet to get just the ID if it's running
        cmd = ["docker", "ps", "--filter", f"name={TARGET}", "--filter", "status=running", "--format", "{{.Names}}"]
        result = subprocess.check_output(cmd).decode().strip()

        if TARGET in result:
            print(f"💚 [HEALER] {TARGET} is pulse-checked and healthy.")
        else:
            print(f"🚨 [HEALER] {TARGET} is NOT running! Awaiting Docker auto-restart...")
            
    except subprocess.CalledProcessError as e:
        print(f"❌ [HEALER] Failed to contact Docker daemon: {e}")

if __name__ == "__main__":
    print(f"🩺 Healer monitoring started for: {TARGET}")
    while True:
        check_container()
        time.sleep(10)