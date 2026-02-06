from __future__ import annotations

import asyncio
import logging
from typing import Any

import discord

from .allowlist import is_allowed
from .bridge import Bridge
from .config import Config
from .formatter import format_event

log = logging.getLogger("multiagents-discord")


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
        return hasattr(message.channel, "type") and "thread" in str(message.channel.type)

    def is_stop_command(self, message: discord.Message) -> bool:
        """Check if this is a !stop command."""
        return message.content.strip().lower() == "!stop"

    def thread_name(self, prompt: str) -> str:
        """Generate a thread name from the prompt (max 50 chars)."""
        if len(prompt) <= 50:
            return prompt
        return prompt[:49] + "…"

    async def on_ready(self):
        log.info("Bot ready as %s", self.user)

    async def on_message(self, message: discord.Message):
        if not self.should_handle(message):
            return

        # Stop command in a thread
        if self.is_thread_message(message) and self.is_stop_command(message):
            await self._stop_session(message.channel)
            return

        # Message in an active thread → forward to session
        if self.is_thread_message(message) and message.channel.id in self._bridges:
            bridge = self._bridges[message.channel.id]
            await bridge.send_message(message.content)
            self._reset_inactivity_timer(message.channel)
            return

        # @mention in a channel → create new thread + session
        if self.is_mention(message):
            # Strip the bot mention from the prompt
            prompt = message.content
            if self.user:
                prompt = prompt.replace(f"<@{self.user.id}>", "").strip()
                prompt = prompt.replace(f"<@!{self.user.id}>", "").strip()

            if not prompt:
                prompt = "Start a discussion"

            thread = await message.create_thread(name=self.thread_name(prompt))
            await self._start_session(thread, prompt)

    async def _start_session(self, thread: discord.Thread, prompt: str):
        """Create a new session and start listening for events."""
        bridge = Bridge(self.config.server_url)

        try:
            session_id = await bridge.connect_and_create(self.config.default_agents)
        except Exception:
            log.exception("Failed to connect to multiagents server")
            await thread.send("Could not connect to multiagents server.")
            return

        self._bridges[thread.id] = bridge

        agents_str = ", ".join(self.config.default_agents)
        await thread.send(f"Session started with {agents_str}.")

        # Send the initial prompt
        await bridge.send_message(prompt)

        # Start listening for events in background
        listener = asyncio.create_task(self._listen_loop(thread, bridge))
        self._listeners[thread.id] = listener

        # Start inactivity timer
        self._reset_inactivity_timer(thread)

    async def _listen_loop(self, thread: discord.Thread, bridge: Bridge):
        """Listen for server events and post them to the thread."""

        async def on_event(event: dict):
            messages = format_event(event)
            for msg in messages:
                await thread.send(msg)

        try:
            await bridge.listen(on_event)
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("Listener error for thread %s", thread.id)
        finally:
            self._cleanup_thread(thread.id)

    async def _stop_session(self, channel: discord.Thread | Any):
        """Stop the session for a thread."""
        thread_id = channel.id
        bridge = self._bridges.get(thread_id)
        if bridge:
            await bridge.cancel()
            await bridge.close()
        await channel.send("Session stopped.")
        self._cleanup_thread(thread_id)
        if hasattr(channel, "edit"):
            try:
                await channel.edit(archived=True)
            except Exception:
                pass

    def _cleanup_thread(self, thread_id: int):
        """Clean up all state for a thread."""
        self._bridges.pop(thread_id, None)
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
