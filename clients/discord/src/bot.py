from __future__ import annotations

import asyncio
import logging
from typing import Any

import discord

from .allowlist import is_allowed
from .bridge import Bridge, ConnectionLost
from .config import Config
from .formatter import format_event

log = logging.getLogger("multiagents-discord")

MAX_RECONNECT_ATTEMPTS = 3
BASE_RECONNECT_DELAY = 1  # seconds
MAX_RECONNECT_DELAY = 30  # seconds

_THREAD_CHANNEL_TYPES = tuple(
    t for t in (
        getattr(discord.ChannelType, "public_thread", None),
        getattr(discord.ChannelType, "private_thread", None),
        getattr(discord.ChannelType, "news_thread", None),
    )
    if t is not None
)


class MultiAgentsBot(discord.Client):
    """Discord bot that bridges to the multiagents platform."""

    def __init__(self, config: Config, **kwargs: Any):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents, **kwargs)

        self.config = config
        # thread_id → Bridge
        self._bridges: dict[int, Bridge] = {}
        # thread_id → asyncio.Task (listener)
        self._listeners: dict[int, asyncio.Task] = {}
        # thread_id → asyncio.Task (inactivity timer)
        self._timers: dict[int, asyncio.Task] = {}
        # thread_id → set of allowed user IDs for that thread
        self._thread_participants: dict[int, set[int]] = {}
        # thread_ids currently being intentionally stopped
        self._stopping: set[int] = set()

    def should_handle(self, message: discord.Message) -> bool:
        """Check if this message should be processed."""
        if message.author.bot:
            return False
        if not is_allowed(message.author.id, self.config.allowlist):
            return False
        return True

    def is_mention(self, message: discord.Message) -> bool:
        """Check if the bot is @mentioned in this message."""
        if not self.user:
            return False
        return self.user in message.mentions

    def is_thread_message(self, message: discord.Message) -> bool:
        """Check if this message is inside a thread."""
        return getattr(message.channel, "type", None) in _THREAD_CHANNEL_TYPES

    def is_stop_command(self, message: discord.Message) -> bool:
        """Check if this is a !stop command."""
        return message.content.strip().lower() == "!stop"

    def thread_name(self, prompt: str) -> str:
        """Generate a non-sensitive thread name."""
        return "multiagents-session"

    def _strip_bot_mention(self, text: str) -> str:
        """Remove bot mention tokens from a message body."""
        if not self.user:
            return text.strip()
        text = text.replace(f"<@{self.user.id}>", "")
        text = text.replace(f"<@!{self.user.id}>", "")
        return text.strip()

    async def on_ready(self):
        log.info("Bot ready as %s", self.user)

    async def on_message(self, message: discord.Message):
        if not self.should_handle(message):
            return

        # Stop command in a thread — only if session is active
        if self.is_thread_message(message) and self.is_stop_command(message):
            if message.channel.id in self._bridges:
                await self._stop_session(message.channel)
            return

        # Message in an active thread → forward to session
        if self.is_thread_message(message) and message.channel.id in self._bridges:
            # After session starts, only forward messages that @mention the bot
            # OR are from the thread owner (creator)
            is_owner = message.author.id in self._thread_participants.get(message.channel.id, set())
            if not self.is_mention(message) and not is_owner:
                return
            bridge = self._bridges[message.channel.id]
            prompt = self._strip_bot_mention(message.content)
            if not prompt:
                return
            await bridge.send_message(prompt)
            self._reset_inactivity_timer(message.channel)
            return

        # @mention in a channel → create new thread + session
        if self.is_mention(message):
            # Strip the bot mention from the prompt
            prompt = self._strip_bot_mention(message.content)

            if not prompt:
                prompt = "Start a discussion"

            thread = await message.create_thread(name=self.thread_name(prompt))
            await self._start_session(thread, prompt, creator_id=message.author.id)

    async def _start_session(self, thread: discord.Thread, prompt: str, creator_id: int | None = None):
        """Create a new session and start listening for events."""
        bridge = Bridge(self.config.server_url)

        try:
            session_id = await bridge.connect_and_create(self.config.default_agents)
        except Exception:
            log.exception("Failed to connect to multiagents server")
            try:
                await bridge.close()
            except Exception:
                pass
            await thread.send("Could not connect to multiagents server.")
            return

        self._bridges[thread.id] = bridge
        # Track the thread creator as the initial participant
        if creator_id is not None:
            self._thread_participants[thread.id] = {creator_id}

        try:
            agents_str = ", ".join(self.config.default_agents)
            await thread.send(f"Session started with {agents_str}.")
            await bridge.send_message(prompt)
        except Exception:
            log.exception("Failed to start session for thread %s", thread.id)
            await bridge.close()
            self._bridges.pop(thread.id, None)
            await thread.send("Failed to start session.")
            return

        # Start listening for events in background
        listener = asyncio.create_task(self._listen_loop(thread, bridge))
        self._listeners[thread.id] = listener

        # Start inactivity timer
        self._reset_inactivity_timer(thread)

    async def _listen_loop(self, thread: discord.Thread, bridge: Bridge):
        """Listen for server events with reconnection on disconnect."""
        attempt = 0
        thread_id = thread.id

        async def on_event(event: dict):
            messages = format_event(event)
            for msg in messages:
                await thread.send(msg)

        try:
            while True:
                try:
                    await bridge.listen(on_event)
                except asyncio.CancelledError:
                    raise
                except ConnectionLost:
                    attempt += 1
                    if attempt > MAX_RECONNECT_ATTEMPTS:
                        log.warning("Max reconnect attempts for thread %s", thread.id)
                        if thread_id not in self._stopping:
                            await thread.send("Lost connection to server. Session ended.")
                        break

                    delay = min(MAX_RECONNECT_DELAY, BASE_RECONNECT_DELAY * (2 ** (attempt - 1)))
                    log.info(
                        "Reconnecting thread %s (attempt %d/%d, delay %.1fs)",
                        thread.id, attempt, MAX_RECONNECT_ATTEMPTS, delay,
                    )
                    if thread_id not in self._stopping:
                        await thread.send(
                            f"Connection lost. Reconnecting (attempt {attempt}/{MAX_RECONNECT_ATTEMPTS})..."
                        )
                    await asyncio.sleep(delay)

                    try:
                        await bridge.reconnect()
                        attempt = 0
                        if thread_id not in self._stopping:
                            await thread.send("Reconnected.")
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        log.exception("Reconnect failed for thread %s", thread.id)
                except Exception:
                    log.exception("Unexpected error in listener for thread %s", thread.id)
                    if thread_id not in self._stopping:
                        await thread.send("An error occurred. Session ended.")
                    break
        except asyncio.CancelledError:
            pass
        finally:
            self._cleanup_thread(thread.id)

    async def _stop_session(self, channel: discord.Thread | Any):
        """Stop the session for a thread."""
        thread_id = channel.id
        self._stopping.add(thread_id)
        listener = self._listeners.get(thread_id)
        if listener and not listener.done():
            listener.cancel()
            try:
                await listener
            except asyncio.CancelledError:
                pass
            except Exception:
                log.exception("Listener shutdown failed for thread %s", thread_id)

        bridge = self._bridges.get(thread_id)
        if bridge:
            try:
                await bridge.cancel()
            except Exception:
                log.debug("bridge.cancel() failed for thread %s", thread_id)
            try:
                await bridge.close()
            except Exception:
                log.debug("bridge.close() failed for thread %s", thread_id)
        await channel.send("Session stopped.")
        self._cleanup_thread(thread_id)
        self._stopping.discard(thread_id)
        if hasattr(channel, "edit"):
            try:
                await channel.edit(archived=True)
            except Exception:
                pass

    def _cleanup_thread(self, thread_id: int):
        """Clean up all state for a thread."""
        self._bridges.pop(thread_id, None)
        self._thread_participants.pop(thread_id, None)
        listener = self._listeners.pop(thread_id, None)
        if listener and not listener.done():
            listener.cancel()
        timer = self._timers.pop(thread_id, None)
        if timer and not timer.done():
            timer.cancel()

    def _reset_inactivity_timer(self, channel: discord.Thread | Any):
        """Reset the inactivity timer for a thread."""
        thread_id = channel.id
        old_timer = self._timers.get(thread_id)
        if old_timer and not old_timer.done():
            old_timer.cancel()

        async def _timeout():
            await asyncio.sleep(self.config.inactivity_timeout)
            await self._stop_session(channel)

        self._timers[thread_id] = asyncio.create_task(_timeout())
