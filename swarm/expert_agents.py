from agents import Agent
from .instructions import *
from .tools.executor import python_executor

def agent_naruto(model):
    agent = Agent(
        name="Agent Naruto",
        instructions=AGENT_NARUTO + DIALOGUE_RULES,
        output_type=str,
        model=model
    )
    return agent

def agent_sasuke(model):
    agent = Agent(
            name="Agent Sasuke",
            instructions=AGENT_SASUKE + DIALOGUE_RULES,
            output_type=str,
            model=model
        )
    return agent

def agent_kakashi(model):
    agent = Agent(
            name="Agent Kakashi",
            instructions=AGENT_KAKASHI + DIALOGUE_RULES,
            output_type=str,
            model=model
        )
    return agent

def agent_itachi(model):
    agent = Agent(
            name="Agent Itachi",
            instructions=AGENT_ITACHI + DIALOGUE_RULES,
            output_type=str,
            model=model
        )
    return agent

def agent_minato(model):
    agent = Agent(
            name="Agent Minato",
            instructions=AGENT_MINATO + DIALOGUE_RULES,
            output_type=str,
            tools=[python_executor],
            model=model
        )
    return agent

def agent_zoro(model):
    agent = Agent(
            name="Agent Zoro",
            instructions=AGENT_ZORO + DIALOGUE_RULES,
            output_type=str,
            model=model
        )
    return agent