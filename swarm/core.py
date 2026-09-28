
from openai import AsyncOpenAI
from agents import OpenAIChatCompletionsModel, Runner, Agent

from .agent_workflow import planner
from .expert_agents import (
    agent_naruto,
    agent_sasuke,
    agent_kakashi,
    agent_minato,
    agent_itachi,
    agent_zoro,
)


def build_orchestrator(model):
    Naruto = agent_naruto(model)
    Sasuke = agent_sasuke(model)
    Kakashi = agent_kakashi(model)
    Minato = agent_minato(model)
    Itachi = agent_itachi(model)
    Zoro = agent_zoro(model)
    planner_agent = planner(model)

    tools = [
        Kakashi.as_tool(
            tool_name="kakashi",
            tool_description="Analyze the problem."
        ),
        Minato.as_tool(
            tool_name="minato",
            tool_description="Write and execute Python code."
        ),
        Itachi.as_tool(
            tool_name="itachi",
            tool_description="Write pseudocode."
        ),
        Zoro.as_tool(
            tool_name="zoro",
            tool_description="Structure the final explanation."
        ),
        planner_agent.as_tool(
            tool_name="planner",
            tool_description="Plan and decide the workflow."
        ),
        Naruto.as_tool(
            tool_name="naruto",
            tool_description="Handle basic reasoning."
        ),
        Sasuke.as_tool(
            tool_name="sasuke",
            tool_description="Perform advanced reasoning and verification."
        ),
    ]

    return Agent(
        name="Orchestrator",
        instructions="""
        You manage a mathematical problem-solving swarm.

        Workflow:
        1. Call Kakashi to analyze the problem.
        2. Call Minato to write and execute Python code.
        3. Have Sasuke verify the proposed solution.
        4. If verification fails, correct the solution and
           verify it again.
        5. Call Zoro to prepare the final explanation.

        Use Itachi when pseudocode is useful.
        Use Naruto for basic reasoning when appropriate.
        Do not fabricate results.
        Never claim a solution is verified if verification fails.
        """,
        model=model,
        tools=[*tools],
    )