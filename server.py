import asyncio
import os
import warnings
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, WebSocket, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pipecat.serializers.vonage import VonageFrameSerializer
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport
from vonage import Auth, HttpClientOptions, Vonage
from vonage_video import AudioConnectorOptions, TokenOptions
from vonage_video.models.audio_connector import AudioConnectorData

load_dotenv(override=True)

warnings.filterwarnings("ignore", message="'asyncio.iscoroutinefunction' is deprecated")


def _require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise HTTPException(status_code=500, detail=f"Missing env var: {name}")
    return val


def _read_private_key(value: str) -> str:
    if value.startswith("-----"):
        return value
    with open(value) as f:
        return f.read()


def _create_vonage_client(application_id: str, private_key: str) -> Vonage:
    auth = Auth(application_id=application_id, private_key=private_key)
    options = HttpClientOptions(video_host="video.api.vonage.com", timeout=30)
    return Vonage(auth=auth, http_client_options=options)


def _generate_client_token(vng: Vonage, session_id: str) -> str:
    raw = vng.video.generate_client_token(
        TokenOptions(session_id=session_id, role="publisher")
    )
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return str(raw)


async def _create_session_async(vng: Vonage) -> str:
    loop = asyncio.get_running_loop()
    session_id = await loop.run_in_executor(
        None, lambda: vng.video.create_session().session_id
    )
    logger.info(f"Created Vonage session: {session_id}")
    return session_id


_active_connectors: dict[str, AudioConnectorData] = {}


def _get_video_client() -> Vonage:
    application_id = _require_env("VONAGE_APPLICATION_ID")
    private_key_raw = _require_env("VONAGE_PRIVATE_KEY")
    private_key = _read_private_key(private_key_raw)
    return _create_vonage_client(application_id, private_key)


async def _stop_audio_connector_async(session_id: str) -> None:
    vng = _get_video_client()
    connector = _active_connectors.pop(session_id, None)
    if connector is None:
        logger.info(f"No active connector found for session {session_id}")
        return
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: vng._http_client.delete(
                vng._http_client.video_host,
                f"/v2/project/{vng._http_client.auth.application_id}/connect?sessionId={session_id}",
            ),
        )
        logger.info(f"Stopped Audio Connector for session {session_id}")
    except Exception as e:
        logger.warning(f"Failed to stop Audio Connector for session {session_id}: {e}")


