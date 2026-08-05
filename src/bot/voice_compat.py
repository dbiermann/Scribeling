"""Compatibility fixes for discord-ext-voice-recv (a pinned fork; see
requirements.txt), to avoid crashing when receving non-Opus data.

Two layers fix this:
     a. `PacketRouter.feed_rtp` -- reject any RTP packet whose payload
        type isn't Opus (120 / 0x78
     b. `PacketRouter._do_run` -- defense in depth: makes a single frame's
        decode failure non-fatal regardless of cause
"""

from __future__ import annotations

import logging

from discord.ext.voice_recv.router import PacketRouter

log = logging.getLogger(__name__)

_OPUS_PAYLOAD_TYPE = 0x78  # 120 -- the only RTP payload type discord.py sends audio as

_router_hardened = False


def patch_router_hardening() -> None:
    global _router_hardened
    if _router_hardened:
        return
    _router_hardened = True
    _patch_ssrc_payload_filter()
    _patch_router_resilience()


def _patch_ssrc_payload_filter() -> None:
    original_feed_rtp = PacketRouter.feed_rtp

    def filtered_feed_rtp(self, packet) -> None:
        if packet.payload != _OPUS_PAYLOAD_TYPE:
            log.debug(
                "Dropping non-opus rtp packet (payload_type=%s, ssrc=%s) -- likely video",
                packet.payload,
                packet.ssrc,
            )
            with self._lock:
                if packet.ssrc not in self._dropped_ssrcs:
                    self._dropped_ssrcs.append(packet.ssrc)
            return
        original_feed_rtp(self, packet)

    PacketRouter.feed_rtp = filtered_feed_rtp


def _patch_router_resilience() -> None:
    def resilient_do_run(self) -> None:
        while not self._end_thread.is_set():
            self.waiter.wait()
            with self._lock:
                for decoder in self.waiter.items:
                    try:
                        data = decoder.pop_data()
                    except Exception:
                        log.debug(
                            "Dropping frame for ssrc=%s after a decode error",
                            decoder.ssrc,
                            exc_info=True,
                        )
                        continue
                    if data is not None:
                        self.sink.write(data.source, data)

    PacketRouter._do_run = resilient_do_run
