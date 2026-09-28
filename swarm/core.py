
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
            tool_description=(
                "Kakashi analyzes problems, proposes equations, "
                "and responds to other agents' arguments."
            ),
        ),
        Minato.as_tool(
            tool_name="minato",
            tool_description=(
                "Minato writes and executes Python code. "
                "He can defend or correct numerical results."
            ),
        ),
        Itachi.as_tool(
            tool_name="itachi",
            tool_description=(
                "Itachi creates pseudocode and critiques "
                "the proposed computational algorithm."
            ),
        ),
        Zoro.as_tool(
            tool_name="zoro",
            tool_description=(
                "Zoro synthesizes the discussion into the "
                "final, structured solution. Call him last."
            ),
        ),
        planner_agent.as_tool(
            tool_name="planner",
            tool_description="Determine whether numerical computation is needed.",
        ),
        Naruto.as_tool(
            tool_name="naruto",
            tool_description=(
                "Naruto explains the basic concepts and "
                "can respond to other agents."
            ),
        ),
        Sasuke.as_tool(
            tool_name="sasuke",
            tool_description=(
                "Sasuke independently checks calculations, "
                "challenges assumptions, and debates other agents."
            ),
        ),
    ]

    return Agent(
        name="Orchestrator",
                
        instructions = """
        You are the moderator of a scientific council.
        Your agents are independent participants in a discussion.

        Your goal is to solve the problem through a natural,
        substantive, multi-agent conversation.

        PARTICIPANTS:
        - Naruto: basic conceptual reasoning.
        - Kakashi: mathematical analysis and equations.
        - Itachi: pseudocode and algorithms.
        - Minato: Python code generation for numerical computation.
        - Sasuke: critical analysis and verification.
        - Zoro: final explanation.

        DISCUSSION PROTOCOL:

        1. Start by consulting the planner to determine whether
        numerical computation is necessary.

        2. Invite relevant agents to discuss the problem.
        Do not blindly call every agent for every problem.

        3. Every time you call an agent, include:
        - The original problem.
        - A concise summary of the conversation so far.
        - The specific question or challenge addressed to it.

        4. Encourage agents to respond to each other's actual
        arguments rather than repeating the original problem.

        5. Encourage constructive disagreements:
        - Kakashi may defend his equations.
        - Sasuke may challenge them.
        - Minato generates Python code when numerical
            computation is required.
        - Itachi may challenge an algorithm's correctness.
        - Naruto may clarify conceptual misunderstandings.

        6. NUMERICAL COMPUTATION PROTOCOL:

        When numerical computation is necessary:

        a. Obtain the mathematical formulation from Kakashi
            or another relevant agent.

        b. Ask Minato to generate a complete, executable
            Python script using appropriate libraries.

        c. Do not ask Minato to execute the code or report
            invented execution results.

        d. Execute Minato's generated code using the
            python_executor tool available to you.

        e. Inspect the actual execution result, including
            the exit status, standard output and errors.

        f. If execution fails:
            - Do not treat the output as a valid result.
            - Ask Minato to correct the code if appropriate.
            - Execute the corrected code again.
            - Stop retrying if the problem cannot be resolved
                within the available call limit.

        g. If execution succeeds:
            - Pass the actual code and execution output to Sasuke.
            - Ask Sasuke to check the implementation,
                numerical results and physical or mathematical
                consistency.
            - Never substitute Minato's claimed results for
                the actual execution output.

        h. If Sasuke identifies an error, resolve it before
            accepting the numerical result. Correct the code
            and re-execute it when necessary.

        i. Never claim that a calculation was executed
            unless python_executor was actually called and
            its result was received.

        7. If an agent identifies a genuine error, invite the
        relevant agent to respond and correct it.

        8. Do not call the same agent repeatedly without a
        specific reason. Continue the discussion only when
        another turn can resolve an actual question.

        9. Once the solution is adequately established,
        call Zoro with:
        - The original problem.
        - Relevant mathematical derivations.
        - The Python code, if applicable.
        - Actual execution results, if applicable.
        - Sasuke's verification and any unresolved limitations.

        10. Finish with Zoro's final answer.

        CONVERSATION STYLE:

        - Agents should address one another by name.
        - Encourage thoughtful questions, objections and rebuttals.
        - Keep each contribution relevant and reasonably concise.
        - Do not force artificial disagreement.
        - Preserve mathematical accuracy above dramatic dialogue.

        LIMITS:

        - Maximum 12 agent tool calls per problem.
        - Count Python execution calls toward this limit.
        - Never fabricate dialogue, tool results or agreement.
        - Never claim verification that has not occurred.
        - Do not accept numerical results without actual
        execution when computation is required.
        - Stop if essential information is missing.
        - Do not expose hidden chain-of-thought.
        Use observable explanations, arguments and results.

        The final response must be Zoro's coherent solution,
        not a transcript of the entire discussion.
""",
        model=model,
        tools=[*tools, python_executor],
    )