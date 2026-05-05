from __future__ import annotations
from typing import Any, Dict, List, Optional, Union

# LangChain core
from langchain.agents import AgentExecutor, initialize_agent, AgentType, create_tool_calling_agent
from langchain_core.tools import BaseTool
from langchain_core.language_models import BaseChatModel
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder

try:
    from langchain_openai import ChatOpenAI  # type: ignore
except Exception:
    ChatOpenAI = None  # type: ignore

try:
    from langchain_groq import ChatGroq  # type: ignore
except Exception:
    ChatGroq = None  # type: ignore

# 
# Notes on Structured Agent Tests
# 
# ZERO_SHOT_REACT_DESCRIPTION does not support multiple input tools like analyze_neighborhood
# STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION works with llama-3.3-70b-versatile
# STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION works fails to terminate using llama-3.1-8b-instant
# CHAT_CONVERSATIONAL_REACT_DESCRIPTION using llama-3.1-8b-instant
#
class StructuredChatAgent:

    def __init__(
        self,
        tools: List[Union[BaseTool, Any]],
        llm: BaseChatModel,
        *,
        verbose: bool = True,
        handle_parsing_errors: bool = True,
        return_intermediate_steps: bool = True,
    ) -> None:
        self.tools = tools
        self.llm = llm
        self.executor = initialize_agent(
            tools,
            llm,
            agent=AgentType.STRUCTURED_CHAT_ZERO_SHOT_REACT_DESCRIPTION,
            verbose=verbose,
            handle_parsing_errors=handle_parsing_errors,
            return_intermediate_steps=return_intermediate_steps,
        )

    def run(self, user_input: str) -> Dict[str, Any]:
        """
        Executes one full agent loop.
        Returns the standard LangChain result dict:
          { "output": str, "intermediate_steps": List[Tuple[AgentAction, str]], ... }
        """
        # structured-chat expects the "input" key when returning intermediate steps
        return self.executor.invoke({"input": user_input})


class ToolCallingAgent:
    """
    Provider-aware OpenAI standard tool-calling agent.
    Works with any model that supports .bind_tools(), including OpenAI (gpt-4o)
    and Groq (llama-3.3-*).

    Parameters
    ----------
    tools : list[BaseTool|Tool]
        LangChain tools.
    llm : BaseChatModel
        A chat model (e.g., ChatOpenAI, ChatGroq).
    force_tool : bool
        If True, nudge/require the model to call at least one tool.
    allow_parallel : bool
        If False, keep tool calls sequential. Important for stateful tools.
        OpenAI supports this via bind_tools(..., parallel_tool_calls=False).
        For Groq, pass model_kwargs={'parallel_tool_calls': False} when creating the LLM.
    max_iterations : int
        Safety cap for the loop.
    verbose, return_intermediate_steps : bool
        Standard AgentExecutor flags.
    """
    
    def __init__(
        self,
        tools: List[Union[BaseTool, Any]],
        llm: BaseChatModel,
        *,
        force_tool: bool = True,
        allow_parallel: bool = False,
        max_iterations: int = 6,
        verbose: bool = True,
        return_intermediate_steps: bool = True,
    ) -> None:
        self.tools = tools
        self.llm = llm
        self.max_iterations = max_iterations

        tool_choice = "any" if force_tool else "auto"


        REACT_TOOLS_SYSTEM_PROMPT = """\
            You are a careful, step-by-step assistant that solves tasks using available tools.

            Follow this loop until you can confidently answer:
            1) THINK: Reason briefly about what to do.
            2) ACT: If needed, call exactly one tool with correct JSON arguments.
            3) OBSERVE: Read the tool result.
            4) REPEAT until done.
            5) FINAL: Give the user a clear answer.

            Rules:
            - Only use provided tools.
            - Tool calls must use the expected JSON schema.
            - If no tool is needed, answer directly.
            """

        prompt = ChatPromptTemplate.from_messages([
            ("system", REACT_TOOLS_SYSTEM_PROMPT),
            ("user", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        # Bind tools with provider-aware handling of parallel tool calls.
        bound_llm = None
        if hasattr(llm, "bind_tools"):
            # Prefer passing parallel control via bind_tools when the provider supports it
            try:
                bound_llm = llm.bind_tools(
                    tools,
                    tool_choice=tool_choice,
                    parallel_tool_calls=allow_parallel,  # Works for OpenAI; some providers ignore
                )
            except TypeError:
                # Fallback: some providers (or older versions) don't accept parallel_tool_calls here.
                # In those cases, ensure you set model_kwargs={'parallel_tool_calls': False} on the LLM itself.
                bound_llm = llm.bind_tools(tools, tool_choice=tool_choice)
        else:
            raise ValueError("The provided llm does not support .bind_tools(...)")

        # Create the agent + executor
        self.agent = create_tool_calling_agent(bound_llm, tools, prompt)
        self.executor = AgentExecutor(
            agent=self.agent,
            tools=tools,
            verbose=verbose,
            return_intermediate_steps=return_intermediate_steps,
            max_iterations=max_iterations,
        )

    def run(self, user_input: str) -> Dict[str, Any]:
        """
        Executes one full agent loop using tool-calling.
        Returns:
          { "output": str, "intermediate_steps": [...], ... }
        """
        return self.executor.invoke({"input": user_input})


class OpenAIToolCallingAgent(ToolCallingAgent):
    """
    Explicit OpenAI version that ensures parallel-tool-calls are controlled via bind_tools.
    Use when you want a clearly-named class for your OpenAI path.
    """
    def __init__(
        self,
        tools: List[Union[BaseTool, Any]],
        llm: BaseChatModel,
        **kwargs: Any,
    ) -> None:
        if ChatOpenAI is not None and not isinstance(llm, ChatOpenAI):  # type: ignore
            raise TypeError("OpenAIToolCallingAgent expects a ChatOpenAI instance")
        super().__init__(tools, llm, **kwargs)


class GroqToolCallingAgent(ToolCallingAgent):
    """
    Explicit Groq version.

    Tip: when you construct ChatGroq, pass:
        ChatGroq(..., model_kwargs={'parallel_tool_calls': False})
    if you need strict sequential tool execution.
    """
    def __init__(
        self,
        tools: List[Union[BaseTool, Any]],
        llm: BaseChatModel,
        **kwargs: Any,
    ) -> None:
        if ChatGroq is not None and not isinstance(llm, ChatGroq):  # type: ignore
            raise TypeError("GroqToolCallingAgent expects a ChatGroq instance")
        super().__init__(tools, llm, **kwargs)
