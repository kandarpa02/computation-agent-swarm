# Computation Agent Swarm

An autonomous multi-agent framework for mathematical problem-solving, scientific reasoning, and numerical computation, powered by the OpenAI Agents SDK.

The swarm uses an LLM-driven orchestrator to delegate tasks to specialist agents, execute Python when necessary, and synthesize results into a final solution.

## Features

- **Autonomous orchestration:** Dynamically selects agents and tools based on the problem.
- **Specialist agents:** Dedicated agents for analysis, verification, algorithm design, computation, and solution synthesis.
- **Numerical computation:** Python execution with NumPy, SciPy, pandas, and JAX.
- **Shared workflow state:** Agents can exchange intermediate results.
- **OpenAI-compatible API:** Integrates with applications through a familiar chat-completions endpoint.
- **Streaming:** Observe agent activity and receive the final answer through SSE.
- **Flexible model configuration:** Supports Ollama and compatible hosted model providers.

## Installation

Requires Python 3.10 or later.

```bash
git clone https://github.com/kandarpa02/computation-agent-swarm.git
cd computation-agent-swarm

python -m pip install --upgrade pip
python -m pip install -e .
```

## Configuration

Create a `model.yaml` file

```yaml
provider:
  model: "qwen3.5:0.8b"
  base_url: "http://127.0.0.1:11434/v1"
  api_key: "ollama"

generation:
  max_turns: 20
```

### Configuration options

| Parameter | Description |
|---|---|
| `provider.model` | Model identifier used by the provider. |
| `provider.base_url` | OpenAI-compatible API base URL. |
| `provider.api_key` | Provider API key or accepted placeholder. |
| `generation.max_turns` | Maximum agent-run turns per request. |

### Example: OpenAI

```yaml
provider:
  model: "YOUR_MODEL_ID"
  base_url: "https://api.openai.com/v1"
  api_key: "YOUR_API_KEY"

generation:
  max_turns: 20
```

For Ollama, ensure the model is installed and the Ollama server is running.

Keep API keys private and do not commit your configuration file to version control.

## Start the API

```bash
compute_agent serve --config model.yaml
```

By default, the server runs at:

```text
http://127.0.0.1:8010
```

The API base URL is:

```text
http://127.0.0.1:8010/v1
```

You can customize the host and port:

```bash
compute_agent serve \
  --config model.yaml \
  --host 127.0.0.1 \
  --port 8010
```

Press `Ctrl+C` to stop the server.

## API Usage

The API exposes the following endpoints:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/v1/models` | List available API models |
| `POST` | `/v1/chat/completions` | Submit a problem to the swarm |

### Health check

```bash
curl http://127.0.0.1:8010/health
```

### Non-streaming request

Submit a problem using the OpenAI-compatible chat-completions endpoint.

```bash
curl -sS http://127.0.0.1:8010/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agent-swarm",
    "messages": [
      {
        "role": "user",
        "content": "A particle starts from rest and accelerates at 2 m/s^2 for 5 seconds. Find its final velocity and displacement."
      }
    ],
    "stream": false
  }'
```

The final answer is available at:

```text
choices[0].message.content
```

To extract it using `jq`:

```bash
curl -sS http://127.0.0.1:8010/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {
        "role": "user",
        "content": "Calculate the determinant of [[1, 2], [3, 4]]."
      }
    ]
  }' | jq -r '.choices[0].message.content'
```

### Streaming request

Set `stream` to `true` to receive server-sent events while the swarm is working.

```bash
curl -N http://127.0.0.1:8010/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "model": "agent-swarm",
    "messages": [
      {
        "role": "user",
        "content": "Derive the moment of inertia of a uniform solid disc about its central axis."
      }
    ],
    "stream": true
  }'
```

The stream can contain:

- `reasoning_content`: observable agent activity, tool calls, and intermediate outputs.
- `content`: the final answer.
- `data: [DONE]`: indicates that the stream has finished.

The `-N` flag disables curl's output buffering so that events appear as they arrive.

`reasoning_content` represents observable workflow output, not a guaranteed complete internal reasoning trace.

## License

MIT License. See [LICENSE](LICENSE).

