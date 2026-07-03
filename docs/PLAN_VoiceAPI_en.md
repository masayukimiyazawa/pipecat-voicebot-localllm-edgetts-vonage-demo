# Plan: Expanding to Vonage Voice API (Phone Calls)

## Overview
This plan outlines the technical steps to extend the current Video API-based bot to support Vonage Voice API (Phone Calls) while maintaining existing Video functionality. The connection will be facilitated via Cloudflare Tunnel.

## Architecture

### Current (Video API Mode)
`Client (Browser/SDK) -> Vonage Video Session -> Audio Connector -> [WebSocket] -> Pipecat Bot`

### New (Voice API Mode)
`Phone Call -> Vonage Voice Platform -> [Webhook/NCCO] -> [WebSocket] -> Pipecat Bot`

## Implementation Steps

### 1. Server-side Expansion (`server.py`)
- **Add Webhook Endpoint**: Implement `POST /voice/webhook` to handle inbound call events from Vonage.
- **NCCO Generation**: Create a logic to return a Nexmo Call Control Object (NCCO) that instructs Vonage to connect the call to the existing `/ws` endpoint via WebSocket.
- **Maintain Video Logic**: Ensure `/demo/connect` and `start_audio_connector` remain operational.

### 2. Bot-side Optimization (`bot.py`)
- **Connection Robustness**: Ensure the `on_client_connected` event triggers the pipeline correctly regardless of whether the source is Video or Voice.
- **Sample Rate Flexibility**: Ensure the transport handles both 8kHz (common in Voice) and 16kHz (current standard) gracefully.

### 3. Connectivity (Cloudflare Tunnel)
- **Tunnel Setup**: Use `cloudflared` to expose the local FastAPI server to a public URL.
- **Vonage Configuration**: Update Vonage Dashboard with the Cloudflare Tunnel URL for the Voice Webhook.

## Verification Plan
1. **Video Mode Test**: Confirm the current web interface still works.
2. **Voice Mode Test**: Place a call to the configured Vonage number and confirm the Pipecat bot responds via WebSocket.
