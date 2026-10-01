
import yaml
from uuid import uuid4
from pathlib import Path
from openai import AsyncOpenAI
from agents import OpenAIChatCompletionsModel, Runner
from agents import set_tracing_disabled
set_tracing_disabled(True)

from ..core import build_orchestrator
from ..tools.core import WorkflowState

def load_config(config_path="config.yaml"):
    path = Path(config_path)

    with path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file)

    if not isinstance(config, dict):
        raise ValueError("Invalid YAML configuration")

    provider = config.get("provider", {})
    generation = config.get("generation", {})

    for key in ("base_url", "api_key", "model"):
        if not provider.get(key):
            raise ValueError(f"Missing provider.{key} in YAML")

    return provider, generation



async def create_orchestrator(config_path="config.yaml"):
    provider, generation = load_config(config_path)

    client = AsyncOpenAI(
        base_url=provider["base_url"],
        api_key=provider["api_key"],
    )

    model = OpenAIChatCompletionsModel(
        model=provider["model"],
        openai_client=client,
    )

    orchestrator = build_orchestrator(model)

    return orchestrator, client, generation


def create_workflow_state(prompt):
    return WorkflowState(
        run_id=str(uuid4()),
        problem=prompt,
        status="running",
    )


async def chat_completion(prompt, config_path="config.yaml"):
    orchestrator, client, generation = (
        await create_orchestrator(config_path)
    )

    state = create_workflow_state(prompt)

    try:
        result = await Runner.run(
            starting_agent=orchestrator,
            input=prompt,
            context=state,
            max_turns=generation.get("max_turns", 20),
        )

        state.status = "completed"
        state.record(
            action="workflow_completed",
            agent="Orchestrator",
        )

        return result.final_output

    except Exception as exc:
        state.status = "failed"
        state.errors.append({
            "stage": "orchestration",
            "error": str(exc),
        })
        state.record(
            action="workflow_failed",
            agent="Orchestrator",
            details=str(exc),
        )
        raise

    finally:
        await client.close()


async def stream_chat_completion(prompt, config_path="config.yaml"):
    orchestrator, client, generation = (
        await create_orchestrator(config_path)
    )

    state = create_workflow_state(prompt)

    try:
        result = Runner.run_streamed(
            starting_agent=orchestrator,
            input=prompt,
            context=state,
            max_turns=generation.get("max_turns", 20),
        )

        last_agent = None

        async for event in result.stream_events():

            # Track the active agent.
            if event.type == "agent_updated_stream_event":
                agent_name = event.new_agent.name

                if agent_name != last_agent:
                    last_agent = agent_name
                    state.current_agent = agent_name
                    state.record(
                        action="agent_started",
                        agent=agent_name,
                    )

                    yield {
                        "type": "reasoning",
                        "agent": agent_name,
                        "text": f"{agent_name} started working.",
                    }

            # Capture streamed model output.
            elif event.type == "raw_response_event":
                data = event.data

                if (
                    getattr(data, "type", None)
                    == "response.output_text.delta"
                ):
                    delta = getattr(data, "delta", "")

                    if delta:
                        yield {
                            "type": "reasoning",
                            "agent": last_agent or "Agent",
                            "text": delta,
                        }

            # Capture tool calls and results.
            elif event.type == "run_item_stream_event":
                item = event.item

                if item.type == "tool_call_item":
                    raw = item.raw_item

                    tool_name = getattr(
                        raw, "name", "unknown_tool"
                    )
                    arguments = getattr(
                        raw, "arguments", ""
                    )

                    state.record(
                        action="tool_call",
                        agent=last_agent,
                        details={
                            "tool": tool_name,
                            "arguments": arguments,
                        },
                    )

                    yield {
                        "type": "reasoning",
                        "agent": last_agent or "Agent",
                        "text": (
                            f"\n{tool_name}:\n"
                            f"Arguments: {arguments}"
                        ),
                    }

                elif item.type == "tool_call_output_item":
                    output = getattr(item, "output", None)

                    state.record(
                        action="tool_result",
                        agent=last_agent,
                        details={
                            "output": str(output)
                        },
                    )

                    yield {
                        "type": "reasoning",
                        "agent": last_agent or "Agent",
                        "text": (
                            "\n[Tool result]\n"
                            f"{output}"
                        ),
                    }

                elif item.type == "handoff_call_item":
                    state.record(
                        action="handoff",
                        agent=last_agent,
                    )

                    yield {
                        "type": "reasoning",
                        "agent": last_agent or "Agent",
                        "text": "\n[Agent handoff]",
                    }

        state.status = "completed"
        state.record(
            action="workflow_completed",
            agent="Orchestrator",
        )

        if result.final_output:
            yield {
                "type": "content",
                "text": str(result.final_output),
            }

    except Exception as exc:
        state.status = "failed"
        state.errors.append({
            "stage": "streaming",
            "error": str(exc),
        })
        state.record(
            action="workflow_failed",
            agent=last_agent or "Orchestrator",
            details=str(exc),
        )

        yield {
            "type": "error",
            "message": str(exc),
        }

    finally:
        await client.close()