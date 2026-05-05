"""
Data Commons Assistant - Main Streamlit Application
"""
import streamlit as st
import os
import re

from chart_renderer import ChartRenderer
from map_renderer import MapRenderer
from react_agent import ReActAgent
from audit_agent import AuditAgent

##############################################################
#   Set up agent
##############################################################

datacommons_uri = os.environ.get("DATACOMMONS_URI")
if not datacommons_uri:
    st.error("No DATACOMMONS_URI found. Please set the DATACOMMONS_URI environment variable.")
    st.stop()

# Initialize agent & agents
agent = ReActAgent(
    mcp_uri=datacommons_uri,
    model_name="gpt-5.2",
    #model_name="gpt-5-mini",
    max_iterations=10,
    system_prompt_path="agent_system_prompt.txt"
)
audit_agent = AuditAgent(model_name="gpt-4o", temperature=0.0)
chart_renderer = ChartRenderer()
map_renderer = MapRenderer()

##############################################################
#   Streamlit App Logic
##############################################################

def escape_markdown(text):
    """Escape markdown special characters but preserve tables and intentional formatting."""
    # Escape lines that are purely === or --- (common in statistical output)
    text = re.sub(r'^(=+)$', r'\\\1', text, flags=re.MULTILINE)
    text = re.sub(r'^(-+)$', r'\\\1', text, flags=re.MULTILINE)
    
    # Escape lines that start with *** or ___ (alternative horizontal rules)
    text = re.sub(r'^(\*{3,})$', r'\\\1', text, flags=re.MULTILINE)
    text = re.sub(r'^(_{3,})$', r'\\\1', text, flags=re.MULTILINE)
    
    # Escape # at start of lines (headers)
    text = re.sub(r'^(#{1,6})\s', r'\\\1 ', text, flags=re.MULTILINE)
    
    return text


st.title("🧠 Data Commons Assistant")

# Initialize Session State
if "messages" not in st.session_state:
    st.session_state["messages"] = [{"role": "assistant", "content": "How can I help you?"}]
if "last_result" not in st.session_state:
    st.session_state["last_result"] = None
if "show_audit" not in st.session_state:
    st.session_state["show_audit"] = False
if "show_steps" not in st.session_state:
    st.session_state["show_steps"] = False

# --- SIDEBAR ---
with st.sidebar:
    st.header("Controls")
    
    if st.button("Clear message history", use_container_width=True):
        st.session_state["messages"] = [{"role": "assistant", "content": "How can I help you?"}]
        st.session_state["last_result"] = None
        st.session_state["show_audit"] = False
        st.session_state["show_steps"] = False
        st.rerun()

    if st.session_state["last_result"] is not None:
        st.divider()
        st.subheader("Analysis Tools")
        
        # Toggle buttons
        if st.button("🧩 View Logic Steps", use_container_width=True):
            st.session_state["show_steps"] = not st.session_state["show_steps"]
            st.session_state["show_audit"] = False
            
        if st.button("🔍 Run Audit", type="secondary", use_container_width=True):
            st.session_state["show_audit"] = True
            st.session_state["show_steps"] = False

# --- MAIN CHAT AREA ---

# 1. Display Message History
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 2. PERSISTENT VISUALIZATION RENDERING
# Only render if we're not showing steps or audit (which would interfere)
last_result = st.session_state["last_result"]
if last_result and (last_result.get("chart_code") or last_result.get("map_code")):
    if not st.session_state["show_steps"] and not st.session_state["show_audit"]:
        explanation = last_result["result"].get("explanation")
        if last_result.get("map_code"):
            map_renderer.render_from_code(
                last_result["map_code"],
                explanation=None,
                geojson_ref=last_result.get("map_geojson_ref"),
                outline_geojson_ref=last_result.get("map_outline_geojson_ref"),
                data_variables=last_result.get("map_data"),
            )
        if last_result.get("chart_code"):
            chart_renderer.render_from_code(last_result["chart_code"], explanation=None)

# 3. Logic Steps Display with Header
if st.session_state["show_steps"] and st.session_state["last_result"]:
    st.divider()
    st.header("🧩 Logic Steps")
    steps = st.session_state["last_result"]["result"].get("intermediate_steps", [])
    
    for i, step in enumerate(steps):
        with st.expander(f"Step {i+1}: {step[0].tool}", expanded=True):
            st.markdown(f"**Action Input:** `{step[0].tool_input}`")
            obs = str(step[1])
            if len(obs.splitlines()) > 5:
                obs = "\n".join(obs.splitlines()[:5]) + "\n... (truncated)"
            st.code(obs)

# 4. Audit Display
if st.session_state["show_audit"] and st.session_state["last_result"]:
    st.divider()
    last = st.session_state["last_result"]
    with st.spinner("Conducting audit..."):
        try:
            st.subheader("🔍 Audit Report")
            audit_report = audit_agent.audit(
                tool_descriptions=last["tool_descriptions"],
                user_prompt=last["prompt"],
                intermediate_steps=last["result"].get("intermediate_steps", []),
                final_answer=last["result"].get("output", "")
            )
            st.markdown(audit_report)
            st.caption(f"*Audited by: {audit_agent.llm.model_name}*")
        except Exception as e:
            st.error(f"Audit failed: {e}")

# --- INPUT AREA ---

prompt = st.chat_input("Ask me about Data Commons topics")

if prompt:
    st.session_state["show_audit"] = False
    st.session_state["show_steps"] = False
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    with st.spinner("Processing..."):
        try:
            result = agent.run(prompt)

            # Capture the latest visualization code (chart or map) before rerunning
            chart_tool = agent.get_chart_tool()
            map_tool = agent.get_map_tool()
            saved_chart_code = None
            saved_map_code = None
            saved_map_geojson_ref = None
            saved_map_outline_geojson_ref = None
            saved_map_data = None

            if chart_tool and hasattr(chart_tool, "_latest_result"):
                latest_result = chart_tool._latest_result
                if latest_result and latest_result.get("code_block"):
                    saved_chart_code = latest_result.get("code_block")

            if map_tool and hasattr(map_tool, "_latest_result"):
                latest_result = map_tool._latest_result
                if latest_result:
                    if latest_result.get("code_block"):
                        saved_map_code = latest_result.get("code_block")
                    if latest_result.get("geojson_ref"):
                        saved_map_geojson_ref = latest_result.get("geojson_ref")
                    if latest_result.get("outline_geojson_ref"):
                        saved_map_outline_geojson_ref = latest_result.get("outline_geojson_ref")
                    if latest_result.get("data"):
                        saved_map_data = latest_result.get("data")
            
            st.session_state["last_result"] = {
                "prompt": prompt,
                "result": result,
                "tool_descriptions": agent.get_tool_descriptions_text(),
                "chart_code": saved_chart_code,
                "map_code": saved_map_code,
                "map_geojson_ref": saved_map_geojson_ref,
                "map_outline_geojson_ref": saved_map_outline_geojson_ref,
                "map_data": saved_map_data,
            }
            
            st.session_state.messages.append({
                "role": "assistant", 
                "content": escape_markdown(result.get("output", ""))
            })

            st.rerun()
            
        except Exception as e:
            st.error(f"Error: {e}")
