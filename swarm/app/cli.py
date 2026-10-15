"""Agent Swarm command line interface.

  serve — run the OpenAI-compatible HTTP API
  run   — interactive chat in this terminal, straight against a config
  chat  — attach the terminal UI to an already-running API
"""

import argparse
import os
import sys
from pathlib import Path

import uvicorn

from .api import create_app
from .app import load_config


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value else default


def _resolve_config(parser: argparse.ArgumentParser, path: Path | None) -> Path:
    if path is None:
        parser.error("a config path is required (positional or --config)")
    config_path = path.expanduser().resolve()
    if not config_path.is_file():
        parser.error(f"Config file not found: {config_path}")
    try:
        load_config(config_path)
    except Exception as exc:
        parser.error(f"Invalid configuration: {exc}")
    return config_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-swarm", description="Agent Swarm CLI")
    parser.add_argument("--version", action="version", version="agent-swarm 1.2.0")
    sub = parser.add_subparsers(dest="command", required=True)

    # ------------------------------------------------ serve (unchanged behavior)
    serve = sub.add_parser("serve", help="Start the Agent Swarm API server")
    serve.add_argument("config_pos", nargs="?", type=Path, help=argparse.SUPPRESS)
    serve.add_argument("--config", dest="config_opt", type=Path,
                       help="Path to the YAML configuration file")
    serve.add_argument("--host", default="127.0.0.1",
                       help="Host to bind to (default: 127.0.0.1)")
    serve.add_argument("--port", type=int, default=8010,
                       help="Port to listen on (default: 8010)")
    serve.add_argument("--log-level", default="info", help="uvicorn log level")

    # ------------------------------------------------ run: local interactive chat
    run = sub.add_parser("run", help="Interactive chat against a config, in this terminal")
    run.add_argument("config_pos", nargs="?", type=Path,
                     help="Path to the YAML configuration file")
    run.add_argument("--config", dest="config_opt", type=Path,
                     help="Path to the YAML configuration file")
    run.add_argument("-m", "--model", default=_env("SWARM_MODEL", "nomber"))
    run.add_argument("-s", "--system", default=_env("SWARM_SYSTEM"))
    run.add_argument("-p", "--prompt", help="one-shot prompt; omit for the interactive REPL")
    run.add_argument("--no-stream", action="store_true", help="wait for the full answer")
    run.add_argument("--spinner", default="circleHalves")

    # ------------------------------------------------ chat: attach to a running API
    chat = sub.add_parser("chat", help="Chat with an already-running Agent Swarm API")
    chat.add_argument("--base-url", default=_env("SWARM_BASE_URL", "http://127.0.0.1:8010"))
    chat.add_argument("--api-key", default=_env("SWARM_API_KEY"))
    chat.add_argument("-m", "--model", default=_env("SWARM_MODEL", "nomber"))
    chat.add_argument("-s", "--system", default=_env("SWARM_SYSTEM"))
    chat.add_argument("-p", "--prompt")
    chat.add_argument("--no-stream", action="store_true")
    chat.add_argument("--spinner", default="circleHalves")

    return parser


def _cmd_serve(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    config_path = _resolve_config(parser, args.config_pos or args.config_opt)

    print("Starting Agent Swarm...")
    print(f"Config: {config_path}")
    print(f"API: http://{args.host}:{args.port}/v1")
    print("Press CTRL+C to stop.")

    app = create_app(str(config_path))
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)


def _cmd_run(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    from .tui import LocalSwarm, TuiOptions, run_tui   # lazy: keeps serve startup light

    config_path = _resolve_config(parser, args.config_pos or args.config_opt)
    options = TuiOptions(
        base_url="local",                 # unused in this mode; kept as fallback
        config_path=str(config_path),     # switches the TUI into in-process mode
        model=args.model,
        system=args.system,
        no_stream=args.no_stream,
        spinner=args.spinner,
        prompt=args.prompt,
        client_factory=lambda: LocalSwarm(str(config_path), model=args.model),
    )
    sys.exit(run_tui(options))


def _cmd_chat(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    from .tui import TuiOptions, run_tui

    options = TuiOptions(
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        system=args.system,
        no_stream=args.no_stream,
        spinner=args.spinner,
        prompt=args.prompt,
    )
    sys.exit(run_tui(options))


def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {"serve": _cmd_serve, "run": _cmd_run, "chat": _cmd_chat}
    try:
        handlers[args.command](parser, args)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()