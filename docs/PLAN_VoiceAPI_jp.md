# プラン: Vonage Voice API (電話) への拡張

## 概要
本プランは、既存の Video API ベースのボットの機能を維持しつつ、Vonage Voice API (電話) をサポートするための技術的な手順をまとめたものです。接続には Cloudflare Tunnel を使用します。

## アーキテクチャ

### 現在 (Video API モード)
`クライアント (ブラウザ/SDK) -> Vonage Video セッション -> Audio Connector -> [WebSocket] -> Pipecat ボット`

### 新規 (Voice API モード)
`電話 -> Vonage Voice プラットフォーム -> [Webhook/NCCO] -> [WebSocket] -> Pipecat ボット`

## 実装ステップ

### 1. サーバー側の拡張 (`server.py`)
- **Webhook エンドポイントの追加**: Vonage からの着信イベントを処理する `POST /voice/webhook` を実装。
- **NCCO の生成**: 電話を既存の `/ws` エンドポイントへ WebSocket 経由で接続するよう指示する NCCO (Nexmo Call Control Object) を生成するロジックを作成。
- **Video ロジックの維持**: `/demo/connect` および `start_audio_connector` が引き続き動作することを確認。

### 2. ボット側の最適化 (`bot.py`)
- **接続の堅牢化**: 接続元が Video か Voice かに関わらず、`on_client_connected` イベントが正しくパイプラインを起動するように調整。
- **サンプルレートの柔軟性**: 8kHz (電話で一般的) と 16kHz (現在の標準) の両方を適切に処理できるように調整。

### 3. 接続設定 (Cloudflare Tunnel)
- **トンネル設定**: `cloudflared` を使用して、ローカルの FastAPI サーバーを公開 URL にマッピング。
- **Vonage 設定**: Vonage ダッシュボードの Voice Webhook URL に Cloudflare Tunnel の URL を設定。

## 検証計画
1. **Video モードテスト**: 現在の Web インターフェースが引き続き動作することを確認。
2. **Voice モードテスト**: 設定した Vonage 番号に電話をかけ、Pipecat ボットが WebSocket 経由で応答することを確認。
