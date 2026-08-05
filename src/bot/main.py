from __future__ import annotations

import asyncio
import logging

import discord
from discord.ext import commands

from bot.config import settings

log = logging.getLogger(__name__)


def build_bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.voice_states = True
    intents.message_content = True

    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        log.info("Logged in as %s (id=%s)", bot.user, bot.user.id)
        try:
            if settings.guild_id:
                guild = discord.Object(id=int(settings.guild_id))
                bot.tree.copy_global_to(guild=guild)
                synced = await bot.tree.sync(guild=guild)
            else:
                synced = await bot.tree.sync()
            log.info("Synced slash commands: %s", [c.name for c in synced])
        except Exception:
            log.exception("Failed to sync slash commands")

    return bot


async def main() -> None:
    logging.basicConfig(level=settings.log_level)

    bot = build_bot()

    # Cogs are loaded as extensions so each feature area stays self-contained
    await bot.load_extension("bot.cogs.transcribe")
    await bot.load_extension("bot.cogs.ping")

    async with bot:
        await bot.start(settings.discord_token)


if __name__ == "__main__":
    asyncio.run(main())
