# Architecture as implemented

The current release is a small, single-node MVP. The HTTP application is a FastAPI modular monolith with a React single-page frontend. There is no separate media worker, Celery queue, FFmpeg pipeline or background transcoding in the current scope.

## Components

- **React 18 + TypeScript + Vite** — browser application, including upload progress and client-side session refresh coordination.
- **Nginx** — serves the frontend build and reverse-proxies `/api/` to FastAPI.
- **FastAPI** — versioned HTTP API under `/api/v1`, authentication, authorization and application use cases.
- **PostgreSQL 17** — users, roles, refresh sessions, channels, videos, grants, comments, reactions, playlists, subscriptions, notifications and moderation records.
- **Alembic** — schema migrations. Compose runs a one-shot `migrate` service after PostgreSQL is healthy and before starting the backend.
- **S3-compatible MinIO service** — original video and thumbnail objects. Production keeps the object-storage service on the private Docker network.
- **Redis 7** — temporary view-count deduplication keys only. Redis is not a queue or durable database.
- **Caddy** — production HTTPS entry point; it proxies to the frontend container.

## Video upload and playback

1. The frontend sends `POST /api/v1/videos/upload` as multipart form data and reports upload progress.
2. The API requires authentication and validates the file size, declared MIME type and basic file signature. Accepted video types are MP4, WebM and MOV; an optional JPEG, PNG or WebP thumbnail is supported.
3. The API generates storage object keys, uploads the original files to the S3-compatible store synchronously, and writes video metadata to PostgreSQL.
4. Playback and thumbnail endpoints first apply server-side visibility/access checks. The backend then reads the object from storage and streams it to the client. Video playback supports a single HTTP byte range for seeking.
5. The application does not transcode, probe media with FFmpeg, generate thumbnails automatically, or run background processing. The uploaded original is the served file.

Private videos are available to their owner and explicitly granted registered users. Public videos appear in public feeds and channels. Unlisted videos are not included in public lists but can be opened by a direct video link. Object-storage access is not exposed as a public URL by the production Compose topology.

## View-count deduplication

- For authenticated viewers, the identity is based on the user ID. For anonymous viewers, it uses the client IP and User-Agent when a client IP is available.
- Redis stores a SHA-256 digest of the identity in a key scoped to the video.
- `SET NX EX` makes the claim atomic across backend processes. The default TTL is 1,800 seconds (30 minutes), configurable with `VIEW_DEDUP_TTL_SECONDS`.
- If Redis is unavailable or full, the API deliberately fails open: the view is counted without deduplication. Redis is therefore excluded from the `/ready` probe.
- Redis has no persistence volume; its keys are temporary and disappear on restart.

## Health probes

- `GET /health` is a liveness check for the API process.
- `GET /ready` executes `SELECT 1` against PostgreSQL. It returns HTTP 200 when the database is reachable and HTTP 503 otherwise.
- Both development and production Compose use `/ready` for the backend healthcheck.

## Production topology and resource profile

Production Compose uses an edge network for Caddy and the frontend and a private internal network for the backend, PostgreSQL, Redis and object storage. Only Caddy publishes public ports (80/443).

Current Compose memory limits for continuously running services total **464 MiB**: PostgreSQL 160 MiB, object storage 96 MiB, Redis 24 MiB, backend 128 MiB, frontend 24 MiB and Caddy 32 MiB. The one-shot migration container has an additional 48 MiB limit while it runs. CPU limits for the continuously running services total approximately 0.22 CPU. These are container limits, not a statement of the VPS's physical capacity; the host OS, Docker and other processes need additional headroom.

This profile is intentionally small and is suitable only for a low-traffic MVP. Keep the initial media catalog small and avoid 4K files. The object-storage volume is not size-capped by these Compose memory limits, so monitor disk usage separately.

## Code organization

- `app/api/routes` contains the HTTP route modules.
- `app/services` contains shared authentication, storage, video-access, serialization and ephemeral-store logic.
- `app/models`, `app/schemas` and `app/db` contain persistence models, API schemas and database setup.
- `backend/tests` covers API behavior, authorization boundaries, database models and Redis deduplication.

Some use-case logic currently remains in route modules; when extending the application, avoid duplicating shared rules and move reusable domain behavior into services.
