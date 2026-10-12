
import json
import time
import uuid

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .app import chat_completion, stream_chat_completion


class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[dict]
    stream: bool = False


def messages_to_input(messages: list[dict]) -> list[dict]:
    result = []

    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")

        # Plain-text message
        if isinstance(content, str):
            result.append({
                "role": role,
                "content": content,
            })
            continue

        # Multimodal message
        if isinstance(content, list):
            parts = []

            for item in content:
                if not isinstance(item, dict):
                    continue

                if item.get("type") == "text":
                    parts.append({
                        "type": "input_text",
                        "text": item.get("text", ""),
                    })

                elif item.get("type") == "image_url":
                    image = item.get("image_url", {})
                    url = (
                        image.get("url", "")
                        if isinstance(image, dict)
                        else image
                    )

                    if url:
                        parts.append({
                            "type": "input_image",
                            "image_url": url,
                        })

            result.append({
                "role": role,
                "content": parts,
            })

    return result


def messages_to_prompt(messages: list[dict]) -> str:
    """Extract readable text from OpenAI-compatible messages."""
    parts = []

    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")

        if isinstance(content, list):
            text_parts = []

            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    text_parts.append(item)

            content = "\n".join(text_parts)

        if not isinstance(content, str):
            content = str(content)

        parts.append(f"{role.upper()}:\n{content}")

    return "\n\n".join(parts)

def messages_to_agent_input(messages: list[dict]) -> list[dict]:
    """Convert OpenAI Chat Completions messages to Agents SDK input."""
    result = []

    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")

        if isinstance(content, str):
            result.append({"role": role, "content": content})
            continue

        if not isinstance(content, list):
            continue

        parts = []

        for item in content:
            if not isinstance(item, dict):
                continue

            if item.get("type") == "text":
                parts.append({
                    "type": "input_text",
                    "text": item.get("text", ""),
                })

            elif item.get("type") == "image_url":
                image = item.get("image_url")
                image_url = image.get("url") if isinstance(image, dict) else image

                if image_url:
                    parts.append({
                        "type": "input_image",
                        "image_url": image_url,
                        "detail": "auto",
                    })

            elif item.get("type") == "input_image":
                # Already in Agents SDK format.
                parts.append(item)

            elif item.get("type") == "input_text":
                parts.append(item)

        if parts:
            result.append({"role": role, "content": parts})

    return result


def create_app(config_path: str = "config.yaml"):
    app = FastAPI(
        title="Agent Swarm API",
        version="1.0.0",
    )

    @app.post("/v1/chat/completions")
    async def completions(request: ChatRequest):
        chat_id = f"chatcmpl-{uuid.uuid4().hex}"
        created = int(time.time())
        model_name = request.model or "agent-swarm"

        # inputs = messages_to_input(request.messages)
        # prompt = messages_to_prompt(inputs)
        prompt = messages_to_agent_input(request.messages)

        if not request.stream:
            answer = await chat_completion(
                prompt,
                config_path,
            )

            return {
                "id": chat_id,
                "object": "chat.completion",
                "created": created,
                "model": model_name,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": answer,
                        },
                        "finish_reason": "stop",
                    }
                ],
            }

        async def generate():
            try:
                async for event in stream_chat_completion(
                    prompt,
                    config_path,
                ):
                    event_type = event.get("type")

                    if event_type == "reasoning":
                        delta = {
                            "reasoning_content": event.get("text", "")
                        }

                    elif event_type == "content":
                        delta = {
                            "content": event.get("text", "")
                        }

                    elif event_type == "error":
                        error = {
                            "error": {
                                "message": event.get(
                                    "message",
                                    "Agent workflow failed.",
                                ),
                                "type": "server_error",
                            }
                        }
                        yield f"data: {json.dumps(error)}\n\n"
                        yield "data: [DONE]\n\n"
                        return

                    else:
                        continue

                    chunk = {
                        "id": chat_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model_name,
                        "choices": [
                            {
                                "index": 0,
                                "delta": delta,
                                "finish_reason": None,
                            }
                        ],
                    }

                    yield f"data: {json.dumps(chunk)}\n\n"

                final_chunk = {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model_name,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop",
                        }
                    ],
                }

                yield f"data: {json.dumps(final_chunk)}\n\n"
                yield "data: [DONE]\n\n"

            except Exception as exc:
                error = {
                    "error": {
                        "message": str(exc),
                        "type": "server_error",
                    }
                }
                yield f"data: {json.dumps(error)}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @app.get("/v1/models")
    async def models():
        return {
            "object": "list",
            "data": [
                {
                    "id": "agent-swarm",
                    "object": "model",
                    "owned_by": "agent-swarm",
                }
            ],
        }

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app