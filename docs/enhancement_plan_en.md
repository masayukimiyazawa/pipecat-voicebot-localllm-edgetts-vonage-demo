# Enhancement Plan: Persistent Conversation Context

## Overview
To enable the voicebot to "remember" past interactions, we will implement a mechanism to persist conversation history to a database and reload it into the LLM context during new sessions.

## Phase 1: Database Integration
1. **Database Selection**: Implement **SQLite** for local development due to its zero-configuration and file-based nature, ensuring compatibility with the current local-first architecture.
2. **Schema Design**:
    - `sessions` table: `session_id` (PK), `user_id`, `created_at`.
    - `messages` table: `id` (PK), `session_id` (FK), `role` (user/assistant), `content`, `timestamp`.
3. **Implementation**: Create a `database_manager.py` utility to handle connections and CRUD operations.

## Phase 2: Pipecat Pipeline Extension
1. **Custom Frame Processor**: Develop a `ConversationHistorySaver` class inheriting from `FrameProcessor`.
2. **Intercepting Frames**:
    - Capture `TextFrame` from the `LLMAssistantAggregator` (User speech transcribed).
    - Capture `TextFrame` from the `AssistantAggregator` (LLM response).
3. **Asynchronous Writing**: Ensure database writes are performed in a non-blocking manner using `asyncio.to_thread` or an async database driver (like `aiosqlite`).

## Phase 3: Context Loading (Memory)
1. **Context Retrieval**: Upon session start, query the database for the last `N` messages associated with the user/session.
2. **Context Injection**: Inject retrieved messages into the `LLMContext` object before the pipeline starts, allowing the LLM to "see" the history.

## Verification
1. **Functional Test**: Verify that a conversation is completed, the database is populated, and a new session correctly retrieves the previous context.
2. **Performance Test**: Ensure that database I/O does not introduce latency in the real-time voice pipeline.