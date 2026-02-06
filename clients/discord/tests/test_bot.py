from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from src.bot import MultiAgentsBot, MAX_RECONNECT_ATTEMPTS
from src.bridge import ConnectionLost
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


def test_is_thread_message_rejects_non_thread_string_type(bot):
    msg = _make_message("followup")
    msg.channel.type = "threadlike-text-channel"
    assert bot.is_thread_message(msg) is False


def test_is_stop_command(bot):
    msg = _make_message("!stop")
    assert bot.is_stop_command(msg) is True

    msg = _make_message("hello")
    assert bot.is_stop_command(msg) is False


def test_thread_name_from_prompt(bot):
    """Thread names should not leak prompt content and should be distinguishable."""
    long_prompt = "Discuss the API design for authentication and authorization"
    name = bot.thread_name(long_prompt)

    # Should not contain any prompt text (sanitization)
    assert "Discuss" not in name
    assert "API" not in name
    assert "authentication" not in name

    # Should follow the Session {timestamp} format
    assert name.startswith("Session ")

    # Should be deterministic for same prompt (timestamp-based)
    name2 = bot.thread_name(long_prompt)
    # Names may differ due to timestamp, but format should be consistent
    assert name2.startswith("Session ")


async def test_stop_command_no_session(bot):
    """!stop in a thread without an active session is ignored (no archive)."""
    msg = _make_message("!stop", thread_id=55555)
    # No bridge registered for this thread
    await bot.on_message(msg)
    # channel.send should NOT be called (no "Session stopped.")
    msg.channel.send.assert_not_called()


async def test_active_thread_non_owner_non_mention_blocked(bot):
    """Messages from non-owner without @mention are blocked."""
    thread_id = 55555
    # User 222 is not the owner (owner is 111)
    msg = _make_message("hello without mention", author_id=222, thread_id=thread_id, mentions_bot=False)

    fake_bridge = AsyncMock()
    bot._bridges[thread_id] = fake_bridge
    bot._thread_participants[thread_id] = {111}  # Owner is user 111

    await bot.on_message(msg)

    fake_bridge.send_message.assert_not_called()


async def test_active_thread_owner_message_forwarded_without_mention(bot):
    """Messages from thread owner (without @mention) are forwarded."""
    thread_id = 55555
    # User 111 is the owner
    msg = _make_message("hello from owner", author_id=111, thread_id=thread_id, mentions_bot=False)

    fake_bridge = AsyncMock()
    bot._bridges[thread_id] = fake_bridge
    bot._thread_participants[thread_id] = {111}  # Owner is user 111

    await bot.on_message(msg)

    fake_bridge.send_message.assert_called_once_with("hello from owner")


async def test_active_thread_message_with_mention_forwards_stripped_prompt(bot):
    thread_id = 55555
    msg = _make_message("<@99> hello there", thread_id=thread_id, mentions_bot=True)

    bot_user = MagicMock()
    bot_user.id = 99
    bot._connection = MagicMock()
    bot._connection.user = bot_user
    msg.mentions = [bot_user]

    fake_bridge = AsyncMock()
    bot._bridges[thread_id] = fake_bridge
    bot._thread_participants[thread_id] = {111}

    await bot.on_message(msg)

    fake_bridge.send_message.assert_called_once_with("hello there")


async def test_stop_command_with_session(bot):
    """!stop in a thread with an active session stops and archives."""
    thread_id = 55555
    msg = _make_message("!stop", thread_id=thread_id)
    msg.channel.edit = AsyncMock()

    # Register a fake bridge
    fake_bridge = AsyncMock()
    bot._bridges[thread_id] = fake_bridge

    await bot.on_message(msg)

    fake_bridge.cancel.assert_called_once()
    fake_bridge.close.assert_called_once()
    msg.channel.send.assert_called_once_with("Session stopped.")
    assert thread_id not in bot._bridges


async def test_stop_session_cancels_listener_before_user_message(bot):
    """_stop_session should cancel/await listener before posting stop confirmation."""
    thread_id = 66666
    channel = MagicMock()
    channel.id = thread_id
    channel.send = AsyncMock()
    channel.edit = AsyncMock()

    listener_cancelled = asyncio.Event()

    async def listener_task():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            listener_cancelled.set()
            raise

    listener = asyncio.create_task(listener_task())
    bot._listeners[thread_id] = listener
    bot._bridges[thread_id] = AsyncMock()

    await bot._stop_session(channel)

    assert listener_cancelled.is_set() or listener.cancelled()
    channel.send.assert_called_once_with("Session stopped.")


async def test_start_session_post_connect_failure(bot):
    """If send_message fails after connect, state is cleaned up."""
    thread = MagicMock()
    thread.id = 12345
    thread.send = AsyncMock()

    fake_bridge = AsyncMock()
    fake_bridge.connect_and_create = AsyncMock(return_value="sess-1")
    fake_bridge.send_message = AsyncMock(side_effect=RuntimeError("send failed"))

    with patch("src.bot.Bridge", return_value=fake_bridge):
        await bot._start_session(thread, "test prompt")

    # Bridge should be cleaned up
    assert 12345 not in bot._bridges
    # User should be notified
    assert any("Failed" in str(call) for call in thread.send.call_args_list)


async def test_listen_loop_reconnects_on_connection_lost(bot):
    """Listen loop attempts reconnection on ConnectionLost."""
    thread = MagicMock()
    thread.id = 77777
    thread.send = AsyncMock()

    call_count = 0

    class FakeBridge:
        async def listen(self, on_event):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionLost("disconnected")
            # After successful reconnect, raise a non-ConnectionLost error
            # to break the loop (simulates unexpected crash)
            raise RuntimeError("unexpected")

        async def reconnect(self):
            pass  # Successful reconnect

    bridge = FakeBridge()
    bot._bridges[thread.id] = bridge

    await bot._listen_loop(thread, bridge)

    # Should have sent reconnection messages
    send_calls = [str(c) for c in thread.send.call_args_list]
    assert any("Connection lost" in s for s in send_calls)
    assert any("Reconnected" in s for s in send_calls)


async def test_listen_loop_gives_up_after_max_attempts(bot):
    """Listen loop gives up after MAX_RECONNECT_ATTEMPTS."""
    thread = MagicMock()
    thread.id = 88888
    thread.send = AsyncMock()

    class FakeBridge:
        async def listen(self, on_event):
            raise ConnectionLost("disconnected")

        async def reconnect(self):
            raise RuntimeError("server down")

    bridge = FakeBridge()
    bot._bridges[thread.id] = bridge

    await bot._listen_loop(thread, bridge)

    send_calls = [str(c) for c in thread.send.call_args_list]
    assert any("Lost connection" in s for s in send_calls)
    # Thread should be cleaned up
    assert thread.id not in bot._bridges
