# 変更履歴

このプロジェクトの全ての重要な変更はこのファイルに記録されます。

## [Unreleased] - 2026-07-03

### 追加
- **信頼性の高い STT VAD のための VADProcessor**: `LLMUserAggregator` 内の VAD を、パイプラインの **STT の前に** 配置されたスタンドアロンの `VADProcessor`（`pipecat.processors.audio.vad_processor` より）に置き換えました。これにより `VADUserStartedSpeakingFrame` / `VADUserStoppedSpeakingFrame` が上流ではなく **下流** へ STT にブロードキャストされ、Video クライアントの再接続時に音声入力が受け付けられなくなる問題を修正しました。以前は STT は user_aggregator の VADController からの上流の VAD イベントのみを受信していましたが、2回目の接続で機能しなくなっていました。
- **接続時の自動挨拶**: `bot.py` に即時と3秒後の2つのバックグラウンドタスクを追加し、LLM を介さず TTS から挨拶テキストを発話します。`asyncio.create_task` と `assistant_aggregator.push_frame()` を使用して LLM をバイパスし、直接 TTS へフレームを送信します。

### 変更
- **システムプロンプト更新**: `bot.py` のシステムインストラクションを更新し、アルファベットの読み上げや英会話を禁止。LLM は常に日本語で応答するようになりました。
- **再接続時の LLM 状態リセット**: `bot.py` の `_reset_service()` を拡張し、接続をまたいで LLM サービスに蓄積された状態をクリアします: `_appended_system_instructions`, `_functions`, `_redundant_registration_warned`, `_explicitly_unregistered_function_names` をクリアし、保留中の `_function_call_tasks`, `_sequential_runner_task`, `_summary_task` をキャンセルします。また、各接続開始時に `LLMContext._messages` を明示的にクリアすることで、前回のセッションからの会話履歴が持ち越されないようにします。これにより、再接続時に LLM が以前の会話を記憶しないようになります。
- **包括的なサービス状態リセット**: `bot.py` の `_reset_service()` を拡張し、接続をまたいで残留する全ての STT 内部属性（`_finalize_pending`, `_finalize_requested`, `_last_transcript_time`, `_last_audio_time`, `_can_reconnect`, `_need_reconnect`, `_reconnecting`, `_muted`）をリセットするようにしました。また、前回の接続の VAD 停止サイクルから残った `_ttfb_timeout_task` を明示的にキャンセルします。

### 修正
- **Audio Connector セッション ID 不一致**: `server.py` の `_connect_audio_connector_async()` を修正し、新しいコネクタを作成する前に **全ての** 既存の Audio Connector を停止するようにしました。以前は新しいセッション ID を停止関数に渡していたため、`_active_connectors` 内の古いエントリと一致せず、コネクタがリークして再接続のたびに蓄積されていました。

## [Unreleased] - 2026-07-02

### 追加
- **モデルプリロード機能**: サーバー起動時に LLM/STT/TTS/VAD モデルを事前に読み込む `preload_models()` を実装し、初回接続時の遅延を削減しました。
- **Keepalive ハートビート**: `server.py` に keepalive タスクを追加し、10秒間隔で WebSocket 経由でハートビートを送信して接続維持を安定化しました。

### 変更
- **モデル管理のグローバル化**: LLM/STT/TTS サービスをリクエストごとに生成 → グローバル変数で共有する方式に変更し、メモリ効率と応答速度を改善しました。
- **VAD パラメータ調整**: 音声検出の感度を調整（`confidence: 0.7→0.5`, `start_secs: 0.3→0.2`, `stop_secs: 0.8→0.2`, `min_volume: 0.4→0.0`）。
- **オーディオデバッグログ**: `AudioFrameLogger` プロセッサを追加し、受信オーディオフレームのサイズとサンプルレートをログ出力するようにしました。
- **接続ごとのトランスポート生成**: `FastAPIWebsocketTransport` の生成を `bot.py` から `server.py` に移動し、WebSocket 接続ごとに新しいトランスポートインスタンスが作成されるようにしました。これにより、前回の接続のバッファや状態が持ち越される問題を防止します。

### 修正
- **再接続時の状態リーク**: `bot.py` に `_reset_service()` を追加し、共有サービスインスタンスを使用して新しいパイプラインを開始する前に、Pipecat プロセッサの内部状態（`_cancelling`, `_user_speaking`, `_audio_buffer`, `_content`, `_wave` 等）をクリアするようにしました。
- **切断時のトランスポートクリーンアップ**: `server.py` の `finally` ブロックに `transport.cleanup()` を追加し、各接続終了後に確実にトランスポートリソースが解放されるようにしました。
- **安定性問題**: モデルのプリロードとグローバル共有により、接続時のモデル読み込み遅延によるタイムアウトを防止しました。

## [Unreleased] - 2026-06-30

### 追加
- **Voice API (PSTN) サポート**: 既存の Video API に加え、Vonage Voice API（電話）経由での接続をサポートしました。
- **NCCO Webhook エンドポイント**: `server.py` に `/voice/webhook` を実装し、Vonage Voice の着信を WebSocket 経由でボットにブリッジします。
- **自動環境設定**: `start.sh` を更新し、Cloudflare Tunnel URL を自動検出して `.env` の `WS_URI` と `VONAGE_WEBHOOK_URL` を更新します。
- **挨拶ロジック改善**: `bot.py` を修正し、接続時に `TextFrame` による初期挨拶を送信することで、ユーザー入力がない場合の LLM の "No user query found" エラーを防止します。
- **ドキュメント**: 新しいアーキテクチャ、デモフロー、API エンドポイント情報を `README.md`（英語）と `README-JP.md`（日本語）に更新しました。

### 変更
- **アーキテクチャ**: システムはデュアルモード接続をサポートするようになりました:
  - **Video モード**: クライアント（ブラウザ）→ Video Session → Audio Connector → ボット
  - **Voice モード**: 電話 → Voice API → Webhook/NCCO → ボット
- **デプロイ**: `start.sh` を macOS との互換性と自動 Cloudflare Tunnel 管理のために最適化しました。
- **設定**: `VONAGE_WEBHOOK_URL` を `.env.example` に追加しました。

### 修正
- **Video クライアント再接続時の無音問題**: `/demo/connect` 呼び出し時に旧 Audio Connector を停止してから新規接続するよう `server.py` を修正しました。再接続時に複数の Audio Connector が並行稼働することで発生していた音声ブリッジの競合を解消しました。
