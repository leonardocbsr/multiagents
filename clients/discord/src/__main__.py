from __future__ import annotations

import logging
import sys

from dotenv import load_dotenv

from .config import Config
from .bot import MultiAgentsBot


def main():
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    try:
        config = Config.from_env()
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    bot = MultiAgentsBot(config)
    bot.run(config.discord_token)


if __name__ == "__main__":
    main()
