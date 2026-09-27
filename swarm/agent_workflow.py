from agents import Agent
from .tools.core import Planner

def planner(model):
    agent = Agent(
        name='Planner',
        tools=[],
        instructions="""
        your job is to understand if the prompt is for numerical computation or not.
        if not numerical emit:
        False,
        else:
        True
        """,
        model=model,
        output_type=bool
    )
    return agent

def executor(model):
    pass

