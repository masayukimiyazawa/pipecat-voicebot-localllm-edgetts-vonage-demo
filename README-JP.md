# Pipecat Voice Bot — LM Studio + Edge TTS + Vonage

LM Studio（ローカル LLM/STT）と Edge TTS（Microsoft Azure、日本語音声）を利用した音声対話ボットです。**ビデオセッション（ブラウザ SDK + Audio Connector）** に対応します。

## アーキテクチャ

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

### ビデオモード（ブラウザ → Video セッション → Audio Connector）

```
1. ブラウザ          2. POST /demo/connect      3. セッション作成
   ┌──────┐   ──────►   ┌──────────┐   ──────►   ┌──────────────┐
   │Client│               │FastAPI   │               │Vonage Cloud  │
   └──────┘               └──────────┘               │(Video API)   │
       ▲                                              └──────┬───────┘
       │                                                     │
       │  5. セッション参加 (OT.initSession)                   │
       │     + 音声 publish/subscribe                       │ 4. Audio
       └─────────────────────────────────────────────────────┘    Connector
                                                                    │
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

1. ユーザーがトンネルURLをブラウザで開き、Webページ（static/index.html）を表示します。
2. "接続"ボタンクリックで POST /demo/connect がサーバーに送信されます。
3. サーバーが Vonage Video セッションを vng.video.create_session() で作成します。
4. サーバーが Audio Connector を vng.video.start_audio_connector() で起動し、
   接続先を Bot の WebSocket（wss://<tunnel-url>/ws）に指定します。
5. ブラウザが OT.initSession(applicationId, sessionId), session.connect(token)
   でセッションに参加し、マイク音声を publish、ボットの音声を subscribe します。
6. 音声が流れる経路: ブラウザ ↔ Vonage Cloud ↔ Audio Connector ↔ ボット
```

## 前提条件

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- [LM Studio](https://lmstudio.ai/)（LLM + Whisper モデルをロードし、`localhost:1234` で待受）
- [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)（Homebrew: `brew install cloudflared`）
- Vonage アカウント（Application ID + Private Key）

## セットアップ

### 1. 環境変数

```bash
cp .env.example .env
```

`.env` を編集:

| 変数 | 設定例 | 説明 |
|------|--------|------|
| `LM_STUDIO_BASE_URL` | `http://localhost:1234/v1` | LM Studio API エンドポイント |
| `LM_MODEL` | `gemma-4-26B-A4B-it-MLX-8bit` | LLM モデル名 |
| `STT_LANGUAGE` | `ja` | Whisper の言語コード |
| `VONAGE_APPLICATION_ID` | `abcd1234-...` | Vonage Application ID（必須） |
| `VONAGE_PRIVATE_KEY` | `./private.key` | 秘密鍵のパス（必須） |
| `VONAGE_AUDIO_RATE` | `16000` | 音声サンプルレート |

### 2. 依存関係インストール

```bash
uv sync
```

## 起動

### 3. LM Studio を起動

LLM モデルと Whisper モデルをロードし、`localhost:1234` で listening 状態にします。

### 4. サーバーとトンネルを起動

```bash
# アプリケーションを起動
bash start.sh
```

スクリプトがサーバーと Cloudflare トンネルの起動を処理します。出力されるトンネル URL を確認してください。

サーバーは起動時に全モデルをプリロードします（約60秒かかることがあります）。

### 5. 接続

ブラウザでトンネルURLを開き、「接続」をクリックしてください。10秒後にボットが挨拶します。

### 停止

```bash
pkill -f server.py && pkill -f cloudflared
```

## API エンドポイント

| エンドポイント | メソッド | 説明 |
|--------------|---------|------|
| `/` | GET | フロントエンド（`static/index.html`） |
| `/health` | GET | ヘルスチェック |
| `/ws` | WebSocket | Pipecat パイプライン（Audio Connector / Voice API から接続） |
| `/connect` | POST | Vonage Audio Connector（従来方式、`WS_URI` 環境変数が必要） |
| `/demo/connect` | POST | ワンクリックデモ: セッション作成 + トークン生成 + Audio Connector 起動 |
| `/voice/webhook` | GET | Vonage Voice API Answer Webhook: 電話を `/ws` にブリッジする NCCO を返却 |

## ファイル構成

```
├── server.py                 # FastAPI サーバ（HTTP + WebSocket）
├── bot.py                    # Pipecat pipeline 定義
├── tts_edge.py               # Edge TTS サービス（Microsoft Azure）
├── pyproject.toml            # 依存関係
├── .env                      # 認証情報（git管理外）
├── static/
│   └── index.html            # フロントエンド（Vonage Video JS SDK）
└── docs/
    └── CHANGELOG.md
```

## デモフロー

1. ユーザーがトンネル URL をブラウザで開く
2. 「接続」をクリック → `POST /demo/connect` が呼ばれる
3. サーバーが Vonage Video セッションを作成、JWT トークンを生成、Audio Connector を起動（`wss://tunnel-url/ws` 宛）
4. フロントエンドが `OT.initSession(applicationId, sessionId)` + `session.connect(token)` でセッションに参加
5. フロントエンドがマイク音声を配信し、ボットの音声ストリームを受信
6. 音声の流れ: ブラウザ → Vonage Cloud → Audio Connector → ボットパイプライン → Audio Connector → ブラウザ

ボットは接続10秒後に TTS で挨拶します。以降のユーザー発話は STT → LLM → TTS で処理されます。

### 音声モード（電話 → Voice API → Webhook）

1. Vonage ダッシュボードで Answer URL に `https://<tunnel-url>/voice/webhook` を設定
2. Vonage 番号に電話をかける
3. 音声が WebSocket 経由でボットにブリッジされる

