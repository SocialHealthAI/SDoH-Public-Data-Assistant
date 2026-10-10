"""Construct the Public Data conversation agent on Core ReActAgent."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from langchain_core.tools import StructuredTool

from data_document import DataDocumentTool
from file_baseline import reject_if_disk_changed, stamp_baseline
from framework_sections import UNKNOWN_HEADING_MESSAGE, resolve_framework_heading
from prompt_escape import escape_prompt_braces
from react_agent import build_public_data_tools, tool_descriptions_text
from sdoh_core.agent_types import ToolCallingAgent
from sdoh_core.llm_config import build_chat_model, build_tool_calling_agent, llm_provider
from sdoh_core.react_agent import ReActAgent
from sdoh_core.requirements_file import RequirementsFileHelper, is_unspecified_document_path

PROPOSE_TOOL_NAME = "propose_data_inventory_assessment_update"
DEFAULT_PROPOSE_HEADING = "1. Problem Definition"
DEFAULT_DOC_PATH = "sdoh_documents/"
PROPOSE_MISSING_BODY = (
    "propose_data_inventory_assessment_update requires section_body: the section "
    "markdown without its top-level ## heading. Do not call with no arguments. "
    "Call again with the full body."
)
PROPOSE_TOOL_DESCRIPTION = (
    "Propose creating or replacing one ## section of the AI Solution "
    "Requirements Definition. Required: section_body (section markdown "
    "without its ## heading). Optional: section_heading, one of "
    "1. Problem Definition, 2. Data Inventory, 3. Data Assessment, "
    "4. AI Approach Recommendation, 5. Operational Requirements. "
    "Defaults to 1. Problem Definition. Never call with no arguments. "
    "Returns the proposed section markdown for review. Does not write "
    "the file. Chat reply MUST include that proposed markdown, then "
    "tell them to Confirm write (or Cancel). One section per call; "
    "confirm each dependent update separately."
)


def _propose_validation_error(_error: Exception) -> str:
    return PROPOSE_MISSING_BODY


class DataConversationAgent(ReActAgent):
    """Core conversation agent with public-data tools and full-document context."""

    def __init__(
        self,
        *args: Any,
        chart_tool: Any = None,
        map_tool: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.chart_tool = chart_tool
        self.map_tool = map_tool
        loop_prompt = ToolCallingAgent._default_system_prompt()
        merged = (
            f"{loop_prompt}\n\n{self.system_prompt}"
            if self.system_prompt
            else loop_prompt
        )
        self.system_prompt = escape_prompt_braces(merged)
        self.agent = build_tool_calling_agent(
            self.llm,
            self.tools,
            force_tool=False,
            max_iterations=self.max_iterations,
            system_prompt=self.system_prompt,
        )

    def get_chart_tool(self):
        return self.chart_tool

    def get_map_tool(self):
        return self.map_tool

    def get_tool_descriptions_text(self) -> str:
        return tool_descriptions_text(self.tools)

    def propose_framework_section(self, heading: str, section_body: str) -> str:
        body = (section_body or "").strip()
        if not body:
            return PROPOSE_MISSING_BODY
        canonical = resolve_framework_heading(heading)
        if not canonical:
            return UNKNOWN_HEADING_MESSAGE
        if self._document_tool is None:
            raise ValueError("No document_tool configured")
        bound = self._document_tool.tool_for_heading(canonical)
        proposed = bound.propose_section(self._doc_path, body)
        stamp_baseline(self._helper, self._doc_path, proposed)
        self._this_turn_proposed = proposed
        self._last_proposed = proposed
        return bound.review_observation(proposed)

    def propose_document_update(self, user_path: str, section_body: str) -> Dict[str, Any]:
        proposed = super().propose_document_update(user_path, section_body)
        stamp_baseline(self._helper, user_path, proposed)
        return proposed

    def apply_pending_write(self, proposed: Dict[str, Any]) -> None:
        reject_if_disk_changed(self._helper, proposed)
        super().apply_pending_write(proposed)

    def _document_context(self) -> str:
        path = self._doc_path
        if is_unspecified_document_path(path):
            return super()._document_context()
        if not self._helper.exists(path):
            base = f"Working file: {path} (does not exist yet)."
        else:
            _preamble, sections = self._helper.parse(self._helper.read(path))
            if not sections:
                base = f"Working file: {path} exists but has no ## sections yet."
            else:
                parts = [f"Working file: {path}", "", "Current sections:"]
                for section in sections:
                    body = (section.body or "").strip()
                    parts.append(f"\n## {section.heading}\n{body}")
                base = "\n".join(parts)
        pending = self._last_proposed
        if not pending:
            return base
        review = pending.get("review_markdown") or pending.get("proposed_full_text") or ""
        return (
            f"{base}\n\nA proposed write is waiting for Confirm write "
            f"(not saved yet):\n{review}"
        )


def build_data_agent(
    *,
    mcp_uri: str,
    system_prompt_path: str = "agent_system_prompt.txt",
    documents_root: Path | None = None,
    file_helper: RequirementsFileHelper | None = None,
    document_tool: DataDocumentTool | None = None,
    default_doc_path: str = DEFAULT_DOC_PATH,
    max_iterations: int = 16,
    **kwargs: Any,
) -> DataConversationAgent:
    helper = file_helper or RequirementsFileHelper(documents_root)
    dm_tool = document_tool or DataDocumentTool(helper)
    holder: dict[str, DataConversationAgent] = {}

    provider = kwargs.get("provider") or llm_provider()
    model_name = kwargs.get("model_name")
    temperature = kwargs.get("temperature", 0.0)
    llm = build_chat_model(
        provider=provider,
        model_name=model_name,
        temperature=temperature,
    )
    public_tools, chart_tool, map_tool = build_public_data_tools(mcp_uri, llm)

    def propose_data_inventory_assessment_update(
        section_body: str,
        section_heading: str = DEFAULT_PROPOSE_HEADING,
    ) -> str:
        return holder["agent"].propose_framework_section(section_heading, section_body)

    propose_tool = StructuredTool.from_function(
        func=propose_data_inventory_assessment_update,
        name=PROPOSE_TOOL_NAME,
        description=PROPOSE_TOOL_DESCRIPTION,
    )
    propose_tool.handle_validation_error = _propose_validation_error
    propose_tool.handle_tool_error = True

    agent = DataConversationAgent(
        tools=[*public_tools, propose_tool],
        system_prompt_path=system_prompt_path,
        document_tool=dm_tool,
        file_helper=helper,
        default_doc_path=default_doc_path,
        max_iterations=max_iterations,
        chart_tool=chart_tool,
        map_tool=map_tool,
        **kwargs,
    )
    holder["agent"] = agent
    return agent
