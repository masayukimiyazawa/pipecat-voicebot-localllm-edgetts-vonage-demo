# Pipecat Voice Bot — LM Studio + pyopenjtalk + Vonage

LM Studio（ローカル LLM/STT）と pyopenjtalk（ローカル日本語 TTS）を利用した音声対話ボットです。**ビデオセッション（ブラウザ SDK）** と **外線電話（PSTN/Vonage Voice API）** の両方に対応します。

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
                    │  │  pyopenjtalk (TTS)             │  │
                    │  └────────────────────────────────┘  │
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

### 音声モード（電話 → Voice API → Webhook/NCCO）

```
1. 着信              2. GET /voice/webhook        3. NCCO を返却
   ┌──────┐   ──────►   ┌──────────┐   ──────►   ┌──────────────┐
   │Phone  │               │FastAPI   │               │Vonage Voice  │
   └──────┘               └──────────┘               │Platform      │
       ▲                                              └──────┬───────┘
       │                                                     │
       │  5. 通話が WebSocket に接続                           │ 4. WebSocket
       └─────────────────────────────────────────────────────┘    接続
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

1. ユーザーが Vonage に登録された電話番号に発信します。
2. Vonage が設定された Answer URL（https://<tunnel-url>/voice/webhook）
   に GET リクエストを送信します（クエリパラメータに to, from,
   conversation_uuid などの発信者情報が含まれます）。
3. サーバーが NCCO（Nexmo Call Control Object）を返却し、Vonage に対して
   WebSocket 経由でボットに接続するよう指示します:
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
4. Vonage が指定された URI に WebSocket 接続を確立します。
5. 通話が WebSocket にブリッジされ、双方向の音声が電話 ↔ ボット間で
   流れるようになります。
6. 接続確立後、ボットが TTS 経由で挨拶メッセージ
   （"こんにちは。音声アシスタントです。何かお手伝いできますか？"）を送信します。
7. 以降のユーザーの発話は STT → LLM → TTS のパイプラインで処理され、
   応答が電話に再生されます。
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
| `STT_LANGUAGE` | `ja` | Whisper の言語コード |
| `VONAGE_APPLICATION_ID` | `abcd1234-...` | Vonage Application ID（必須） |
| `VONAGE_PRIVATE_KEY` | `-----BEGIN PRIVATE KEY-----...` | 秘密鍵（PEM 文字列またはファイルパス、必須） |
| `WS_URI` | `wss://xxx.trycloudflare.com/ws` | 公開 WebSocket URL（start.sh で自動設定） |
| `VONAGE_WEBHOOK_URL` | `https://xxx.trycloudflare.com/voice/webhook` | Vonage Voice API Answer URL（start.sh で自動設定） |

### 2. 依存関係インストール

```bash
uv sync
```

## 起動

### 3. LM Studio を起動

LLM モデルと Whisper モデルをロードし、`localhost:1234` で listening 状態にします。

### 4. ワンコマンド起動（推奨）

```bash
bash start.sh
```

以下の処理を自動で行います:

1. Cloudflare Tunnel（`cloudflared`）を起動し、公開 URL を取得
2. `.env` の `WS_URI` と `VONAGE_WEBHOOK_URL` を自動更新
3. Python サーバーを再起動
4. ブラウザ用 URL と Vonage 設定用の Webhook URL を表示

### 5. 停止方法

実行中のコンポーネントを停止するには、以下のコマンドを使用します。

#### Python サーバーの停止
```bash
# PID を特定して終了させる
ps aux | grep -E "python|uvicorn" | grep -v grep | awk '{print $2}' | xargs kill -9
```

#### Cloudflare Tunnel の停止
```bash
# PID を特定して終了させる
ps aux | grep cloudflared | grep -v grep | awk '{print $2}' | xargs kill -9
```

#### すべてのプロセスを停止する (最も早い方法)
```bash
pkill -f server.py && pkill -f cloudflared
```

### 6. 接続方法
...
## API エンドポイント

| エンドポイント | メソッド | 説明 |
|--------------|---------|------|
| `/` | GET | フロントエンド（`static/index.html`） |
| `/health` | GET | ヘルスチェック |
| `/ws` | WebSocket | Pipecat パイプライン（Audio Connector / Voice API から接続） |
| `/connect` | POST | Vonage Audio Connector（従来方式、`WS_URI` 環境変数が必要） |
| `/demo/connect` | POST | ワンクリックデモ: セッション作成 + トークン生成 + Audio Connector 起動（ビデオモード） |
| `/voice/webhook` | GET | Vonage Voice API Answer Webhook: 電話を `/ws` にブリッジする NCCO を返却 |

## ファイル構成

```
├── server.py                 # FastAPI サーバ（HTTP + WebSocket）
├── bot.py                    # Pipecat pipeline 定義
├── lm_studio_stt.py          # LM Studio STT サービス
├── tts_piper_plus.py         # Piper-plus TTS ラッパー（日英対応）
├── pyproject.toml            # 依存関係
├── setup.sh                  # TTS 音声モデルダウンローダー
├── start.sh                  # ワンコマンド起動スクリプト
├── .env                      # 認証情報（git管理外）
├── .env.example              # テンプレート
├── static/
│   └── index.html            # フロントエンド（Vonage Video JS SDK）
└── docs/
    ├── CHANGELOG.md
    ├── PLAN_VoiceAPI_en.md
    └── PLAN_VoiceAPI_jp.md
```

## デモフロー

### 1. ビデオモード（ブラウザ）
1. ユーザーがトンネル URL をブラウザで開く
2. 「接続」をクリック → `POST /demo/connect` が呼ばれる
3. サーバーが Vonage Video セッションを作成、JWT トークンを生成、Audio Connector を起動（`wss://tunnel-url/ws` 宛）
4. フロントエンドが `OT.initSession(applicationId, sessionId)` + `session.connect(token)` でセッションに参加
5. フロントエンドがマイク音声を配信し、ボットの音声ストリームを受信
6. 音声の流れ: ブラウザ → Vonage Cloud → Audio Connector → ボットパイプライン → Audio Connector → ブラウザ

### 2. 音声モード（電話 / PSTN）
1. Vonage ダッシュボードで **Answer URL** に `https://<tunnel-url>/voice/webhook` を設定
2. ユーザーがあなたの Vonage 番号に電話をかける
3. Vonage が `/voice/webhook` に Webhook を送信、サーバーが NCCO を返却
4. 電話が WebSocket（`/ws`）経由でボットにブリッジされる
5. 音声の流れ: 電話 → Vonage Voice プラットフォーム → WebSocket → ボットパイプライン → WebSocket → 電話

## シーケンス

ボットはクライアント接続時に TTS エンジンを介してテキストの挨拶を送信します。ウェイクワードは不要です。

## 注意事項

- Cloudflare Tunnel（`trycloudflare.com`）は稼働保証なしのクイックトンネルです。本番運用時は名前付きトンネル＋独自ドメインを推奨します。
- 電話モードを使用する場合、Vonage ダッシュボードで Answer URL を起動のたびに更新する必要があります（クイックトンネルは再起動ごとに URL が変わります）。
