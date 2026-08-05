from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import discord
from discord import app_commands
from discord.ext import commands, voice_recv

from bot import stt_model, voice_compat
from bot.config import settings
from bot.transcription import TranscriptionSink

log = logging.getLogger(__name__)

# Generous timeout for the flush+disconnect steps in /stop: CPU whisper
STOP_TIMEOUT_S = 30.0


class TranscribeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # At most one active session per guild
        self._sessions: dict[
            int, tuple[voice_recv.VoiceRecvClient, TranscriptionSink]
        ] = {}
        # Guilds currently running /stop -- guards against a second /stop
        # racing the first one while flush/disconnect are still in flight.
        self._stopping: set[int] = set()
        self._transcriber: stt_model.Transcriber | None = None
        self._executor: ThreadPoolExecutor | None = None

    async def cog_load(self) -> None:

        if not discord.opus.is_loaded():
            discord.opus._load_default()

        # Patch router to not crash from non opus packets
        voice_compat.patch_router_hardening()

        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="whisper")
        loop = asyncio.get_running_loop()
        self._transcriber = await loop.run_in_executor(
            self._executor, stt_model.load_transcriber, settings
        )

    async def cog_unload(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)

    @app_commands.command(
        name="transcribe",
        description="Join your current voice channel and start live transcription",
    )
    async def transcribe(self, interaction: discord.Interaction):
        if interaction.guild_id in self._sessions:
            await interaction.response.send_message(
                "Already connected to a voice channel in this server. Use /stop first."
            )
            return

        if self._transcriber is None:
            await interaction.response.send_message(
                "Transcription model is still starting up, try again in a moment.",
                ephemeral=True,
            )
            return

        voice_state = getattr(interaction.user, "voice", None)
        if voice_state is None or voice_state.channel is None:
            await interaction.response.send_message("Must join voice channel first")
            return
        channel = voice_state.channel

        await interaction.response.defer()

        try:
            voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)
        except Exception:
            log.exception("Failed to join voice channel %s", channel.name)
            await interaction.followup.send("Failed to join that voice channel.")
            return

        try:
            sink = TranscriptionSink(
                transcriber=self._transcriber,
                executor=self._executor,
                transcripts_dir=settings.transcripts_dir,
                silence_debounce_s=settings.whisper_silence_debounce_s,
            )
            voice_client.listen(sink)
        except Exception:
            # Without this, a failure here leaves the bot connected to the
            # channel with no session tracked -- undiagnosable and un-/stop-able.
            log.exception("Failed to start listening in voice channel %s", channel.name)
            await voice_client.disconnect(force=True)
            await interaction.followup.send(
                "Joined the voice channel but failed to start transcription."
            )
            return

        self._sessions[interaction.guild_id] = (voice_client, sink)

        await interaction.followup.send(
            f"Joined **{channel.name}** — live transcription will be saved to `{sink.output_path}`."
        )

    @app_commands.command(name="stop", description="Leave the current voice channel")
    async def stop(self, interaction: discord.Interaction):
        if interaction.guild_id in self._stopping:
            await interaction.response.send_message(
                "Already stopping, hang on...", ephemeral=True
            )
            return

        session = self._sessions.get(interaction.guild_id)
        if session is None:
            await interaction.response.send_message(
                "Not currently connected to a voice channel in this server."
            )
            return

        voice_client, sink = session
        # The guild's session slot stays reserved (not popped) until this
        # whole shutdown sequence finishes -- popping it up front let a
        # second /transcribe race in and join voice again while this one was
        # still (potentially indefinitely) stuck flushing/disconnecting.
        self._stopping.add(interaction.guild_id)
        await interaction.response.defer()

        ok = True
        try:
            try:
                await asyncio.wait_for(sink.flush_pending(), timeout=STOP_TIMEOUT_S)
            except Exception:
                log.exception(
                    "Failed to flush pending transcription for guild %s",
                    interaction.guild_id,
                )
                ok = False

            voice_client.stop_listening()

            try:
                await asyncio.wait_for(
                    voice_client.disconnect(), timeout=STOP_TIMEOUT_S
                )
            except Exception:
                log.exception(
                    "Graceful disconnect failed/timed out for guild %s, forcing",
                    interaction.guild_id,
                )
                ok = False
                await voice_client.disconnect(force=True)
        except Exception:
            log.exception(
                "Unexpected error stopping session for guild %s", interaction.guild_id
            )
            ok = False
        finally:
            # Always release the slot and respond, even on failure -- an
            # orphaned session that can never /stop again is worse than one
            # that stopped messily.
            self._sessions.pop(interaction.guild_id, None)
            self._stopping.discard(interaction.guild_id)

        if ok:
            await interaction.followup.send("Left the voice channel.")
        else:
            await interaction.followup.send(
                "Left the voice channel, but something went wrong while stopping "
                "cleanly — check the logs."
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(TranscribeCog(bot))
