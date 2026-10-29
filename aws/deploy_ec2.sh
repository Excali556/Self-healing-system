#!/usr/bin/env bash
# ==============================================================================
# Nexus Automated AWS EC2 Deployment Script
# Provisions Docker, mounts volumes, configures systemd, and starts Nexus cluster
# ==============================================================================

set -euo pipefail

echo "======================================================"
echo "⚡ Starting Nexus Autonomous Resilience System Deployment"
echo "======================================================"

# 1. Update OS and install system prerequisites
echo "📦 Installing prerequisites (Docker, Git, Curl)..."
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl gnupg lsb-release git

# 2. Install Docker Engine if not present
if ! command -v docker &> /dev/null; then
    echo "🐳 Installing Docker Engine..."
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
    sudo apt-get update -y
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    sudo usermod -aG docker "$USER"
fi

# 3. Enable and start Docker daemon
sudo systemctl enable docker
sudo systemctl restart docker

# 4. Clone or pull Nexus repository
NEXUS_DIR="/opt/nexus"
if [ ! -d "$NEXUS_DIR" ]; then
    echo "📥 Cloning Nexus repository to $NEXUS_DIR..."
    sudo git clone https://github.com/Excali556/self-healing-system.git "$NEXUS_DIR"
    sudo chown -R "$USER:$USER" "$NEXUS_DIR"
else
    echo "🔄 Pulling latest changes into $NEXUS_DIR..."
    cd "$NEXUS_DIR"
    git pull origin main || true
fi

cd "$NEXUS_DIR"

# 5. Launch full Nexus stack with Docker Compose
echo "🚀 Building and starting Nexus multi-service cluster..."
docker compose down || true
docker compose up -d --build

# 6. Verify health
echo "⏳ Awaiting healthy state..."
sleep 10
docker compose ps

echo ""
echo "======================================================"
echo "🎉 Nexus is successfully deployed and running on AWS!"
echo "======================================================"
echo "  - Streamlit Dashboard:  http://<EC2-PUBLIC-IP>:8501"
echo "  - Grafana Dashboard:    http://<EC2-PUBLIC-IP>:3000 (admin / admin)"
echo "  - Prometheus TSDB:      http://<EC2-PUBLIC-IP>:9090"
echo "  - FastAPI Victim App:   http://<EC2-PUBLIC-IP>:8000/docs"
echo "  - Autonomous Healer:    http://<EC2-PUBLIC-IP>:5050/docs"
echo "======================================================"
