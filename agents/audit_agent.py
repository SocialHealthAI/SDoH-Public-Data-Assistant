"""
Audit Agent for reviewing ReAct Agent responses
"""
from typing import Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage


class AuditAgent:
    """
    Audit agent that reviews the ReAct agent's reasoning process and output.
    Uses a different LLM to provide independent verification.
    """
    
    def __init__(self, model_name: str = "gpt-4o", temperature: float = 0.2):
        """
        Initialize the Audit Agent.
        
        Args:
            model_name: OpenAI model name
            temperature: LLM temperature setting
        """
        self.llm = ChatOpenAI(model=model_name, temperature=temperature)
        self.system_prompt = """You are an audit agent tasked with reviewing the reasoning and output of a data analytics AI assistant.

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
    
    def audit(self, user_prompt: str, tool_descriptions: str, intermediate_steps: List, final_answer: str) -> str:
        """
        Conduct an audit of the agent's response.
        
        Args:
            user_prompt: The original user request
            tool_descriptions: Text description of available tools
            intermediate_steps: The reasoning steps taken
            final_answer: The final response generated
            
        Returns:
            Audit report as string
        """
        # Format steps
        steps_desc = "\n".join([
            f"**Step {i}:**\n- Tool: {step[0].tool}\n- Input: {step[0].tool_input}\n- Observation: {step[1]}\n"
            for i, step in enumerate(intermediate_steps, 1)
        ])
        
        audit_context = f"""The answering agent had access to the following tools:

{tool_descriptions}

**USER REQUEST:**
{user_prompt}

**INTERMEDIATE REASONING STEPS:**
{steps_desc}

**FINAL ANSWER:**
{final_answer}
"""
        
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=f"Please audit the following agent interaction:\n\n{audit_context}")
        ]
        
        response = self.llm.invoke(messages)
        return response.content