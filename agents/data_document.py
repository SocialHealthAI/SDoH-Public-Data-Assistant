"""Data Inventory / Assessment binding of the Core Document Management Tool."""
from __future__ import annotations

from sdoh_core.document_section_tool import DocumentSectionTool
from sdoh_core.requirements_file import RequirementsFileHelper

from framework_sections import resolve_framework_heading

PROBLEM_DEFINITION_HEADING = "1. Problem Definition"


def is_problem_definition_heading(heading: str) -> bool:
    normalized = heading.strip().lower()
    if normalized == "problem definition":
        return True
    if "problem definition" not in normalized:
        return False
    return normalized.startswith("1.") or normalized.startswith("1 ")


class DataDocumentTool(DocumentSectionTool):
    """Document Management binding. Default heading is Problem Definition."""

    def __init__(self, helper: RequirementsFileHelper) -> None:
        super().__init__(
            helper,
            heading=PROBLEM_DEFINITION_HEADING,
            heading_match=is_problem_definition_heading,
        )

    def tool_for_heading(self, heading: str) -> DocumentSectionTool:
        canonical = resolve_framework_heading(heading)
        if not canonical:
            raise ValueError(f"Unknown framework heading: {heading}")
        if is_problem_definition_heading(canonical):
            return self
        return DocumentSectionTool(self.helper, heading=canonical)

    def current_inventory(self, user_path: str) -> str | None:
        return self.tool_for_heading("2. Data Inventory").current_section(user_path)

    def current_assessment(self, user_path: str) -> str | None:
        return self.tool_for_heading("3. Data Assessment").current_section(user_path)
