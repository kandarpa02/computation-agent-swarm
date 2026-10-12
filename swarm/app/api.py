
import json
import logging
import time
import uuid
from typing import Any

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .app import chat_completion, stream_chat_completion


logger = logging.getLogger("agent_swarm.api")


class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[dict[str, Any]] = Field(min_length=1)
    stream: bool = False


def messages_to_agent_input(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert OpenAI Chat Completions messages to Agents SDK input."""
    result = []

    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")

        if role not in {"system", "developer", "user", "assistant"}:
            logger.warning("Skipping unsupported message role: %s", role)
            continue

        # Plain-text messages.
        if isinstance(content, str):
            result.append({
                "role": role,
                "content": content,
            })
            continue

        # Multimodal content.
        if not isinstance(content, list):
            logger.warning(
                "Skipping unsupported content type for role %s: %s",
                role,
                type(content).__name__,
            )
            continue

        parts = []

        for item in content:
            if not isinstance(item, dict):
                if isinstance(item, str):
                    parts.append({
                        "type": "input_text",
                        "text": item,
                    })
                continue

            item_type = item.get("type")

            if item_type in {"text", "input_text"}:
                text = item.get("text", "")
                if isinstance(text, str):
                    parts.append({
                        "type": "input_text",
                        "text": text,
                    })

            elif item_type == "image_url":
                image = item.get("image_url", {})
                image_url = (
                    image.get("url", "")
                    if isinstance(image, dict)
                    else image
                )

                if isinstance(image_url, str) and image_url:
                    parts.append({
                        "type": "input_image",
                        "image_url": image_url,
                        "detail": (
                            image.get("detail", "auto")
                            if isinstance(image, dict)
                            else "auto"
                        ),
                    })

            elif item_type == "input_image":
                # Already expressed in Agents SDK input format.
                parts.append(item)

            else:
                logger.debug(
                    "Ignoring unsupported content part: %s",
                    item_type,
                )

        if parts:
            result.append({
                "role": role,
                "content": parts,
            })

    if not result:
        raise ValueError("No supported messages were provided.")

    return result


def sse_event(payload: dict[str, Any]) -> str:
    """Serialize one JSON payload as a Server-Sent Event."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def create_app(config_path: str = "config.yaml") -> FastAPI:
    app = FastAPI(
        title="Agent Swarm API",
        version="1.0.1",
    )

    @app.post("/v1/chat/completions")
    async def completions(request: ChatRequest):
        chat_id = f"chatcmpl-{uuid.uuid4().hex}"
        created = int(time.time())
        model_name = request.model or "agent-swarm"

        try:
            prompt = messages_to_agent_input(request.messages)
        except ValueError as exc:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            ) from exc

        logger.info(
            "Chat request received: id=%s model=%s stream=%s messages=%d",
            chat_id,
            model_name,
            request.stream,
            len(request.messages),
        )

        if not request.stream:
            try:
                answer = await chat_completion(
                    prompt,
                    config_path,
                )

                if not isinstance(answer, str):
                    answer = str(answer)

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

            except Exception:
                logger.exception(
                    "Non-streaming chat failed: id=%s",
                    chat_id,
                )
                raise

        async def generate():
            try:
                async for event in stream_chat_completion(
                    prompt,
                    config_path,
                ):
                    if not isinstance(event, dict):
                        logger.warning(
                            "Ignoring unexpected stream event: %s",
                            type(event).__name__,
                        )
                        continue

                    event_type = event.get("type")

                    if event_type == "reasoning":
                        delta = {
                            "reasoning_content": str(
                                event.get("text", "")
                            )
                        }

                    elif event_type == "content":
                        delta = {
                            "content": str(event.get("text", ""))
                        }

                    elif event_type == "error":
                        logger.error(
                            "Workflow error: id=%s message=%s",
                            chat_id,
                            event.get("message", "Unknown error"),
                        )

                        error_payload = {
                            "error": {
                                "message": str(
                                    event.get(
                                        "message",
                                        "Agent workflow failed.",
                                    )
                                ),
                                "type": "server_error",
                                "code": "agent_workflow_error",
                            }
                        }

                        yield sse_event(error_payload)
                        yield "data: [DONE]\n\n"
                        return

                    else:
                        logger.debug(
                            "Ignoring unknown event type: %s",
                            event_type,
                        )
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

                    yield sse_event(chunk)

                # End the assistant turn.
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

                yield sse_event(final_chunk)
                yield "data: [DONE]\n\n"

                logger.info("Chat stream completed: id=%s", chat_id)

            except Exception as exc:
                logger.exception(
                    "Streaming chat failed: id=%s",
                    chat_id,
                )

                # Once streaming starts, HTTP status codes cannot reliably
                # be changed. Send an SSE error and terminate the stream.
                error_payload = {
                    "error": {
                        "message": str(exc),
                        "type": "server_error",
                        "code": "stream_error",
                    }
                }

                yield sse_event(error_payload)
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/v1/models")
    async def models():
        return {
            "object": "list",
            "data": [
                {
                    "id": "nomber",
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "computation-agent-swarm",
                }
            ],
        }

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
