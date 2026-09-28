
import yaml
from pathlib import Path
from openai import AsyncOpenAI
from agents import OpenAIChatCompletionsModel, Runner
from agents import set_tracing_disabled
set_tracing_disabled(True)

from ..core import build_orchestrator


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


async def chat_completion(prompt, config_path="config.yaml"):
    orchestrator, client, generation = await create_orchestrator(
        config_path
    )

    try:
        result = await Runner.run(
            starting_agent=orchestrator,
            input=prompt,
            max_turns=None,
        )
        return result.final_output
    finally:
        await client.close()



async def stream_chat_completion(prompt, config_path="config.yaml"):
    orchestrator, client, generation = await create_orchestrator(
        config_path
    )

    try:
        result = Runner.run_streamed(
            starting_agent=orchestrator,
            input=prompt,
            max_turns=None,
        )

        last_agent = None

        async for event in result.stream_events():
            # Track the active agent.
            if event.type == "agent_updated_stream_event":
                agent_name = event.new_agent.name

                if agent_name != last_agent:
                    last_agent = agent_name
                    yield {
                        "type": "reasoning",
                        "agent": agent_name,
                        "text": f"[{agent_name}] Started working."
                    }

            # Capture streamed model output.
            elif event.type == "raw_response_event":
                data = event.data

                if getattr(data, "type", None) == "response.output_text.delta":
                    delta = getattr(data, "delta", "")

                    if delta:
                        yield {
                            "type": "reasoning",
                            "agent": last_agent or "Agent",
                            "text": delta,
                        }

            # Capture completed tool and message events.
            elif event.type == "run_item_stream_event":
                item = event.item

                if item.type == "tool_call_item":
                    raw = item.raw_item

                    tool_name = getattr(raw, "name", "unknown_tool")
                    arguments = getattr(raw, "arguments", "")

                    yield {
                        "type": "reasoning",
                        "agent": last_agent or "Agent",
                        "text": (
                            f"\n[Tool call: {tool_name}]\n"
                            f"Arguments: {arguments}"
                        ),
                    }

                elif item.type == "tool_call_output_item":
                    output = getattr(item, "output", None)

                    yield {
                        "type": "reasoning",
                        "agent": last_agent or "Agent",
                        "text": (
                            "\n[Tool result]\n"
                            f"{output}"
                        ),
                    }

                elif item.type == "handoff_call_item":
                    yield {
                        "type": "reasoning",
                        "agent": last_agent or "Agent",
                        "text": "\n[Agent handoff]",
                    }

        # Only the final answer goes into assistant content.
        if result.final_output:
            yield {
                "type": "content",
                "text": str(result.final_output),
            }

    finally:
        await client.close()