"""DataDocumentTool propose does not write until apply."""
from pathlib import Path

import pytest

from data_document import DataDocumentTool
from sdoh_core.requirements_file import (
    UNSPECIFIED_FILE_MESSAGE,
    RequirementsFileHelper,
)


def test_propose_inventory_does_not_write(tmp_path: Path):
    helper = RequirementsFileHelper(tmp_path)
    helper.write(
        "doc.md",
        "# AI Solution Requirements Definition\n\n## 1. Problem Definition\n\nDiabetes.\n",
        confirm=True,
    )
    tool = DataDocumentTool(helper)
    bound = tool.tool_for_heading("2. Data Inventory")

    proposed = bound.propose_section("doc.md", "* PLACES diabetes\n")

    assert helper.exists("doc.md")
    assert "PLACES" not in helper.read("doc.md")
    assert proposed["wrote"] is False
    assert proposed["heading"] == "2. Data Inventory"
    assert "PLACES" in proposed["review_markdown"]

    bound.apply_proposed_write(proposed, confirm=True)
    assert "PLACES" in helper.read("doc.md")
    assert "Diabetes" in helper.read("doc.md")


def test_propose_folder_only_path_raises(tmp_path: Path):
    helper = RequirementsFileHelper(tmp_path)
    tool = DataDocumentTool(helper)

    with pytest.raises(ValueError, match="folder"):
        tool.propose_section("sdoh_documents/", "body")
    assert "file" in UNSPECIFIED_FILE_MESSAGE.lower()
