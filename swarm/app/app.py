
import yaml
from pathlib import Path
from openai import AsyncOpenAI
from agents import OpenAIChatCompletionsModel, Runner

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
            max_turns=generation.get("max_turns", 10),
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
            max_turns=generation.get("max_turns", 10),
        )

        async for event in result.stream_events():
            if event.type == "raw_response_event":
                delta = getattr(event.data, "delta", None)

                if isinstance(delta, str) and delta:
                    yield delta

    finally:
        await client.close()