"""
SDoH Public Data Assistant — Core Streamlit shell plus product charts/maps.
"""
import os

import streamlit as st

from sdoh_core.streamlit_app import AfterTurnHook, AssistantAppConfig, run_assistant_app

from audit_agent import AuditAgent, StreamlitAuditAdapter
from build_data_agent import DEFAULT_DOC_PATH, build_data_agent
from chart_renderer import ChartRenderer
from map_renderer import MapRenderer
from react_agent import collect_viz_extras
from welcome_message import HELP_TEXT, build_welcome_message

datacommons_uri = os.environ.get("DATACOMMONS_URI")
if not datacommons_uri:
    st.error("No DATACOMMONS_URI found. Please set the DATACOMMONS_URI environment variable.")
    st.stop()

agent = build_data_agent(
    mcp_uri=datacommons_uri,
    max_iterations=16,
    system_prompt_path="agent_system_prompt.txt",
    default_doc_path=DEFAULT_DOC_PATH,
)
audit_agent = StreamlitAuditAdapter(AuditAgent(temperature=0.0))
chart_renderer = ChartRenderer()
map_renderer = MapRenderer()


def collect_turn(result: dict) -> dict:
    audit_agent.remember_turn(agent.get_tool_descriptions_text(), result)
    extras = collect_viz_extras(agent.get_chart_tool(), agent.get_map_tool())
    extras["tool_descriptions"] = agent.get_tool_descriptions_text()
    return extras


def render_turn(last_result: dict) -> None:
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


def intro_for_path(doc_path: str) -> str:
    return build_welcome_message(doc_path, agent._helper, agent._document_tool)


run_assistant_app(
    AssistantAppConfig(
        title="🧠 SDoH Public Data Assistant",
        intro_message=HELP_TEXT.strip(),
        chat_placeholder="Ask about public SDoH indicators, places, or analyses",
        file_input_label="Requirements file",
        default_doc_path=DEFAULT_DOC_PATH,
        agent=agent,
        audit_agent=audit_agent,
        file_helper=agent._helper,
        intro_builder=intro_for_path,
        after_turn=AfterTurnHook(collect=collect_turn, render=render_turn),
    )
)
