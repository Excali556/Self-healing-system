import streamlit as st
import docker
import time
import pandas as pd

st.set_page_config(page_title="Nexus Chaos Control", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    div[data-testid="stMetricValue"] { font-size: 28px; color: #00ffcc !important; }
    div[data-testid="stMetricDelta"] svg { display: none; }
    .status-card {
        background: rgba(255, 255, 255, 0.05);
        padding: 20px;
        border-radius: 15px;
        border-left: 5px solid #00ffcc;
        margin-bottom: 10px;
    }
    .stTable { background-color: transparent !important; }
    h1, h2, h3 { color: #ffffff !important; font-family: 'Courier New', Courier, monospace; }
    </style>
    """, unsafe_allow_html=True)

st.title("⚡ NEXUS: CLUSTER RESILIENCE")
st.write("---")
client = docker.from_env()
if 'history' not in st.session_state:
    st.session_state.history = []
placeholder = st.empty()
while True:
    try:
        containers = client.containers.list(all=True, filters={"name": "app"})
        containers.sort(key=lambda x: x.name)
        
        running_count = sum(1 for c in containers if c.status == "running")
        total_count = len(containers)
        health_pct = (running_count / total_count * 100) if total_count > 0 else 0

        with placeholder.container():
            m1, m2, m3 = st.columns(3)
            m1.metric("CLUSTER UPTIME", f"{health_pct:.0f}%", delta="SYSTEM STABLE" if health_pct > 70 else "CRITICAL")
            m2.metric("ACTIVE NODES", f"{running_count}/{total_count}")
            m3.metric("LATENCY SCAN", "12ms", delta="-2ms")

            st.write("### 🛰️ NODE REPOSITORY")
            cols = st.columns(max(total_count, 1))
            for idx, container in enumerate(containers):
                is_up = container.status == "running"
                status_color = "#00ffcc" if is_up else "#ff4b4b"
                
                with cols[idx]:
                    st.markdown(f"""
                        <div style="background: rgba(255,255,255,0.03); border-radius: 10px; padding: 15px; border-top: 4px solid {status_color}; text-align: center;">
                            <p style="margin:0; font-size: 12px; color: #888;">NODE ID</p>
                            <p style="margin:0; font-weight: bold; color: white;">{container.name.upper()}</p>
                            <p style="margin-top: 10px; font-size: 18px; color: {status_color};">{container.status.upper()}</p>
                        </div>
                    """, unsafe_allow_html=True)
            st.write("---")
            st.write("### 📈 STRESS METRICS")
            st.session_state.history.append({
                "Time": time.strftime("%H:%M:%S"), 
                "Healthy Nodes": running_count
            })
            
            if len(st.session_state.history) > 20:
                st.session_state.history.pop(0)

            df = pd.DataFrame(st.session_state.history).set_index("Time")
            st.area_chart(df, color="#00ffcc", use_container_width=True)

    except Exception as e:
        st.error(f"⚠️ NEXUS LINK SEVERED: {e}")

    time.sleep(2)