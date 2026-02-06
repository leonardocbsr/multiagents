from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from src.bot import MultiAgentsBot
from src.config import Config


@pytest.fixture
def config():
    return Config(
        discord_token="fake-token",
        allowlist={111, 222},
        server_url="ws://localhost:8421/ws",
        default_agents=["claude", "codex"],
        inactivity_timeout=1800,
    )


@pytest.fixture
def bot(config):
    return MultiAgentsBot(config)


def _make_message(
    content: str,
    author_id: int = 111,
    is_bot: bool = False,
    channel_type: str = "text",
    mentions_bot: bool = False,
    thread_id: int | None = None,
):
    """Create a mock Discord message."""
    msg = MagicMock()
    msg.content = content
    msg.author.id = author_id
    msg.author.bot = is_bot
    msg.author.display_name = "TestUser"
    msg.id = 12345

    if thread_id:
        msg.channel = MagicMock()
        msg.channel.id = thread_id
        msg.channel.type = discord.ChannelType.public_thread
    else:
        msg.channel = MagicMock()
        msg.channel.id = 99999
        msg.channel.type = discord.ChannelType.text

    if mentions_bot:
        bot_user = MagicMock()
        bot_user.id = 99
        msg.mentions = [bot_user]
    else:
        msg.mentions = []

    msg.channel.create_thread = AsyncMock()
    msg.channel.send = AsyncMock()

    return msg


def test_should_ignore_bot_messages(bot):
    msg = _make_message("hello", is_bot=True)
    assert bot.should_handle(msg) is False


def test_should_ignore_non_allowlisted_user(bot):
    msg = _make_message("hello", author_id=999)
    assert bot.should_handle(msg) is False


def test_should_handle_allowlisted_user(bot):
    msg = _make_message("hello", author_id=111)
    assert bot.should_handle(msg) is True


def test_is_mention(bot):
    bot_user = MagicMock()
    bot_user.id = 99
    bot._connection = MagicMock()
    bot._connection.user = bot_user  # Simulate logged-in bot user

    msg = _make_message("hello @bot")
    msg.mentions = [bot_user]  # Same object as bot.user
    assert bot.is_mention(msg) is True


def test_is_thread_message(bot):
    msg = _make_message("followup", thread_id=55555)
    assert bot.is_thread_message(msg) is True


def test_is_stop_command(bot):
    msg = _make_message("!stop")
    assert bot.is_stop_command(msg) is True

    msg = _make_message("hello")
    assert bot.is_stop_command(msg) is False


def test_thread_name_from_prompt(bot):
    long_prompt = "Discuss the API design for authentication and authorization"
    assert bot.thread_name(long_prompt) == "Discuss the API design for authentication and aut…"
    assert bot.thread_name("Short") == "Short"
    assert len(bot.thread_name("A" * 200)) <= 50