async def _connect_audio_connector_async(
    vng: Vonage, session_id: str, ws_uri: str, audio_rate: int
) -> None:
    # Stop ALL previous connectors (they leak if only the new session_id is used)
    for old_sid in list(_active_connectors.keys()):
        await _stop_audio_connector_async(old_sid)

    logger.info(
        f"Connecting Vonage Audio Connector: session={session_id}, ws={ws_uri}, rate={audio_rate}"
    )
    token = _generate_client_token(vng, session_id)
    audio_opts = AudioConnectorOptions(
        session_id=session_id,
        token=token,
        websocket={
            "uri": ws_uri,
            "audioRate": audio_rate,
            "bidirectional": True,
        },
    )

    loop = asyncio.get_running_loop()
    connector = await loop.run_in_executor(
        None, lambda: vng.video.start_audio_connector(audio_opts)
    )
    _active_connectors[session_id] = connector
    logger.info(f"Audio Connector started successfully: id={connector.id}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from bot import preload_models
    
    logger.info("Server starting up...")
    await preload_models()
    logger.info("Server ready to accept calls")
    yield


app = FastAPI(lifespan=lifespan)

@app.get("/voice/webhook")
async def voice_webhook(request: Request) -> JSONResponse:
    """
    Handles inbound Vonage Voice API calls.
    Returns an NCCO to connect the call to the WebSocket endpoint.
    Vonage sends a GET request with call parameters as query strings.
    """
    # Log incoming call information from query parameters
    query_params = dict(request.query_params)
    logger.info(f"Received Voice Webhook (GET). Call info: {query_params}")
    
    # Determine the WebSocket URI for the bot
    # We use the host from the request to construct the correct absolute WebSocket URI
    host = request.headers.get("host", "localhost:8005")
    scheme = "wss" if not host.startswith("localhost") else "ws"
    ws_uri = f"{scheme}://{host}/ws"
    
    logger.info(f"Connecting call to bot at: {ws_uri}")

    # Construct NCCO to connect the call to the WebSocket
    # Explicitly specify content-type for reliable bidirectional audio
    ncco = [
        {
            "action": "connect",
            "endpoint": [
                {
                    "type": "websocket",
                    "uri": ws_uri,
                    "content-type": "audio/l16;rate=16000"
                }
            ]
        }
    ]

    return JSONResponse(content=ncco)


@app.post("/voice/webhook")
async def voice_webhook_post(request: Request) -> JSONResponse:
    """
    Alternative endpoint for POST requests (if needed).
    """
    return await voice_webhook(request)


app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/connect")
async def connect() -> JSONResponse:
    application_id = _require_env("VONAGE_APPLICATION_ID")
    private_key_raw = _require_env("VONAGE_PRIVATE_KEY")
    private_key = _read_private_key(private_key_raw)
    ws_uri = _require_env("WS_URI")
    audio_rate = int(os.getenv("VONAGE_AUDIO_RATE", "16000"))

    vng = _create_vonage_client(application_id, private_key)
    session_id = await _create_session_async(vng)

    try:
        await _connect_audio_connector_async(vng, session_id, ws_uri, audio_rate)
    except Exception as e:
        logger.warning(f"Audio Connector start failed for session {session_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to connect Audio Connector: {e}"
        )

    return JSONResponse(
        {
            "status": "connect_triggered",
            "session_id": session_id,
            "ws_uri": ws_uri,
            "audio_rate": audio_rate,
        }
    )


@app.post("/demo/connect")
async def demo_connect(request: Request) -> JSONResponse:
    application_id = _require_env("VONAGE_APPLICATION_ID")
    private_key_raw = _require_env("VONAGE_PRIVATE_KEY")
    private_key = _read_private_key(private_key_raw)
    audio_rate = int(os.getenv("VONAGE_AUDIO_RATE", "16000"))

    ws_uri = os.getenv("WS_URI")
    if not ws_uri:
        host = request.headers.get("host", "localhost:8005")
        scheme = "ws" if host.startswith("localhost") else "wss"
        ws_uri = f"{scheme}://{host}/ws"

    vng = _create_vonage_client(application_id, private_key)
    session_id = await _create_session_async(vng)

    try:
        await _connect_audio_connector_async(vng, session_id, ws_uri, audio_rate)
    except Exception as e:
        logger.warning(f"Audio Connector start failed for session {session_id}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to connect Audio Connector: {e}"
        )

    token = _generate_client_token(vng, session_id)

    return JSONResponse(
        {
            "session_id": session_id,
            "token": token,
            "application_id": application_id,
        }
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Client connected to /ws")

    # 1. 接続ごとに「新しいトランスポート」を必ず作成する
    # これにより、以前の接続の残骸（古いバッファや状態）の影響を防ぐ
    sample_rate = int(os.getenv("VONAGE_AUDIO_RATE", "16000"))
    serializer = VonageFrameSerializer(
        VonageFrameSerializer.InputParams(
            vonage_sample_rate=sample_rate,
        )
    )

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_out_10ms_chunks=2,
            serializer=serializer,
        ),
    )

    async def keepalive():
        while True:
            try:
                await websocket.send_text('{"event":"keepalive"}')
                await asyncio.sleep(10)
            except Exception:
                break

    keepalive_task = asyncio.create_task(keepalive())

    try:
        from bot import bot
        from pipecat.runner.types import WebSocketRunnerArguments

        # 2. 新しいトランスポートを渡してボットを起動
        runner_args = WebSocketRunnerArguments(websocket=websocket, body={})
        # bot() 内部で transport を使うように bot.py も調整済み
        await bot(runner_args, transport) 
        
    except Exception as e:
        logger.exception(f"Pipecat bot error: {e}")
    finally:
        # 3. 確実にクリーンアップ
        keepalive_task.cancel()
        await transport.cleanup()
        logger.info("WebSocket endpoint cleaned up")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8005)
