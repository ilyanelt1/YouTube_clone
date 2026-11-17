# YouTube Clone

A YouTube-inspired video hosting MVP built with FastAPI, PostgreSQL, S3-compatible storage and React.

## Implemented

- Email/username registration and login.
- Argon2id password hashing, short-lived JWT access tokens and rotating HttpOnly refresh sessions.
- PostgreSQL schema managed by Alembic.
- Video upload (MP4, WebM, MOV; up to 500 MB) to S3-compatible object storage.
- Public video feed, title search and browser playback with HTTP byte-range streaming.
- Responsive React interface for authentication, upload, search and playback.
- Docker Compose services for PostgreSQL, Redis, S3-compatible storage, backend and frontend.

## Stack

Python 3.14, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 17, boto3, S3-compatible storage, Redis, React 18, TypeScript, Vite, Nginx and Docker Compose.

## Run locally

1. Install Docker Engine and the Docker Compose plugin.
2. Copy the environment template:
   ```bash
   cp .env.example .env
   ```
3. Change the passwords in `.env`. Generate a secret with:
   ```bash
   openssl rand -hex 32
   ```
   Put the generated value in `SECRET_KEY`. Keep the PostgreSQL password identical in `POSTGRES_PASSWORD` and `DATABASE_URL`; keep the MinIO password identical in `MINIO_ROOT_PASSWORD` and `S3_SECRET_KEY`.
4. Build and start the stack:
   ```bash
   docker compose up --build -d
   ```
5. Open:
   - Frontend: http://localhost:8083
   - API documentation: http://localhost:8003/docs
   - MinIO console (local machine only): http://localhost:9003

## Main API

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `GET /api/v1/videos` — public feed; optional `q`, `limit`, `offset`.
- `POST /api/v1/videos/upload` — authenticated multipart upload with `title`, optional `description` and `file`.
- `GET /api/v1/videos/{id}`
- `GET /api/v1/videos/{id}/play` — video stream with byte-range support.

## Useful commands

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
docker compose exec backend alembic current
docker compose down
```

## Current MVP limitations

Videos are published publicly after upload. Transcoding, thumbnail generation, private/unlisted playback permissions, likes, comments, subscriptions, playlists, moderation UI and background processing are not part of this two-day MVP. Do not expose the MinIO console or database publicly. For an Internet-facing deployment, put HTTPS in front of the frontend and configure firewall rules and backups.
