from collections.abc import AsyncGenerator, AsyncIterator
from io import BytesIO

import av
import edge_tts
import numpy as np

from pipecat.frames.frames import Frame, TTSAudioRawFrame
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TTSService
from pipecat.utils.text.simple_text_aggregator import (
    Aggregation,
    AggregationType,
    SimpleTextAggregator,
)


EDGE_SAMPLE_RATE = 24000


class BufferingTextAggregator(SimpleTextAggregator):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._buffer = ""

    async def aggregate(self, text: str) -> AsyncIterator[Aggregation]:
        self._buffer += text
        if False:
            yield  # make this an async generator (no-op), text yielded on flush only

    async def flush(self) -> Aggregation | None:
        if self._buffer:
            result = Aggregation(text=self._buffer.strip(" "), type=AggregationType.SENTENCE)
            await self.reset()
            return result
        return None

    async def handle_interruption(self):
        self._buffer = ""

    async def reset(self):
        self._buffer = ""
        self._text = ""


class EdgeTTSService(TTSService):
    def __init__(
        self,
        *,
        voice: str = "ja-JP-NanamiNeural",
        **kwargs,
    ):
        settings = TTSSettings(
            model="edge-tts",
            voice=voice,
            language="ja",
        )
        super().__init__(
            push_start_frame=True,
            push_stop_frames=True,
            stop_frame_timeout_s=30.0,
            settings=settings,
            **kwargs,
        )
        self._voice = voice
        self._text_aggregator = BufferingTextAggregator()

    def can_generate_metrics(self) -> bool:
        return True

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        from loguru import logger

        logger.debug(f"Edge TTS: {text[:80]}...")

        try:
            mp3_chunks: list[bytes] = []
            communicate = edge_tts.Communicate(text, self._voice)
            async for chunk in communicate.stream():
                if chunk["type"] == "audio" and chunk["data"]:
                    mp3_chunks.append(chunk["data"])

            if not mp3_chunks:
                return

            mp3_data = b"".join(mp3_chunks)

            input_container = av.open(BytesIO(mp3_data))
            frames: list[np.ndarray] = []
            for frame in input_container.decode(audio=0):
                if frame:
                    arr = frame.to_ndarray()
                    frames.append(arr)
            input_container.close()

            if not frames:
                return

            combined = np.concatenate(frames, axis=1)
            if combined.shape[0] > 1:
                mono = combined.mean(axis=0)
            else:
                mono = combined[0]

            pcm_int16 = (mono * 32767).clip(-32768, 32767).astype(np.int16).tobytes()

            resampled = await self._resampler.resample(
                pcm_int16, EDGE_SAMPLE_RATE, self.sample_rate
            )
            if resampled:
                yield TTSAudioRawFrame(
                    audio=resampled,
                    sample_rate=self.sample_rate,
                    num_channels=1,
                    context_id=context_id,
                )
        except Exception as e:
            logger.error(f"Edge TTS error: {e}")
