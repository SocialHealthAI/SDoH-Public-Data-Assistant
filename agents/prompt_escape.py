"""Literal-brace escaping for LangChain ChatPromptTemplate (current GitHub sdoh_core)."""


def escape_prompt_braces(text: str) -> str:
    """Double `{` / `}` so f-string templates do not treat JSON examples as variables.

    Drop call sites once sdoh_core ToolCallingAgent uses a literal SystemMessage
    and that version is installed from GitHub.
    """
    return text.replace("{", "{{").replace("}", "}}")
