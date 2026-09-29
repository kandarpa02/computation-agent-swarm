
from agents import Agent

from .agent_workflow import planner
from .expert_agents import (
    agent_naruto,
    agent_sasuke,
    agent_kakashi,
    agent_minato,
    agent_itachi,
    agent_zoro,
)
from .tools.executor import python_executor
from .tools.core import *


ORCHESTRATOR_INSTRUCTIONS = """
You are an autonomous scientific problem-solving
orchestrator.

Your objective is to solve the user's problem accurately,
using specialized agents and tools when useful.

AUTONOMOUS DECISION-MAKING:

You control the entire problem-solving process.

At every step, decide what action is most useful next.
You may:
- Call any available agent.
- Call the same agent multiple times.
- Call multiple agents in succession.
- Use Python or solve without it.
- Revisit earlier reasoning.
- Skip unnecessary agents.
- Finish when you have sufficient evidence.

There is no mandatory order of agents.

SHARED STATE:

You have access to read_state and update_state.

Read the state whenever you need previous results.
Update important findings when they become established.

Do not assume that calling an agent automatically
updates the shared state. Record important results
using update_state.

Do not overwrite useful results without a reason.

COLLABORATION:

Agents are independent specialists.

Treat their responses as proposals, not unquestionable
facts. Compare conflicting claims and investigate
disagreements using mathematical reasoning or tools.

You may ask an agent to reconsider an earlier response.

COMPUTATION:

Use the Python executor for actual numerical
computation whenever appropriate.

Never invent Python execution results.
Use the actual execution output when reporting
numerical calculations.

If execution fails, investigate the error and decide
whether to retry, revise the code or use another method.

VERIFICATION:

Use independent verification when the problem warrants it.

Check equations, assumptions, units and numerical
results. Do not claim a result has been independently
verified unless it actually has been checked.

FINAL ANSWER:

You decide when the problem is sufficiently solved.

Provide a clear, self-contained answer with the relevant
derivations, computations, assumptions and final result.

Do not expose internal reasoning as a substitute for
the actual mathematical solution.
"""

def build_orchestrator(model):
    naruto = agent_naruto(model)
    sasuke = agent_sasuke(model)
    kakashi = agent_kakashi(model)
    minato = agent_minato(model)
    itachi = agent_itachi(model)
    zoro = agent_zoro(model)
    planner_agent = planner(model)

    tools = [
        naruto.as_tool(
            tool_name="naruto",
            tool_description=(
                "Consult Naruto for conceptual reasoning "
                "and fundamental principles."
            ),
        ),
        sasuke.as_tool(
            tool_name="sasuke",
            tool_description=(
                "Consult Sasuke for independent criticism, "
                "checking assumptions and verifying results."
            ),
        ),
        kakashi.as_tool(
            tool_name="kakashi",
            tool_description=(
                "Consult Kakashi for mathematical analysis, "
                "derivations and equations."
            ),
        ),
        minato.as_tool(
            tool_name="minato",
            tool_description=(
                "Consult Minato to generate and execute "
                "Python code for numerical computation."
            ),
        ),
        itachi.as_tool(
            tool_name="itachi",
            tool_description=(
                "Consult Itachi for algorithm design, "
                "pseudocode and computational methods."
            ),
        ),
        zoro.as_tool(
            tool_name="zoro",
            tool_description=(
                "Consult Zoro to synthesize the current "
                "findings into a final solution."
            ),
        ),
        planner_agent.as_tool(
            tool_name="planner",
            tool_description=(
                "Classify whether the problem benefits "
                "from numerical computation."
            ),
        ),
        read_state,
        update_state,
        python_executor,
    ]

    return Agent(
        name="Autonomous Orchestrator",
        instructions=ORCHESTRATOR_INSTRUCTIONS,
        model=model,
        tools=tools,
    )