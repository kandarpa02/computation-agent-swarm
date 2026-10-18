
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



from agents import Agent, Runner, function_tool


def build_create_sub_agent_tool(model, available_tools):
    """
    Build a tool that lets Omega dynamically create and execute
    specialist agents using the configured model and approved tools.
    """

    @function_tool
    async def create_sub_agent(
        name: str,
        specialty: str,
        task: str,
        tool_names: str,
    ) -> str:
        """
        Create and execute a specialist agent.

        name: Short name for the specialist.
        specialty: The specialist's role and expertise.
        task: The specific work the specialist must perform.
        tool_names: Comma-separated names of approved tools,
                    or 'none' if no tools are needed.
        """

        # Resolve model-selected tool names into actual Python tools.
        selected_tools = []

        requested_names = [
            item.strip()
            for item in tool_names.split(",")
            if item.strip() and item.strip().lower() != "none"
        ]

        for tool_name in requested_names:
            if tool_name not in available_tools:
                allowed = ", ".join(sorted(available_tools))
                return (
                    f"Subagent creation rejected: unknown tool "
                    f"'{tool_name}'. Available tools: {allowed or 'none'}."
                )

            selected_tools.append(available_tools[tool_name])

        # The application supplies the real model object.
        # Omega supplies the specialist's role and task.
        specialist = Agent(
            name=name,
            instructions=(
                f"You are {name}, a specialist agent.\n"
                f"Your area of expertise: {specialty}\n\n"
                "Complete the assigned task independently. "
                "Use your available tools when appropriate. "
                "Explain your findings clearly, state assumptions, "
                "and identify uncertainty instead of inventing results."
            ),
            model=model,
            tools=selected_tools,
            output_type=str,
        )

        # Execute the newly created agent immediately.
        result = await Runner.run(
            specialist,
            task,
        )

        return (
            f"Specialist: {name}\n"
            f"Specialty: {specialty}\n"
            f"Task: {task}\n\n"
            f"Findings:\n{result.final_output}"
        )

    return create_sub_agent


# def agent_naruto(model):
#     return make_agent(
#         "Agent Naruto", AGENT_NARUTO, model
#     )


# def agent_sasuke(model):
#     return make_agent(
#         "Agent Sasuke", AGENT_SASUKE, model
#     )


# def agent_kakashi(model):
#     return make_agent(
#         "Agent Kakashi", AGENT_KAKASHI, model
#     )


# def agent_itachi(model):
#     return make_agent(
#         "Agent Itachi", AGENT_ITACHI, model
#     )


# def agent_minato(model):
#     return make_agent(
#         "Agent Minato",
#         AGENT_MINATO,
#         model,
#         # tools=[python_executor],
#     )


# def agent_zoro(model):
#     return make_agent(
#         "Agent Zoro", AGENT_ZORO, model
#     )