# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - 2026-07-04

### Added
- **Edge TTS Support**: Replaced Bark TTS with `EdgeTTSService` (`tts_edge.py`) using Microsoft Edge TTS (`ja-JP-NanamiNeural`). Decodes MP3 output via PyAV, resamples from 24kHz to 16kHz, outputs int16 PCM.
- **BufferingTextAggregator**: Custom aggregator that accumulates all LLM response text and synthesizes once per turn (via `LLMFullResponseEndFrame`), eliminating sentence-by-sentence gaps between audio segments.

### Changed
- **VAD Sensitivity**: Lowered `confidence` from 0.5 to 0.3 and `start_secs` from 0.2s to 0.1s for better speech detection.
- **Greeting Delay**: Increased initial greeting delay from 2s to 10s after connection.
- **Removed Bark TTS**: Deleted `tts_bark.py` and removed `"bark[all]"` dependency from `pyproject.toml`.

### Fixed
- **TTS Buffer Never Flushed**: Monkey-patched `LLMAssistantAggregator._handle_llm_end` to forward `LLMFullResponseEndFrame` downstream to TTS, so buffered text is actually synthesized.
- **Greeting Not Synthesized**: Pushed `LLMFullResponseEndFrame` after greeting `TextFrame` to trigger TTS flush.

### Changed
- **System Prompt Update**: Updated system instruction in `bot.py` to prevent alphabet reading/spelling (e.g. "A, B, C") and English conversation; the LLM now always responds in Japanese.
- **LLM State Reset on Reconnection**: Expanded `_reset_service()` in `bot.py` to clear accumulated LLM service state across connections: clears `_appended_system_instructions`, `_functions`, `_redundant_registration_warned`, `_explicitly_unregistered_function_names`, cancels pending `_function_call_tasks`, `_sequential_runner_task`, and `_summary_task`. Also explicitly clears `LLMContext._messages` at the start of each connection to ensure conversation history does not carry over from previous sessions. This prevents the LLM from remembering previous conversations after reconnection.
- **Comprehensive Service State Reset**: Expanded `_reset_service()` in `bot.py` to reset all STT-internal attributes that persist across connections (`_finalize_pending`, `_finalize_requested`, `_last_transcript_time`, `_last_audio_time`, `_can_reconnect`, `_need_reconnect`, `_reconnecting`, `_muted`). Also explicitly cancels any dangling `_ttfb_timeout_task` left from the previous connection's VAD stop cycle.

### Fixed
- **Audio Connector Session ID Mismatch**: Fixed `server.py` `_connect_audio_connector_async()` to stop **all** previous Audio Connectors before creating a new one. Previously it was passing the new session ID to the stop function, which never matched the old connector entry, causing connectors to leak and accumulate across reconnections.

## [Unreleased] - 2026-07-02

### Added
- **Model Preloading**: Implemented `preload_models()` to pre-load LLM/STT/TTS/VAD models at server startup, reducing initial connection latency.
- **Keepalive Heartbeat**: Added keepalive task in `server.py` to send WebSocket heartbeats every 10 seconds for connection stability.

### Changed
- **Global Model Management**: Changed LLM/STT/TTS services from per-request generation to global shared instances, improving memory efficiency and response speed.
- **VAD Parameter Tuning**: Adjusted voice detection sensitivity (`confidence: 0.7→0.5`, `start_secs: 0.3→0.2`, `stop_secs: 0.8→0.2`, `min_volume: 0.4→0.0`).
- **Audio Debug Logging**: Added `AudioFrameLogger` processor to log received audio frame size and sample rate.
- **Per-Connection Transport**: Moved `FastAPIWebsocketTransport` creation from `bot.py` to `server.py` so each WebSocket connection gets a fresh transport instance, preventing stale buffer/state carryover.

### Fixed
- **State Leak Across Reconnections**: Added `_reset_service()` in `bot.py` to clear internal Pipecat processor state (`_cancelling`, `_user_speaking`, `_audio_buffer`, `_content`, `_wave`, etc.) before starting a new pipeline with shared service instances.
- **Transport Cleanup on Disconnect**: Added `transport.cleanup()` call in `server.py`'s `finally` block to ensure transport resources are properly released after each connection.
- **Stability Issues**: Prevented connection timeouts caused by model loading delays through preloading and global sharing of models.

## [Unreleased] - 2026-06-30

### Added
- **Voice API (PSTN) Support**: Added support for connecting via Vonage Voice API (phone calls) in addition to the existing Video API.
- **NCCO Webhook Endpoint**: Implemented `/voice/webhook` in `server.py` to handle inbound Vonage Voice calls and bridge them to the bot via WebSocket.
- **Automatic Environment Configuration**: Updated `start.sh` to automatically detect the Cloudflare Tunnel URL and update `WS_URI` and `VONAGE_WEBHOOK_URL` in `.env`.
- **Improved Greeting Logic**: Modified `bot.py` to send an initial greeting via `TextFrame` upon connection, preventing "No user query found" errors in the LLM when no user input is present.
- **Documentation**: Updated `README.md` (English) and `README-JP.md` (Japanese) with new architecture, demo flows, and API endpoint information.

### Changed
- **Architecture**: The system now supports a dual-mode connectivity:
  - **Video Mode**: Client (Browser) → Video Session → Audio Connector → Bot.
  - **Voice Mode**: Phone Call → Voice API → Webhook/NCCO → Bot.
- **Deployment**: Optimized `start.sh` for better compatibility with macOS and automatic Cloudflare Tunnel management.
- **Configuration**: Added `VONAGE_WEBHOOK_URL` to `.env.example`.

### Fixed
- **Video Client Reconnection Silence**: Modified `server.py` to stop the previous Audio Connector before starting a new one on each `/demo/connect` call. This resolved audio bridge conflicts caused by multiple Audio Connectors running concurrently during reconnection.
