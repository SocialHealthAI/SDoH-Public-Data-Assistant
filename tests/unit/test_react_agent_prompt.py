"""System prompt brace escaping for LangChain ChatPromptTemplate (GitHub sdoh_core)."""
from prompt_escape import escape_prompt_braces


def test_escape_prompt_braces_doubles_json_examples():
    raw = 'data={...} and data={"columns":["x"]}'
    escaped = escape_prompt_braces(raw)
    assert escaped == 'data={{...}} and data={{"columns":["x"]}}'
