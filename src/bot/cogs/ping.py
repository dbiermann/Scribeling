"""Discord-facing layer: replies "pong" to "ping" in the command channel."""
from __future__ import annotations

import logging

import discord
from discord.ext import commands

from bot.config import settings

log = logging.getLogger(__name__)


class PingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id != settings.command_channel_id:
            return
        if message.content.strip().lower() == "ping":
            await message.channel.send("pong")


async def setup(bot: commands.Bot):
    await bot.add_cog(PingCog(bot))
