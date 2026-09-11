# 変更履歴

このプロジェクトの全ての重要な変更はこのファイルに記録されます。

## [Unreleased] - 2026-07-04

### 修正
- **Videoクライアントからの音声入力受信問題**: グローバルプリロード済みのSTT/LLM/TTSインスタンスを再利用する方式から、接続ごとに新規作成する方式に戻しました。`_reset_service()` による内部状態のリセットが不完全だったため、音声入力フレームがSTTに届かない問題が発生していました。これにより、旧バージョン同等の音声認識精度と入力受信が復元されました。
- **VADパラメータの最適化**: `VADProcessor` の削除と、`LLMUserAggregatorParams` 内のVAD設定を旧バージョンの値に戻しました: `confidence=0.7`, `start_secs=0.3`, `stop_secs=0.8`, `min_volume=0.4`。これにより、音声検出の精度が向上しました。
- **パイプライン構成の簡素化**: 不要な `VADProcessor` と `AudioFrameLogger` を削除し、パイプラインを `transport.input() → stt → user_aggregator → llm → assistant_aggregator → tts → transport.output()` に戻しました。
- **Smart Turn Analyzerのプリロード削除**: `LocalSmartTurnAnalyzerV3` のプリロードを削除しました。
- **モデルプリロードの削除**: `preload_models()`, `get_llm()`, `get_stt()`, `get_tts()` を削除し、サーバー起動時の待機時間を短縮しました。

### 追加
- **Edge TTS 対応**: Bark TTS を `EdgeTTSService`（`tts_edge.py`）に置き換え、Microsoft Edge TTS（`ja-JP-NanamiNeural`）を使用。PyAV で MP3 をデコードし、24kHz→16kHz にリサンプル、int16 PCM を出力。
- **BufferingTextAggregator**: LLM 応答テキストを全てバッファリングし、`LLMFullResponseEndFrame` 受信時に1回だけ合成するカスタムアグリゲーター。文ごとの切れ目を解消。

### 変更
- **VAD感度調整**: `confidence` を 0.5→0.3、`start_secs` を 0.2s→0.1s に低下。
- **挨拶ディレイ**: 接続時の挨拶を 2秒後→10秒後に変更。
- **Bark TTS 削除**: `tts_bark.py` を削除し、`pyproject.toml` から `"bark[all]"` 依存を除去。

### 修正
- **TTS バッファがフラッシュされない問題**: `LLMAssistantAggregator._handle_llm_end` をモンキーパッチで変更し、`LLMFullResponseEndFrame` を下流の TTS に転送。バッファリングされたテキストが実際に合成されるよう修正。
- **挨拶が合成されない問題**: 挨拶 `TextFrame` の後に `LLMFullResponseEndFrame` をプッシュして TTS フラッシュをトリガー。

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
- **TTSの長文対応 (Chunking)**: `tts_irodori.py` において、長いテキストを句読点で適切に分割（チャンク化）してリクエストを送るように変更しました。これにより、TTSサーバーのタイムアウトや処理制限による音声の欠損を防止します。
- **TTSタイムアウトの最適化**: `httpx` のタイムアウト設定を強化し、接続時および通信時の安定性を向上させました。
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
