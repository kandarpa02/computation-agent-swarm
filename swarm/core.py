
from agents import Agent

from .instructions import ORCHESTRATOR_INSTRUCTIONS
from .expert_agents import build_create_sub_agent_tool
from .tools.core import read_state, update_state
from .tools.executor import python_executor


def build_orchestrator(model):

    # Explicit allowlist: the model chooses names, but Python
    # resolves them to actual tool objects.
    available_subagent_tools = {
        "python_executor": python_executor,
        "read_state": read_state,
        "update_state": update_state,
    }

    create_sub_agent = build_create_sub_agent_tool(
        model=model,
        available_tools=available_subagent_tools,
    )

    tools = [
        create_sub_agent,
        read_state,
        update_state,
        python_executor,
    ]

    return Agent(
        name="Omega",
        instructions=ORCHESTRATOR_INSTRUCTIONS,
        model=model,
        tools=tools,
    )
