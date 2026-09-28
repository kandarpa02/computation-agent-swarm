from agents import Agent
from .tools.core import Planner


def planner(model):
    return Agent(
        name="Planner",
        instructions="""
        You are a numerical computation classifier.

        Determine whether the user's problem requires
        numerical computation using Python.

        Return exactly one word:
        TRUE
        or
        FALSE

        TRUE: The problem requires numerical calculations
        that benefit from Python.

        FALSE: The problem can be solved without Python.

        Never return explanations, punctuation, Markdown,
        JSON, or additional text.
        """,
        model=model,
        output_type=str,
    )

def executor(model):
    pass

