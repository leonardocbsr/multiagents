import argparse
import logging
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="multiagents", description="Multi-agent group chat")
    parser.add_argument(
        "-a",
        "--agents",
        default="claude,codex,kimi",
        help="Comma-separated agents (default: claude,codex,kimi)",
    )
    parser.add_argument("-t", "--timeout", type=float, default=1800.0, help="Idle timeout per agent in seconds (default: 1800)")
    parser.add_argument("--parse-timeout", type=float, default=1200.0, help="Timeout for parsing agent output in seconds (default: 1200)")
    parser.add_argument("--send-timeout", type=float, default=120.0, help="WebSocket send timeout in seconds (default: 120)")
    parser.add_argument("--hard-timeout", type=float, default=0, help="Hard timeout per agent in seconds (0 = disabled, default: 0)")
    parser.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8421, help="Port (default: 8421)")

    subparsers = parser.add_subparsers(dest="command")
    init_parser = subparsers.add_parser("init", help="Initialize .multiagents/ in a directory")
    init_parser.add_argument("--path", default=None, help="Target directory (default: current directory)")

    return parser


def _get_local_ip() -> str | None:
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None


def main():
    args = build_parser().parse_args()
    log = logging.getLogger("multiagents")
    log.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    handler.setFormatter(fmt)
    log.addHandler(handler)

    if args.command == "init":
        from pathlib import Path
        from .memory.cli import init_project

        target = Path(args.path) if args.path else Path.cwd()
        init_project(target)
        print(f"Initialized .multiagents/ in {target}")
        return

    agent_names = [a.strip() for a in args.agents.split(",")]

    import uvicorn
    from .server.app import create_app

    app = create_app(
        default_agents=agent_names,
        timeout=args.timeout,
        parse_timeout=args.parse_timeout,
        send_timeout=args.send_timeout,
        hard_timeout=args.hard_timeout or None,
    )
    print(f"  Local:   http://localhost:{args.port}")
    lan_ip = _get_local_ip()
    if lan_ip and args.host != "127.0.0.1":
        print(f"  Network: http://{lan_ip}:{args.port}")
    print()
    log.info(
        "starting multiagents — agents=%s timeout=%.0fs parse_timeout=%.0fs send_timeout=%.0fs hard_timeout=%.0fs",
        args.agents,
        args.timeout,
        args.parse_timeout,
        args.send_timeout,
        args.hard_timeout,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning", log_config=None)


if __name__ == "__main__":
    main()
