import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Optional

import numpy as np
import pyopenjtalk

from pipecat.frames.frames import Frame, TTSAudioRawFrame
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TTSService


CHUNK_SIZE = 4096


class PiperPlusTTSService(TTSService):
    def __init__(
        self,
        *,
        speed: float = 1.0,
        half_tone: float = 0.0,
        **kwargs,
    ):
        settings = TTSSettings(
            model=None,
            voice="pyopenjtalk",
            language="ja",
        )
        super().__init__(
            push_start_frame=True,
            push_stop_frames=True,
            settings=settings,
            **kwargs,
        )
        self._speed = speed
        self._half_tone = half_tone

    def reset(self) -> None:
        self._buffer = bytearray()
        if hasattr(self, '_context_id'):
            self._context_id = None

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        from loguru import logger
        logger.debug(f"TTS received text: '{text}'")

        audio, sr = await asyncio.to_thread(
            pyopenjtalk.tts, text, self._speed, self._half_tone
        )

        if audio.dtype == np.float64 and audio.max() > 1.0:
            audio_int16 = np.clip(audio, -32768, 32767).astype(np.int16)
        else:
            audio_int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
        audio_bytes = audio_int16.tobytes()

        logger.debug(f"TTS raw: sr={sr}, len={len(audio)}samples, max={audio_int16.max()}")

        async def _chunked_iterator() -> AsyncIterator[bytes]:
            for i in range(0, len(audio_bytes), CHUNK_SIZE):
                yield audio_bytes[i : i + CHUNK_SIZE]

        async for frame in self._stream_audio_frames_from_iterator(
            _chunked_iterator(),
            in_sample_rate=sr,
            context_id=context_id,
        ):
            if isinstance(frame, TTSAudioRawFrame):
                audio_arr = np.frombuffer(frame.audio, dtype=np.int16)
                logger.debug(f"TTS frame out: {len(frame.audio)}B, sr={frame.sample_rate}, max={audio_arr.max()}")
            yield frame
