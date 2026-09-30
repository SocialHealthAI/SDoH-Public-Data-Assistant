"""
Product audit prompt for the Public Data Assistant.

Uses sdoh_core.AuditAgent for the LLM call; this module owns the review criteria.
"""
from typing import List

from sdoh_core.audit_agent import AuditAgent as CoreAuditAgent
from sdoh_core.llm_config import llm_content_to_text

AUDIT_SYSTEM_PROMPT = """You are an audit agent tasked with reviewing the reasoning and output of a data analytics AI assistant.

Your responsibilities:
1. Verify logical consistency in the reasoning steps
2. Check if the tools were used appropriately
3. Assess whether the final answer adequately addresses the user's request
4. Identify any potential errors, omissions, or areas for improvement
5. Evaluate if the response is clear, accurate, and actionable

Provide a structured audit report with:
- **Strengths**: What was done well
- **Issues Found**: Any problems, inconsistencies, or errors (if none, state "None identified")
- **Recommendations**: Suggestions for improvement, including improvements to user request.

Be constructive, specific, and focus on substantive issues rather than minor stylistic preferences."""


def format_tool_steps_for_audit(
    tool_descriptions: str, intermediate_steps: List
) -> str:
    """Flatten tool catalog + intermediate steps for Core AuditAgent.conversation."""
    steps_desc = "\n".join(
        [
            f"**Step {i}:**\n- Tool: {step[0].tool}\n"
            f"- Input: {step[0].tool_input}\n"
            f"- Observation: {llm_content_to_text(step[1])}\n"
            for i, step in enumerate(intermediate_steps, 1)
        ]
    )
    return (
        "The answering agent had access to the following tools:\n\n"
        f"{tool_descriptions}\n\n"
        "**INTERMEDIATE REASONING STEPS:**\n"
        f"{steps_desc}"
    )


class AuditAgent(CoreAuditAgent):
    """Public-data audit agent with a fixed product system prompt."""

    def __init__(
        self,
        model_name: str | None = None,
        provider: str | None = None,
        temperature: float = 0.2,
    ) -> None:
        super().__init__(
            AUDIT_SYSTEM_PROMPT,
            model_name=model_name,
            provider=provider,
            temperature=temperature,
        )

    def audit_turn(
        self,
        user_prompt: str,
        tool_descriptions: str,
        intermediate_steps: List,
        final_answer: str,
    ) -> str:
        """Audit a public-data turn (tools + steps + final answer)."""
        conversation = format_tool_steps_for_audit(
            tool_descriptions, intermediate_steps
        )
        return self.audit(user_prompt, conversation, final_answer)
