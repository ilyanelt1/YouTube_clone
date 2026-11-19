# AI Agent Instructions

Build and maintain the YouTube-like video hosting MVP using FastAPI, PostgreSQL and React.

## Current architecture
- The HTTP application is a FastAPI modular monolith. There is no separate media worker, Celery queue or FFmpeg processing pipeline in the current MVP.
- Video uploads are validated and stored synchronously by the API in the S3-compatible object store. Do not add background media processing unless the product scope is explicitly changed.
- PostgreSQL stores relational metadata and authorization state. Alembic owns every schema change.
- MinIO-compatible object storage stores original video and thumbnail files. Playback is authorized by the API and streamed through the backend; the application does not issue presigned URLs.
- Redis is an ephemeral store for view-count deduplication only. Keys expire after the configured TTL (default 30 minutes). Redis failure is intentionally fail-open and must not make the API unavailable or unready.

## Security
- Never commit secrets. Hash passwords with Argon2id.
- Enforce authorization server-side for every protected operation, including private video metadata, playback and thumbnails.
- Keep the object-storage service off the public production network. Generate storage keys server-side and validate upload size, MIME type and file signatures.
- Never log passwords, access tokens, refresh tokens or storage credentials.
- Do not assume rate limiting or CSRF/origin protections are implemented; treat them as outstanding hardening work before broad public registration.

## Health and operations
- `GET /health` is the liveness endpoint.
- `GET /ready` checks PostgreSQL with `SELECT 1`; it returns HTTP 503 when PostgreSQL is unavailable.
- Redis is deliberately excluded from readiness because view counting has a fail-open fallback.
- Production Compose runs the one-shot `migrate` service before starting the backend.

## Quality and Git
- Add tests for critical behavior and security boundaries, including negative authorization cases.
- Run tests and linters; never claim a command passed unless it was executed.
- Use small purposeful conventional commits. Do not rewrite history or modify unrelated files.

## AI workflow
Inspect relevant code/tests before editing. Report changed files, decisions, commands, test results and limitations. Preserve original AI conversation exports in native formats; never fabricate them.
