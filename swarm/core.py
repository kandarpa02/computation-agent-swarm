from openai import AsyncOpenAI
from agents import OpenAIChatCompletionsModel, Runner, Agent
from ollama import Client
from .agent_workflow import planner
from .expert_agents import (
    agent_naruto,
    agent_sasuke,
    agent_kakashi,
    agent_minato,
    agent_itachi,
    agent_zoro
)

async def chat_completion(base_url, api_key, model, prompt):
    client = AsyncOpenAI(
        base_url=base_url,
        api_key=api_key,
        
    )
    Model = OpenAIChatCompletionsModel(
        model = model,
        openai_client = client
    )

    Naruto = agent_naruto(model)
    Sasuke = agent_sasuke(model)
    Kakashi = agent_kakashi(model)
    Minato = agent_minato(model)
    Itachi = agent_itachi(model)
    Zoro = agent_zoro(model)
    planner_agent = planner(model)

    Naruto_tool = Naruto.as_tool(
        tool_name="naruto",
        tool_description="Delegate basic reasoning tasks to Naruto."
    )

    Sasuke_tool = Sasuke.as_tool(
        tool_name="sasuke",
        tool_description="Delegate advanced reasoning and verify Narutos's tasks to Sasuke."
    )

    Kakashi_tool = Kakashi.as_tool(
        tool_name="kakashi",
        tool_description="Delegate analysis tasks to Kakashi."
    )

    Minato_tool = Minato.as_tool(
        tool_name="minato",
        tool_description="Delegate coding and Python execution tasks to Minato."
    )

    Itachi_tool = Itachi.as_tool(
        tool_name="itachi",
        tool_description="Delegate writing pseudocode tasks to Itachi."
    )

    Zoro_tool = Zoro.as_tool(
        tool_name="zoro",
        tool_description="Delegate solution explanation and structuring tasks to Zoro."
    )

    planner_tool = planner_agent.as_tool(
        tool_name="planner",
        tool_description="Delegate task planning and workflow decisions to the planner."
    )
    orchestrator = Agent(
        name="Orchestrator",
        instructions="""
        You are the manager of a mathematical problem-solving swarm.

        You have four specialist agents:

        1. Kakashi: analyzes the problem.
        2. Minato: writes and executes Python code.
        3. Verifier: checks the solution.
        4. Zoro: prepares the final explanation.

        Workflow:
        - First, call Kakashi to analyze the problem.
        - Then, call Minato using the analysis.
        - Send the proposed solution and computation to Verifier.
        - If the solution is incorrect, use the specialists
        to correct it and verify it again.
        - Once verified, call Zoro to prepare the final answer.

        Do not fabricate results. If verification fails,
        do not present the solution as verified.
        """,
        model=model,
        tools=[
            Kakashi_tool,
            Minato_tool,
            Itachi_tool,
            Zoro_tool,
            planner_tool,
            Naruto_tool,
            Sasuke_tool
        ],
    )
    rusult = await Runner.run(
        starting_agent=orchestrator,
        input=prompt,
        max_turns=10)

    return rusult.final_output