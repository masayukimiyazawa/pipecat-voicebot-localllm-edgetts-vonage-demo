# Pipecat Voice Bot — Plan

## Overview

A voice conversation bot connecting through the **Vonage Unified Video API**. The browser uses the Vonage Video JS SDK to join a session, and the Vonage Audio Connector bridges audio to the Pipecat pipeline running on the server.

```
Browser (Vonage Video JS SDK)
  │ OT.initSession(applicationId, sessionId)
  │ session.connect(token)
  │ session.publish() / session.subscribe()
  ▼
Vonage Cloud
  │ Audio Connector (raw PCM16 WebSocket)
  ▼
FastAPI + Pipecat (localhost:8005)
  │ pipeline: STT → LLM → TTS
  ▼
Client hears response
```

## Architecture

| Layer | Technology |
|-------|------------|
| Frontend | Vonage Video JS SDK (`OT`) via CDN |
| Server | FastAPI + uvicorn (port 8005) |
| Pipeline | Pipecat (`FastAPIWebsocketTransport`) |
| STT | LM Studio Whisper (`LMStudioSTTService`, JSON/base64 POST) |
| LLM | LM Studio (`OpenAILLMService`, chat completions) |
| TTS | Piper-plus (`PiperPlusTTSService`, local ONNX) |
| Session bridge | Vonage Audio Connector (raw PCM16, 16kHz, mono) |

## Audio Flow

| Direction | Source → Target | Format | Medium |
|-----------|----------------|--------|--------|
| User → Bot | Browser mic → Vonage Cloud | Opus/WebRTC | Vonage Video SDK |
| Bot ← Vonage | Audio Connector → Server `/ws` | PCM16 16kHz mono | WebSocket (raw binary) |
| Bot → Vonage | Server `/ws` → Audio Connector | PCM16 16kHz mono | WebSocket (raw binary) |
| Bot → User | Vonage Cloud → Browser speaker | Opus/WebRTC | Vonage Video SDK |

## Interruption

The `VonageFrameSerializer` handles `InterruptionFrame` by sending `{"action": "clear"}` JSON to the Vonage Audio Connector, which clears its playback buffer.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Serve `static/index.html` |
| GET | `/health` | Health check |
| POST | `/demo/connect` | Create session + generate token + start Audio Connector |
| POST | `/connect` | Legacy Audio Connector (requires `WS_URI` env) |
| WebSocket | `/ws` | Pipecat pipeline (consumed by Audio Connector) |

## Key Files

```
├── server.py                   # FastAPI: static files + REST + WebSocket
├── bot.py                      # Pipecat pipeline
│   ├── LMStudioSTTService      # STT (LM Studio, JSON body)
│   ├── OpenAILLMService        # LLM (LM Studio, chat completions)
│   ├── PiperPlusTTSService     # TTS (Piper-plus, local ONNX)
│   └── VonageFrameSerializer   # Serializer for Audio Connector protocol
├── lm_studio_stt.py            # LM Studio STT implementation
├── tts_piper_plus.py           # Piper-plus TTS wrapper (Ja/En bilingual)
├── static/index.html           # Vonage Video JS SDK frontend
├── docs/PLAN.md                # English plan (this file)
└── docs/PLAN.ja.md             # Japanese plan
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `pipecat-ai[openai,websocket,silero,piper,runner]` | Pipeline, transport, VAD, TTS |
| `vonage>=3.3.1` | Vonage REST API (auth, session) |
| `vonage-video` | Audio Connector API |
| `fastapi`, `uvicorn` | Web server |
| `python-dotenv` | Environment variables |
| `pyopenjtalk-plus` | Japanese TTS support |

## Env Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `LM_STUDIO_BASE_URL` | Yes | LM Studio API endpoint |
| `LM_MODEL` | No | LLM model name (empty = default) |
| `STT_MODEL` | No | Whisper model name |
| `STT_LANGUAGE` | No | STT language code |
| `PIPER_PLUS_VOICE_ID` | No | TTS voice model |
| `VONAGE_APPLICATION_ID` | Yes | Vonage application UUID |
| `VONAGE_PRIVATE_KEY` | Yes | Private key (path or inline) |
| `VONAGE_AUDIO_RATE` | No | Audio sample rate (default 16000) |
| `WS_URI` | For `/connect` | wss://ngrok-url/ws |

## Demo Flow

1. `ngrok http 8005` → `https://abc123.ngrok.dev`
2. Open the ngrok URL in a browser
3. Click **接続** → `POST /demo/connect`:
   - Server creates Vonage session (via REST API)
   - Server generates JWT client token
   - Server starts Audio Connector → `wss://ngrok-url/ws`
   - Returns `{ session_id, token, application_id }`
4. Frontend: `OT.initSession(applicationId, sessionId)`, `session.connect(token)`
5. Frontend publishes mic, subscribes to bot audio
6. Bot hears user → STT → LLM → TTS → responds to user
