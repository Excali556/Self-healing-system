# 🚀 Nexus: Self-Healing Chaos Lab

A high-availability, containerized system designed to simulate real-world failures and autonomous recovery.  
This project demonstrates **Resilience Engineering** by combining chaos engineering principles with automated self-healing infrastructure.

At its core, Nexus pits an intelligent **Chaos Monkey** against a cluster of containerized FastAPI services, validating system robustness under failure conditions.

---

## 🧠 Architecture Overview

The system is composed of four core layers:

### 🧩 1. The Victim (Application Layer)
- A containerized FastAPI service simulating a production workload
- Exposes `/` and `/health` endpoints
- Injects **random failures (HTTP 500)** to mimic real-world instability

---

### 💣 2. The Villain (Chaos Layer)
- A Python-based Chaos Monkey
- Randomly kills or disrupts running containers
- Uses Docker socket (`/var/run/docker.sock`) for direct container control

---

### 🛡️ 3. The Hero (Recovery Layer)
- Continuously monitors system state
- Detects service failures
- Relies on Docker restart policies (`unless-stopped`) for automated recovery
- Logs system health and recovery events

---

### 📊 4. Nexus Dashboard (Observability Layer)
- Built using Streamlit with modern UI (Glassmorphism)
- Provides real-time insights into:
  - Node status (UP/DOWN)
  - Cluster health
  - System latency
- Visualizes stability using time-series metrics

---

## 🛠️ Key Features

### ⚡ High Availability
- Supports horizontal scaling (`--scale app=N`)
- Simulates multi-node distributed systems

---

### 🔁 Auto-Healing Infrastructure
- Automatically recovers from failures using Docker restart policies
- Validates resilience under continuous disruption

---

### 🔥 Chaos Engineering
- Injects controlled failures into the system
- Tests system robustness and fault tolerance

---

### 📈 Real-Time Observability
- Live dashboard displaying cluster health
- Tracks node uptime, failures, and recovery cycles

---

### 🧪 Stress Testing & Metrics
- Visualizes system stability under repeated failures
- Helps understand degradation and recovery patterns

---

### 🐳 Docker-in-Docker Control
- Securely mounts Docker socket
- Enables programmatic infrastructure manipulation

---

## 🚀 Getting Started

### 📌 Prerequisites
- Docker
- Docker Compose
- Python 3.10+

---

### ⚙️ Setup

```bash
git clone https://github.com/your-username/self-healing-system.git
cd self-healing-system
