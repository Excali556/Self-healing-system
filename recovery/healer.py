from flask import Flask, request, jsonify
import subprocess
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Global tracker for failed attempts
healing_attempts = {}

def run_remediation(playbook_name, target_host):
    """Executes a specific Ansible playbook."""
    playbook_path = f"playbooks/{playbook_name}"
    try:
        # Added -c docker to use Docker connector instead of SSH
        result = subprocess.run(
            ['ansible-playbook', playbook_path, '-c', 'docker', '-i', f"{target_host},"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception as e:
        logging.error(f"Failed to run Ansible: {e}")
        return False

def run_common_fix(action, target_host, service=None):
    """Executes common_fixes.yml with variables."""
    cmd = [
        'ansible-playbook', 
        'playbooks/common_fixes.yml',
        '-c', 'docker',
        '-i', f"{target_host},",
        '--extra-vars', f"repair_action={action} service_name={service}"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0

def smart_heal(instance, action, service=None):
    """Retries healing up to 3 times."""
    key = f"{instance}_{action}_{service}"
    count = healing_attempts.get(key, 0)
    
    if count >= 3:
        logging.critical(f"LOOP DETECTED: {key} failed 3 times. Stopping.")
        return False
        
    success = run_common_fix(action, instance, service)
    if not success:
        healing_attempts[key] = count + 1
    else:
        healing_attempts[key] = 0 # Reset on success
    return success

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"}), 200

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    if not data:
        return jsonify({"error": "No data received"}), 400

    logging.info(f"Alert received: {data.get('status')}")

    for alert in data.get('alerts', []):
        labels = alert.get('labels', {})
        alert_name = labels.get('alertname')
        instance = labels.get('instance') 
        status = alert.get('status')

        if status == "firing":
            logging.info(f"Processing {alert_name} for {instance}...")
            
            if alert_name == "TargetDown":
                run_remediation('restart_service.yml', instance)
            
            elif alert_name == "DiskFillingUp":
                smart_heal(instance, "clear_logs")
                
            elif alert_name == "HighMemoryUsage":
                smart_heal(instance, "flush_ram")

    return jsonify({"status": "processed"}), 200

if __name__ == '__main__':
    # This must be the VERY LAST thing in the file
    app.run(host='0.0.0.0', port=5000, debug=True)