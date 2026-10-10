"""Welcome builder: no LLM, folder-only path is not a missing file."""
from pathlib import Path

from data_document import DataDocumentTool
from sdoh_core.requirements_file import RequirementsFileHelper
from welcome_message import HELP_TEXT, build_welcome_message


def test_welcome_folder_only_has_no_filename():
    helper = RequirementsFileHelper()
    tool = DataDocumentTool(helper)
    text = build_welcome_message("sdoh_documents/", helper, tool)

    assert "Welcome, I am the SDoH AI Public Data Assistant" in text
    assert "ai-solution-requirements-definition.md" not in text
    assert "continuing with" not in text.lower()
    assert HELP_TEXT.strip() in text


def test_welcome_missing_file_names_path(tmp_path: Path):
    helper = RequirementsFileHelper(tmp_path)
    tool = DataDocumentTool(helper)
    text = build_welcome_message("draft.md", helper, tool)

    assert "`draft.md`" in text
    assert "no requirements file" in text.lower()


def test_welcome_existing_file_recaps_sections(tmp_path: Path):
    helper = RequirementsFileHelper(tmp_path)
    helper.write(
        "doc.md",
        "# AI Solution Requirements Definition\n\n"
        "## 1. Problem Definition\n\nDiabetes in Indiana.\n\n"
        "## 2. Data Inventory\n\nPLACES diabetes county rates.\n\n"
        "## 3. Data Assessment\n\nto be defined\n",
        confirm=True,
    )
    tool = DataDocumentTool(helper)
    text = build_welcome_message("doc.md", helper, tool)

    assert "continuing with `doc.md`" in text
    assert "PLACES diabetes" in text
    assert "still empty" in text
