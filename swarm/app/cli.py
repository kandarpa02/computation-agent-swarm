
import argparse
from pathlib import Path

import uvicorn

from .app import load_config
from .api import create_app


def main():
    parser = argparse.ArgumentParser(
        prog="agent-swarm",
        description="Agent Swarm CLI",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    serve = subparsers.add_parser(
        "serve",
        help="Start the Agent Swarm API server",
    )

    serve.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to the YAML configuration file",
    )

    serve.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )

    serve.add_argument(
        "--port",
        type=int,
        default=8010,
        help="Port to listen on (default: 8010)",
    )

    args = parser.parse_args()

    if args.command == "serve":
        config_path = args.config.expanduser().resolve()

        if not config_path.is_file():
            parser.error(f"Config file not found: {config_path}")

        # Validate the configuration before starting.
        try:
            load_config(config_path)
        except Exception as exc:
            parser.error(f"Invalid configuration: {exc}")

        print("Starting Agent Swarm...")
        print(f"Config: {config_path}")
        print(f"API: http://{args.host}:{args.port}/v1")
        print("Press CTRL+C to stop.")

        app = create_app(str(config_path))

        uvicorn.run(
            app,
            host=args.host,
            port=args.port,
            log_level="info",
        )


if __name__ == "__main__":
    main()