import docker
import time
import random

client = docker.from_env()

while True:
    time.sleep(10)
    # Find all containers that belong to our "app" service
    all_apps = client.containers.list(filters={"name": "app"})
    
    if all_apps:
        target = random.choice(all_apps)
        print(f"🔥 [CHAOS] Picking a fight with: {target.name}")
        target.restart()
    else:
        print("📭 [CHAOS] No apps found to harass.")