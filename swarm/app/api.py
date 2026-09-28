
# src/agent_swarm/server.py

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


def create_app(config_path: str):
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def completions(request: ChatRequest):
        chat_id = f"chatcmpl-{uuid.uuid4().hex}"

        prompt = request.messages

        if not request.stream:
            answer = await chat_completion(
                prompt, config_path
            )

            return {
                "id": chat_id,
                "object": "chat.completion",
                "created": int(time.time()),
                "model": request.model or "agent-swarm",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": answer,
                    },
                    "finish_reason": "stop",
                }],
            }


        async def generate():
            try:
                async for event in stream_chat_completion(
                    prompt, config_path
                ):
                    if event["type"] == "reasoning":
                        delta = {
                            "reasoning_content": event["text"]
                        }
                    else:
                        delta = {
                            "content": event["text"]
                        }

                    chunk = {
                        "id": chat_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": request.model or "agent-swarm",
                        "choices": [{
                            "index": 0,
                            "delta": delta,
                            "finish_reason": None,
                        }],
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"

                final_chunk = {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": request.model or "agent-swarm",
                    "choices": [{
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop",
                    }],
                }
                yield f"data: {json.dumps(final_chunk)}\n\n"
                yield "data: [DONE]\n\n"

            except Exception:
                error = {
                    "error": {
                        "message": "Agent workflow failed.",
                        "type": "server_error",
                    }
                }
                yield f"data: {json.dumps(error)}\n\n"

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
            "data": [{
                "id": "agent-swarm",
                "object": "model",
                "owned_by": "agent-swarm",
            }],
        }

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app