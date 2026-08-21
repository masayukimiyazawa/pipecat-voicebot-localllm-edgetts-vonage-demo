# Pipecat Voice Bot — LM Studio + Edge TTS + Vonage

Voice conversation bot powered by LM Studio (local LLM/STT) and Edge TTS (Microsoft Azure, Japanese). The bot uses **Video Sessions** (via Browser SDK + Audio Connector).

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
                    │  └────────────────────────────────┘  │
                    │  Edge TTS (ja-JP-NanamiNeural)       │
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
| `LM_MODEL` | `gemma-4-26B-A4B-it-MLX-8bit` | LLM model name |
| `STT_LANGUAGE` | `ja` | Whisper language code |
| `VONAGE_APPLICATION_ID` | `abcd1234-...` | Vonage Application ID (required) |
| `VONAGE_PRIVATE_KEY` | `./private.key` | Vonage private key path (required) |
| `VONAGE_AUDIO_RATE` | `16000` | Audio sample rate |

### 2. Install dependencies

```bash
uv sync
```

## Running

### 3. Start LM Studio

Load an LLM and Whisper model, ensure the server is listening on `localhost:1234`.

### 4. Start server & tunnel

```bash
# Start the application
bash start.sh
```

The script handles starting the server and the Cloudflare tunnel. Note the tunnel URL in the output.

The server pre-loads all models at startup (may take ~60s).

### 5. Connect

Open the tunnel URL in a browser. Click **接続**. The bot will greet you after 10 seconds.

### Stop

```bash
pkill -f server.py && pkill -f cloudflared
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serves frontend (`static/index.html`) |
| `/health` | GET | Health check |
| `/ws` | WebSocket | Pipecat pipeline endpoint (consumed by Audio Connector / Voice API) |
| `/connect` | POST | Vonage Audio Connector (legacy, requires `WS_URI` env) |
| `/demo/connect` | POST | One-shot demo: creates session + token + starts Audio Connector |
| `/voice/webhook` | GET | Vonage Voice API Answer Webhook: returns NCCO to bridge call to `/ws` |

## Project Structure

```
├── server.py                 # FastAPI server (HTTP + WebSocket)
├── bot.py                    # Pipecat pipeline definition
├── tts_edge.py               # Edge TTS service (Microsoft Azure)
├── pyproject.toml            # Dependencies
├── .env                      # Credentials (git-ignored)
├── static/
│   └── index.html            # Frontend (Vonage Video JS SDK)
└── docs/
    └── CHANGELOG.md
```

## Demo Flow

1. User opens the tunnel URL in a browser
2. Clicks **接続** → `POST /demo/connect` is called
3. Server creates a Vonage Video session, generates a JWT token, and starts the Audio Connector (pointing to `wss://tunnel-url/ws`)
4. Frontend joins the session via `OT.initSession(applicationId, sessionId)` + `session.connect(token)`
5. Frontend publishes microphone audio and subscribes to the bot's audio stream
6. Audio flows: Browser → Vonage Cloud → Audio Connector → Bot Pipeline → Audio Connector → Browser

The bot greets the user 10 seconds after connection via TTS. Subsequent user speech follows: STT → LLM → TTS.

## Demo Video Clip (Japanese)

https://youtu.be/rJUi4qRV0v4?si=rOaV3trFJpBU3oWW

### Voice Mode (Phone Call → Voice API → Webhook)

1. Set your Vonage Voice API Answer URL to `https://<tunnel-url>/voice/webhook`
2. Call your Vonage number
3. The call is bridged to the bot via WebSocket

