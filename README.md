# Pipecat Voice Bot — LM Studio + pyopenjtalk + Vonage

Voice conversation bot powered by LM Studio (local LLM/STT) and pyopenjtalk (local Japanese TTS). The bot supports both **Video Sessions** (via Browser SDK) and **Phone Calls** (via PSTN/Vonage Voice API).

## Architecture

```
                    ┌─────────────────────────────────────┐
                    │        Cloudflare Tunnel            │
                    │     (WebSocket + HTTP/HTTPS)        │
                    │         trycloudflare.com           │
                    └──────────┬──────────────────────────┘
                               │
                    localhost:8005
                               │
                    ┌──────────▼──────────────────────────┐
                    │  FastAPI + Pipecat                   │
                    │  Pipeline: STT → LLM → TTS          │
                    │  ┌────────────────────────────────┐  │
                    │  │  LM Studio (:1234)             │  │
                    │  │  ├── LLM (gemma/llama etc)     │  │
                    │  │  └── Whisper (STT)             │  │
                    │  │  pyopenjtalk (TTS)             │  │
                    │  └────────────────────────────────┘  │
                    └──────────────────────────────────────┘
```

### Video Mode (Browser → Video Session → Audio Connector)

```
1. Browser                2. POST /demo/connect         3. Create Session
   ┌──────┐   ──────►   ┌──────────┐   ──────►   ┌──────────────┐
   │Client│               │FastAPI   │               │Vonage Cloud  │
   └──────┘               └──────────┘               │(Video API)   │
       ▲                                              └──────┬───────┘
       │                                                     │
       │  5. Join session (OT.initSession)                   │
       │     + publish/subscribe audio                       │ 4. Start Audio
       └─────────────────────────────────────────────────────┘    Connector
                                                                    │
                                                            ┌───────▼───────┐
                                                            │  WebSocket   │
                                                            │  /ws          │
                                                            └───────┬───────┘
                                                                    │
                                                            ┌───────▼───────┐
                                                            │  Pipecat Bot  │
                                                            │  STT→LLM→TTS  │
                                                            └───────────────┘

1. User opens the tunnel URL in a browser (static/index.html).
2. User clicks "接続" → browser sends POST /demo/connect to the server.
3. Server creates a Vonage Video session via vng.video.create_session().
4. Server starts an Audio Connector via vng.video.start_audio_connector(),
   pointing it to wss://<tunnel-url>/ws (the bot's WebSocket endpoint).
5. Browser joins the session via OT.initSession(applicationId, sessionId)
   and session.connect(token), then publishes microphone audio and
   subscribes to the bot's audio stream.
6. Audio flows: Browser ↔ Vonage Cloud ↔ Audio Connector ↔ Bot.
```

### Voice Mode (Phone Call → Voice API → Webhook/NCCO)

