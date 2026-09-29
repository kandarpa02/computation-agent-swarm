
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


def messages_to_prompt(messages: list[dict]) -> str:
    """Convert OpenAI-compatible messages into a text prompt."""
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

        prompt = messages_to_prompt(request.messages)

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