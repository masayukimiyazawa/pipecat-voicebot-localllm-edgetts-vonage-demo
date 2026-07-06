import asyncio
import os
from dotenv import load_dotenv
from fastapi import WebSocket
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.frames.frames import TextFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection
from pipecat.processors.aggregators.llm_response_universal import (
    LLMAssistantAggregator,
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import WebSocketRunnerArguments
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.whisper.stt import WhisperSTTServiceMLX, MLXModel
from pipecat.transcriptions.language import Language
from tts_edge import EdgeTTSService
from pipecat.serializers.vonage import VonageFrameSerializer
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.workers.runner import WorkerRunner

load_dotenv(override=True)

# Monkey-patch LLMAssistantAggregator to forward frames downstream to TTS.
# Pipecat 1.4.0's _handle_text absorbs text for context but does not push
# it to the next processor, starving the TTS service.
_original_handle_text = LLMAssistantAggregator._handle_text
async def _forwarding_handle_text(self, frame: TextFrame):
    await _original_handle_text(self, frame)
    await self.push_frame(frame, FrameDirection.DOWNSTREAM)
LLMAssistantAggregator._handle_text = _forwarding_handle_text

# Also forward LLMFullResponseEndFrame so TTS flushes its audio buffer.
_original_handle_llm_end = LLMAssistantAggregator._handle_llm_end
async def _forwarding_handle_llm_end(self, frame):
    await _original_handle_llm_end(self, frame)
    await self.push_frame(frame, FrameDirection.DOWNSTREAM)
LLMAssistantAggregator._handle_llm_end = _forwarding_handle_llm_end

AUDIO_OUT_SAMPLE_RATE: int = 16_000

LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
LM_MODEL = os.getenv("LM_MODEL", "")
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "ja")

async def run_bot(transport: BaseTransport, handle_sigint: bool, sample_rate: int, websocket: WebSocket):
    llm = OpenAILLMService(
        base_url=LM_STUDIO_BASE_URL,
        api_key="not-needed",
        settings=OpenAILLMService.Settings(
            model=LM_MODEL,
            system_instruction=(
                "あなたは音声アシスタントです。"
                "応答はテキスト読み上げで読まれるため、自然な会話調にしてください。"
                "アルファベットの読み上げ（例: A, B, C）や英会話は行わず、常に日本語で応答してください。"
                "記号やマークダウンは避けてください。"
                "1回の応答は2〜3文程度で、やや詳しめに話してください。"
            ),
        ),
    )

    stt = WhisperSTTServiceMLX(
        settings=WhisperSTTServiceMLX.Settings(
            model=MLXModel.LARGE_V3_TURBO_Q4,
            language=Language(STT_LANGUAGE),
            no_speech_prob=0.3,
        ),
    )

    tts = EdgeTTSService(
        voice="ja-JP-NanamiNeural",
    )

    context = LLMContext()
    # Ensure context starts completely empty (LLMContext() already does this,
    # but be explicit to prevent any residual messages from carrying over)
    context._messages.clear()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(
                    confidence=0.7,
                    start_secs=0.3,
                    stop_secs=0.8,
                    min_volume=0.4,
                ),
            ),
            audio_idle_timeout=2.0,
            user_turn_stop_timeout=5.0,
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            assistant_aggregator,
            tts,
            transport.output(),
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=sample_rate,
            audio_out_sample_rate=AUDIO_OUT_SAMPLE_RATE,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(_transport, _client):
        logger.info("Client connected. Waiting for user input...")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_transport, _client):
        logger.info("Client disconnected. Ending session.")
        await worker.cancel()

    async def _send_delayed_greeting():
        await asyncio.sleep(10)
        logger.info("Sending greeting...")
        await assistant_aggregator.push_frame(
            TextFrame("こんにちは。私の声は聞こえていますか？これからいろいろなお話をしましょう。何か質問があれば何でも聞いてくださいね。"),
            FrameDirection.DOWNSTREAM,
        )
        from pipecat.frames.frames import LLMFullResponseEndFrame
        await assistant_aggregator.push_frame(
            LLMFullResponseEndFrame(),
            FrameDirection.DOWNSTREAM,
        )

    runner = WorkerRunner(handle_sigint=handle_sigint)
    await runner.add_workers(worker)
    greeting_task = asyncio.create_task(_send_delayed_greeting())
    await runner.run()
    greeting_task.cancel()


async def bot(runner_args: WebSocketRunnerArguments, transport: FastAPIWebsocketTransport):
    # Default to 16000 if not specified, but allow override from environment
    sample_rate = int(os.getenv("VONAGE_AUDIO_RATE", "16000"))
    
    logger.info(f"Starting bot with sample rate: {sample_rate}")

    await run_bot(transport, runner_args.handle_sigint, sample_rate, runner_args.websocket)