```
1. Inbound Call           2. GET /voice/webhook         3. Return NCCO
   ┌──────┐   ──────►   ┌──────────┐   ──────►   ┌──────────────┐
   │Phone  │               │FastAPI   │               │Vonage Voice  │
   └──────┘               └──────────┘               │Platform      │
       ▲                                              └──────┬───────┘
       │                                                     │
       │  5. Call bridged to WebSocket                       │ 4. Connect to
       └─────────────────────────────────────────────────────┘    WebSocket
                                                                    │
                                                            ┌───────▼───────┐
                                                            │  WebSocket   │
                                                            │  /ws          │
                                                            └───────┬───────┘
                                                                    │
                                                            ┌───────▼───────┐
                                                            │  Pipecat Bot  │
                                                            │  STT→LLM→TTS  │
                                                            └───────────────┘

1. A user calls your Vonage phone number.
2. Vonage sends a GET request to the configured Answer URL
   (https://<tunnel-url>/voice/webhook) with call metadata in
   query parameters (to, from, conversation_uuid, etc.).
3. Server returns an NCCO (Nexmo Call Control Object) instructing
   Vonage to connect the call to the bot via WebSocket:
   [
     {
       "action": "connect",
       "endpoint": [
         {
           "type": "websocket",
           "uri": "wss://<tunnel-url>/ws"
         }
       ]
     }
   ]
4. Vonage establishes a WebSocket connection to the provided URI.
5. The call is now bridged: audio flows bidirectionally between
   the phone and the Pipecat pipeline.
6. On connect, the bot sends a greeting ("こんにちは...") via TTS.
7. Subsequent user speech follows: STT → LLM → TTS → phone.
```

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- [LM Studio](https://lmstudio.ai/) with an LLM and Whisper model loaded, listening on `localhost:1234`
- [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) (`brew install cloudflared`)

## Setup

### 1. Environment variables

```bash
cp .env.example .env
```

Edit `.env`:

| Variable | Example | Description |
|----------|---------|-------------|
| `LM_STUDIO_BASE_URL` | `http://localhost:1234/v1` | LM Studio API endpoint |
| `STT_LANGUAGE` | `ja` | Whisper language code |
| `VONAGE_APPLICATION_ID` | `abcd1234-...` | Vonage Application ID (required) |
| `VONAGE_PRIVATE_KEY` | `-----BEGIN PRIVATE KEY-----...` | Vonage private key (path or inline, required) |
| `WS_URI` | `wss://xxx.trycloudflare.com/ws` | Public WebSocket URL (auto-set by start.sh) |
| `VONAGE_WEBHOOK_URL` | `https://xxx.trycloudflare.com/voice/webhook` | Vonage Voice API Answer URL (auto-set by start.sh) |

### 2. Install dependencies

```bash
uv sync
```

## Running

### 3. Start LM Studio

Load an LLM and Whisper model, ensure the server is listening on `localhost:1234`.

### 4. One-command start (recommended)

```bash
bash start.sh
```

This automatically:
1. Starts a Cloudflare Tunnel (`cloudflared`) and captures the public URL
2. Updates `WS_URI` and `VONAGE_WEBHOOK_URL` in `.env`
3. Restarts the Python server
4. Prints the URLs and instructions

### 5. Stop the application

To stop the running components, use the following commands:

#### Stop Python Server
```bash
# Find the PID and kill it
ps aux | grep -E "python|uvicorn" | grep -v grep | awk '{print $2}' | xargs kill -9
```

#### Stop Cloudflare Tunnel
```bash
# Find the PID and kill it
ps aux | grep cloudflared | grep -v grep | awk '{print $2}' | xargs kill -9
```

#### Stop All Processes (Quickest)
```bash
pkill -f server.py && pkill -f cloudflared
```

### 6. Connect
...
## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serves frontend (`static/index.html`) |
| `/health` | GET | Health check |
| `/ws` | WebSocket | Pipecat pipeline endpoint (consumed by Audio Connector / Voice API) |
| `/connect` | POST | Vonage Audio Connector (legacy, requires `WS_URI` env) |
| `/demo/connect` | POST | One-shot demo: creates session + token + starts Audio Connector (Video Mode) |
| `/voice/webhook` | GET | Vonage Voice API Answer Webhook: returns NCCO to bridge call to `/ws` |

## Project Structure

```
├── server.py                 # FastAPI server (HTTP + WebSocket)
├── bot.py                    # Pipecat pipeline definition
├── lm_studio_stt.py          # LM Studio STT service (JSON with base64 audio)
├── tts_piper_plus.py         # Piper-plus TTS wrapper (Ja/En)
├── pyproject.toml            # Dependencies
├── setup.sh                  # TTS voice model downloader
├── start.sh                  # One-command startup script
├── .env                      # Credentials (git-ignored)
├── .env.example              # Template
├── static/
│   └── index.html            # Frontend (Vonage Video JS SDK)
└── docs/
    ├── CHANGELOG.md
    ├── PLAN_VoiceAPI_en.md
    └── PLAN_VoiceAPI_jp.md
```

## Demo Flow

### 1. Video Mode (Browser-based)
1. User opens the tunnel URL in a browser
2. Clicks **接続** → `POST /demo/connect` is called
3. Server creates a Vonage Video session, generates a JWT token, and starts the Audio Connector (pointing to `wss://tunnel-url/ws`)
4. Frontend joins the session via `OT.initSession(applicationId, sessionId)` + `session.connect(token)`
5. Frontend publishes microphone audio and subscribes to the bot's audio stream
6. Audio flows: Browser → Vonage Cloud → Audio Connector → Bot Pipeline → Audio Connector → Browser

### 2. Voice Mode (Phone Call)
1. Configure **Answer URL** in Vonage Dashboard to `https://<tunnel-url>/voice/webhook`
2. A user calls your Vonage number
3. Vonage sends a webhook to `/voice/webhook`, which returns an NCCO
4. The call is bridged to the bot via WebSocket (`/ws`)
5. Audio flows: Phone → Vonage Voice Platform → WebSocket → Bot Pipeline → WebSocket → Phone

## Sequencing

The bot initiates conversation on client connection by sending a text greeting via the TTS engine. No wake word required.
