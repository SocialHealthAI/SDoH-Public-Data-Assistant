"""Product-owned opening chat bubble. No LLM."""
from __future__ import annotations

from sdoh_core.requirements_file import is_unspecified_document_path

HELP_TEXT = """Welcome, I am the SDoH AI Public Data Assistant. I can help you with data exploration and analysis queries for public data sources.
I can also help you with updating an "AI Solution Requirements Definition" with public data sources information and data availability.

To explore and analyze data you can:
1. **Discover indicators** — Search across connected public repositories for variables that match your topic (for example diabetes prevalence, opioid prescribing, or social isolation).
2. **Fetch observations** — Pull values for counties, states, ZIP Code Tabulation Areas, places, or census tracts for a chosen year.
3. **Analyze** — Run correlation, regression, descriptive statistics, or simple forecasts on wide tables the agent assembles.
4. **Visualize** — Generate charts or choropleth maps.

If you specify an "AI Solution Requirements Definition" file I will help you with the **Data Inventory** and **Data Assessment** sections. The file must have a Problem Definition section. To work on the "AI Solution Requirements Definition" you can ask me to:
1. Summarize the key data analysis needed.
2. Update the data sections based on analyzing the data requirements in the Problem Definition.
3. Add data items to the data sections based on your exploration and analysis."""


def _first_usable_paragraph(body: str | None) -> str:
    if not body:
        return ""
    for line in body.splitlines():
        text = line.strip()
        if not text or text.startswith("#") or text.lower() in {
            "to be defined",
            "tbd",
            "placeholder",
        }:
            continue
        return text
    return ""


def build_welcome_message(doc_path: str, file_helper, document_tool) -> str:
    help_text = HELP_TEXT.strip()
    if is_unspecified_document_path(doc_path):
        return help_text
    if not file_helper.exists(doc_path):
        return (
            f"{help_text}\n\nThere is no requirements file at `{doc_path}` yet. "
            "Name a file under sdoh_documents/ when you want document updates."
        )
    inventory = document_tool.current_inventory(doc_path)
    assessment = document_tool.current_assessment(doc_path)
    bits = [f"We are continuing with `{doc_path}`."]
    inv_sum = _first_usable_paragraph(inventory)
    ass_sum = _first_usable_paragraph(assessment)
    if inv_sum:
        bits.append(f"Data Inventory: {inv_sum}")
    else:
        bits.append("The Data Inventory section is still empty or a placeholder.")
    if ass_sum:
        bits.append(f"Data Assessment: {ass_sum}")
    else:
        bits.append("The Data Assessment section is still empty or a placeholder.")
    return f"{help_text}\n\n{' '.join(bits)}"
