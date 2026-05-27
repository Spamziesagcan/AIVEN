# AIVEN

Aiven is a lightweight LLM chatbot with inference logging, near-real-time ingestion, and dashboard-style observability.

## What It Does

- Multi-turn chat with short context retention
- Lightweight logging around inference calls
- Ingestion endpoint that validates and stores metadata
- SQLite persistence for conversations and inference logs
- Streaming responses for supported providers
- Conversation actions: create, list, resume, and delete

## Architecture

The current deployment is intentionally simple:

- `frontend` provides the UI
- `backend` serves the API, chat endpoints, and storage layer
- SQLite stores conversations and inference logs
- Ingestion is handled inline when Redis is not used

The backend supports multiple providers through environment configuration. The active provider is selected with `LLM_PROVIDER`, and the provider-specific API keys are read from the environment.

## Data Model

The database stores two primary entities:

- `conversations`: conversation id, title, created timestamp, updated timestamp
- `messages`: message id, conversation id, role, content, timestamp
- `inference_logs`: request metadata, provider, model, timing, status, previews, raw payload, and received time

### Schema Decisions

- Conversations and messages are normalized so a conversation can be deleted cleanly.
- Inference logs are stored separately so they can be queried independently from chat history.
- Raw payloads are preserved alongside extracted fields to make debugging and reprocessing easier.
- SQLite was chosen for the current setup because it keeps local development and demos simple.

## Logging and Ingestion Flow

1. The UI sends a chat request to the backend.
2. The backend wrapper records provider, model, latency, request status, and previews.
3. The ingestion payload is validated.
4. The processed event is written to the database.

If Redis is not configured, the app still works because ingestion can run inline.

## Setup

### 1. Configure environment

Copy the example file and fill in the provider key you want to use:

```bash
copy .env.example .env
```

### 2. Start the app

```bash
docker compose up --build
```

### 3. Open the app

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- Health check: `http://localhost:8000/api/health`

## Environment Variables

Important variables:

- `LLM_PROVIDER` chooses the provider: `gemini`, `openai`, or `claude`
- `GEMINI_API_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY` provide credentials
- `DATABASE_URL` enables Postgres instead of SQLite
- `OLLIVE_DB_PATH` controls the SQLite file location
- `NEXT_PUBLIC_API_BASE` points the frontend to the backend API

## Tradeoffs

- SQLite keeps the project easy to run locally, but Postgres is better for multi-instance production use.
- Inline ingestion reduces moving parts, but a queue-based pipeline scales better.
- The UI is compact and functional rather than feature-heavy.
- Deleting a conversation is a hard delete for simplicity.

## What I Would Improve Next

- Add PII redaction before logs are stored
- Reintroduce a queue-backed ingestion worker for scale
- Add auth and per-user conversation isolation
- Move the deployment to Kubernetes with separate services
- Add richer dashboards and filtering for logs

## Demo

Demo link: not provided.

## Repository Structure

- `backend/` FastAPI app, ingestion logic, SDK wrapper, and storage code
- `frontend-next/` chat UI and dashboard UI
- `frontend/` static frontend assets used by the backend shell
- `docker-compose.yml` local one-command setup

## Notes

- The project name is `Aiven`.
- The repo is set up for local Docker Compose development and can be adapted for self-hosted Kubernetes later.
