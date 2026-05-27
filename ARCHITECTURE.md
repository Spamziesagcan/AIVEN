# Architecture Overview

## Purpose

Lightweight inference logging and ingestion pipeline for the LLM chatbot project. Captures inference metadata in near real-time, validates and enriches logs, stores chat and telemetry data, and exposes observability surfaces for metrics and debugging.

## Repo mapping

- Frontend: [frontend/](frontend/)
- Backend: [backend/](backend/)
- Local DB (demo): [data/ollive.sqlite3](data/ollive.sqlite3)
- Orchestration: [docker-compose.yml](docker-compose.yml)

Key backend files:
- [backend/app/sdk.py](backend/app/sdk.py) — SDK / wrapper for LLM calls and telemetry emission
- [backend/app/ingestion.py](backend/app/ingestion.py) — ingestion API and validation
- [backend/app/llm.py](backend/app/llm.py) — provider adapters and LLM call abstraction
- [backend/app/store.py](backend/app/store.py) — DB write helpers and persistence
- [backend/app/db.py](backend/app/db.py) — DB connection and schema helpers
- [backend/app/request_logger.py](backend/app/request_logger.py) — request-level logging and traces
- [backend/app/worker.py](backend/app/worker.py) — background tasks (retries, batching)

## High-level components

- Frontend UI: multi-turn chat, conversation list/resume, cancel actions; calls backend chat endpoints.
- Lightweight SDK: wraps provider calls, captures inference metadata, emits non-blocking ingestion events.
- LLM adapter: normalizes calls across providers and returns structured provider metrics.
- Ingestion service: receives SDK events, validates/normalizes them, enriches, and persists.
- Persistence: stores conversations, messages, inference events and aggregates.
- Worker: handles retries, batching, enrichment and aggregate calculations.

## Ingestion flow

1. Frontend sends user message to chat endpoint (backend creates conversation_id if absent).
2. Chat handler calls the SDK to perform an LLM request.
3. SDK emits an `inference.request.start` event (minimal preview, `request_id`, `conversation_id`).
4. LLM adapter performs the provider call and returns response + provider metrics.
5. SDK emits an `inference.request.end` event with latency, tokens, status, and truncated previews.
6. Ingestion service validates and normalizes received events, extracts derived metrics, and persists via `store.py`.
7. Background workers compute aggregates and push metrics to observability endpoints or tables.

## SDK logging strategy

- Event types: `inference.request.start`, `inference.request.end`, `inference.request.error`, `conversation.message`.
- Minimum fields captured: `request_id`, `conversation_id`, `timestamp`, `stage`, `model`, `provider`, `latency_ms`, `tokens_prompt`, `tokens_completion`, `status`, `error` (nullable), `input_preview`, `output_preview`, `raw_provider_meta`.
- Delivery: non-blocking HTTP POST to ingestion endpoint; local buffering + exponential backoff on failures; optional batching for throughput.
- Privacy: truncate or redact previews by default (configurable). Provide per-request opt-out for telemetry.

## Payload validation & parsing

- Use a lightweight schema validator (pydantic/marshmallow) in ingestion to strictly validate incoming events.
- Normalize provider-specific fields into canonical fields (`tokens_prompt`, `tokens_completion`, `latency_ms`).
- Return `4xx` for malformed events; accept, enrich and store valid events.

## Schema design

Recommended tables (prototype uses SQLite; production should use Postgres/JSONB or time-series store):

- `conversations`
  - `id`, `user_id` (nullable), `created_at`, `updated_at`, `last_message_preview`
- `messages`
  - `id`, `conversation_id`, `role`, `text`, `created_at`, `message_index`
- `inference_events`
  - `id`, `request_id`, `conversation_id`, `message_id` (nullable), `stage`, `model`, `provider`, `status`, `latency_ms`, `tokens_prompt`, `tokens_completion`, `cost_estimate`, `timestamp`, `input_preview`, `output_preview`, `raw_meta` (JSON)
- `aggregates`
  - `time_bucket`, `provider`, `model`, `requests`, `avg_latency`, `p95_latency`, `errors`

Tradeoffs:

- SQLite: zero-config and portable for demos, but limited concurrency — migrate to Postgres for production.
- Normalize messages and inference events to enable replay and analytics, at cost of additional writes.

## Storage & indexing recommendations

- Use Postgres in production with `JSONB` for `raw_meta` and indices on `conversation_id`, `request_id`, `timestamp`, and `model`.
- For high-volume telemetry, use a time-series store (ClickHouse / InfluxDB) for aggregates and Prometheus for metrics.
- Index suggestions: `conversation_id`, `timestamp`, `provider`, partial index for `status='error'`.

## Observability & dashboards

- Key metrics: request rate (RPS), average/p95 latency, error rate, tokens per request, cost estimates per model/provider.
- Emit metrics from ingestion to a Prometheus-compatible endpoint or compute aggregates into `aggregates` table for UI dashboards.
- Use the frontend `ObservabilityDashboard` component to query aggregated endpoints for latency/throughput/error charts.
- Persist structured JSON logs in `logs/llm_requests.jsonl` for audit and replay.

## Scaling considerations

- Make ingestion stateless and scale horizontally behind a load balancer.
- Introduce a durable message queue (Kafka/RabbitMQ) between ingestion and workers to decouple spikes.
- Use worker pools and bulk inserts for DB writes; time-based partitioning for telemetry tables.
- SDK: implement batching and backpressure handling (HTTP 429 -> backoff + local buffering).

## Failure handling & retries

- SDK: best-effort delivery with bounded local buffering; retries with exponential backoff; fallback to durable local queue.
- Ingestion: dedupe by `request_id`, acknowledge events after validation/enqueue; move failed writes to dead-letter queue.
- Alerts for backlog, elevated error rates, and worker failures.

## Security & privacy

- PII minimization: truncate/redact previews; configurable redaction hooks (regex or ML); per-request opt-out.
- TLS for all SDK->ingestion traffic; DB encryption at rest in production.
- Do not log provider API keys or secrets; ensure `raw_meta` is scrubbed for sensitive fields.

## Tradeoffs & rationale

- Prioritize user experience: non-blocking SDK delivery avoids adding latency to the chat experience at the cost of possible telemetry loss (mitigated by local durable queues).
- Keep the demo simple and reproducible with SQLite and `docker-compose` while documenting migration paths to production-grade components.

## Deployment notes

- Local/demo: run `docker-compose.yml` to start frontend and backend; SQLite is mounted under `data/` for persistence.
- Production: containerize services, run on Kubernetes, use managed Postgres and a message broker, add autoscaling for ingestion.

## Improvements given more time

- Replace SQLite with Postgres + Timescale/ClickHouse for telemetry.
- Add a durable broker (Kafka/RabbitMQ) and robust backpressure handling.
- Implement streaming responses end-to-end and chunk-level telemetry with sequence IDs.
- Add pluggable PII redaction and retention policies.
- Build Prometheus + Grafana dashboards and automated alerts.

## How bonus features integrate

- Multi-provider: `llm.py` implements provider adapters; `sdk` selects adapter per request.
- Streaming: SDK emits chunk-level events with sequence numbers; ingestion supports reassembly.
- Event-based: ingestion publishes validated events to topics for billing, analytics and replay consumers.
- Docker Compose: extend `docker-compose.yml` to include Postgres/Redis for prod-like testing.
- PII redaction: SDK pre-send hooks for scrubbing.

---

If you want, I can also add this content to the repository `README.md` or open a PR updating docs.
