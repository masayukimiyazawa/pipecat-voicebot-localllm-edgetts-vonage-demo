# Pipecat Voice Bot — 設計書

## 概要

**Vonage Unified Video API** を利用した音声会話ボット。ブラウザは Vonage Video JS SDK でセッションに参加し、Audio Connector が音声をサーバーの Pipecat パイプラインに中継します。

```
ブラウザ (Vonage Video JS SDK)
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
クライアントが応答を受信
```

## アーキテクチャ

| レイヤ | 技術 |
|--------|------|
| フロントエンド | Vonage Video JS SDK (`OT`) via CDN |
| サーバー | FastAPI + uvicorn (ポート 8005) |
| パイプライン | Pipecat (`FastAPIWebsocketTransport`) |
| STT | LM Studio Whisper (`LMStudioSTTService`, JSON/base64 POST) |
| LLM | LM Studio (`OpenAILLMService`, chat completions) |
| TTS | Piper-plus (`PiperPlusTTSService`, ローカル ONNX) |
| セッション中継 | Vonage Audio Connector (raw PCM16, 16kHz, mono) |

## 音声の流れ

| 向き | 変換元 → 変換先 | フォーマット | 媒体 |
|------|----------------|-------------|------|
| ユーザー→Bot | ブラウザマイク → Vonage Cloud | Opus/WebRTC | Vonage Video SDK |
| Bot←Vonage | Audio Connector → サーバー `/ws` | PCM16 16kHz mono | WebSocket (raw binary) |
| Bot→Vonage | サーバー `/ws` → Audio Connector | PCM16 16kHz mono | WebSocket (raw binary) |
| Bot→ユーザー | Vonage Cloud → ブラウザ | Opus/WebRTC | Vonage Video SDK |

## 割り込み

`VonageFrameSerializer` が `InterruptionFrame` を検出すると、Audio Connector に `{"action": "clear"}` JSON を送信して再生バッファをクリアします。

## エンドポイント

| Method | Path | 用途 |
|--------|------|------|
| GET | `/` | `static/index.html` を返す |
| GET | `/health` | ヘルスチェック |
| POST | `/demo/connect` | セッション作成 + トークン生成 + Audio Connector 起動 |
| POST | `/connect` | 従来の Audio Connector (`WS_URI` env 必須) |
| WebSocket | `/ws` | Pipecat パイプライン（Audio Connector が接続） |

## 主要ファイル

```
├── server.py                   # FastAPI: 静的ファイル + REST + WebSocket
├── bot.py                      # Pipecat パイプライン
│   ├── LMStudioSTTService      # STT (LM Studio, JSON body)
│   ├── OpenAILLMService        # LLM (LM Studio, chat completions)
│   ├── PiperPlusTTSService     # TTS (Piper-plus, ローカル ONNX)
│   └── VonageFrameSerializer   # Audio Connector 用シリアライザ
├── lm_studio_stt.py            # LM Studio STT 実装
├── tts_piper_plus.py           # Piper-plus TTS ラッパー (日英バイリンガル)
├── static/index.html           # Vonage Video JS SDK フロントエンド
├── docs/PLAN.md                # 英語版設計書
└── docs/PLAN.ja.md             # 日本語版設計書 (本ファイル)
```

## 依存関係

| パッケージ | 用途 |
|-----------|------|
| `pipecat-ai[openai,websocket,silero,piper,runner]` | パイプライン、トランスポート、VAD、TTS |
| `vonage>=3.3.1` | Vonage REST API (認証、セッション) |
| `vonage-video` | Audio Connector API |
| `fastapi`, `uvicorn` | Web サーバー |
| `python-dotenv` | 環境変数 |
| `pyopenjtalk-plus` | 日本語 TTS サポート |

## 環境変数

| 変数 | 必須 | 説明 |
|------|------|------|
| `LM_STUDIO_BASE_URL` | Yes | LM Studio API エンドポイント |
| `LM_MODEL` | No | LLM モデル名 (空＝デフォルト) |
| `STT_MODEL` | No | Whisper モデル名 |
| `STT_LANGUAGE` | No | STT 言語コード |
| `PIPER_PLUS_VOICE_ID` | No | TTS 音声モデル |
| `VONAGE_APPLICATION_ID` | Yes | Vonage アプリケーション UUID |
| `VONAGE_PRIVATE_KEY` | Yes | 秘密鍵 (パス or インライン) |
| `VONAGE_AUDIO_RATE` | No | 音声サンプルレート (デフォルト 16000) |
| `WS_URI` | `/connect` 用 | wss://ngrok-url/ws |

## デモの流れ

1. `ngrok http 8005` → `https://abc123.ngrok.dev`
2. ブラウザで ngrok URL を開く
3. **接続** をクリック → `POST /demo/connect`:
   - サーバーが Vonage セッションを作成 (REST API)
   - JWT クライアントトークンを生成
   - Audio Connector 起動 → `wss://ngrok-url/ws`
   - `{ session_id, token, application_id }` を返却
4. フロントエンド: `OT.initSession(applicationId, sessionId)`, `session.connect(token)`
5. マイク配信 + ボットの音声を購読
6. Bot が音声を処理: STT → LLM → TTS → ユーザーに応答
