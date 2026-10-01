
from agents import Agent

from .instructions import ORCHESTRATOR_INSTRUCTIONS
from .expert_agents import (
    agent_naruto,
    agent_sasuke,
    agent_kakashi,
    agent_minato,
    agent_itachi,
    agent_zoro,
)
from .tools.core import read_state, update_state


def build_orchestrator(model):
    # Initialize the council.
    naruto = agent_naruto(model)
    sasuke = agent_sasuke(model)
    kakashi = agent_kakashi(model)
    minato = agent_minato(model)
    itachi = agent_itachi(model)
    zoro = agent_zoro(model)

    # Register specialists as callable agent tools.
    council = [
        naruto.as_tool(
            tool_name="naruto",
            tool_description=(
                "Council specialist for conceptual and "
                "physical reasoning. Consult for fundamental "
                "principles, assumptions and interpretations."
            ),
        ),
        sasuke.as_tool(
            tool_name="sasuke",
            tool_description=(
                "Independent council critic. Consult to "
                "challenge assumptions, independently verify "
                "solutions and investigate contradictions. "
                "Do not use merely to approve an answer."
            ),
        ),
        kakashi.as_tool(
            tool_name="kakashi",
            tool_description=(
                "Mathematical specialist. Consult for rigorous "
                "derivations, equations, proofs and analytical "
                "solutions."
            ),
        ),
        minato.as_tool(
            tool_name="minato",
            tool_description=(
                "Computational specialist with access to the "
                "Python executor. Consult for numerical "
                "calculations, simulations, code execution "
                "and computational verification."
            ),
        ),
        itachi.as_tool(
            tool_name="itachi",
            tool_description=(
                "Computational methods specialist. Consult "
                "for algorithm design, pseudocode, numerical "
                "methods and computational strategy."
            ),
        ),
        zoro.as_tool(
            tool_name="zoro",
            tool_description=(
                "Council synthesis specialist. Consult to "
                "organize established findings, reconcile "
                "compatible results and prepare a coherent "
                "final solution."
            ),
        ),
    ]

    # The orchestrator is the sole owner of shared-state
    # management and council coordination.
    tools = [
        *council,
        read_state,
        update_state,
    ]

    return Agent(
        name="Council Orchestrator",
        instructions=ORCHESTRATOR_INSTRUCTIONS,
        model=model,
        tools=tools,
    )