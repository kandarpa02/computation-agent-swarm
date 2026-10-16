from agents import Agent

from .instructions import (
    AGENT_NARUTO,
    AGENT_SASUKE,
    AGENT_KAKASHI,
    AGENT_ITACHI,
    AGENT_MINATO,
    AGENT_ZORO,
    DIALOGUE_RULES,
    AGENT_OUTPUT_CONTRACT,
)
from .tools.executor import python_executor


def make_agent(name, instructions, model, tools=None):
    return Agent(
        name=name,
        instructions=(
            instructions
            + "\n\n"
            + AGENT_OUTPUT_CONTRACT
            + "\n\n"
            + DIALOGUE_RULES
        ),
        output_type=str,
        tools=tools or [],
        model=model,
    )


def agent_naruto(model):
    return make_agent(
        "Agent Naruto", AGENT_NARUTO, model
    )


def agent_sasuke(model):
    return make_agent(
        "Agent Sasuke", AGENT_SASUKE, model
    )


def agent_kakashi(model):
    return make_agent(
        "Agent Kakashi", AGENT_KAKASHI, model
    )


def agent_itachi(model):
    return make_agent(
        "Agent Itachi", AGENT_ITACHI, model
    )


def agent_minato(model):
    return make_agent(
        "Agent Minato",
        AGENT_MINATO,
        model,
        # tools=[python_executor],
    )


def agent_zoro(model):
    return make_agent(
        "Agent Zoro", AGENT_ZORO, model
    )