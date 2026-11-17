# YouTube Clone

A YouTube-inspired video hosting MVP built with FastAPI, PostgreSQL, S3-compatible object storage and React.

## Implemented

- Email/username registration and login.
- Argon2id password hashing, short-lived JWT access tokens and rotating HttpOnly refresh sessions.
- PostgreSQL schema managed by Alembic.
- Authenticated video upload: MP4, WebM and MOV, up to 500 MB.
- Server-side validation of MIME type, file signature and file size.
- Optional JPEG, PNG or WebP cover image upload, up to 5 MB.
- Public, unlisted and private visibility.
- Private video details, covers and playback protected by the HttpOnly refresh-session cookie.
- Public feed, title search, creator's video library, metadata editing and video deletion.
- Browser upload progress indicator.
- HTTP byte-range streaming for playback and seeking.
- Video likes/dislikes, threaded comments, comment moderation by authors and channel owners.
- Share links with unique per-user share counts, playback view counters and channel subscriptions.
- Docker Compose services for PostgreSQL 17, Redis, S3-compatible storage, backend and frontend.

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
   Put the generated value in `SECRET_KEY`. Keep the PostgreSQL password identical in `POSTGRES_PASSWORD` and `DATABASE_URL`; keep the storage password identical in `MINIO_ROOT_PASSWORD` and `S3_SECRET_KEY`.
4. Build and start the stack:
   ```bash
   docker compose up --build -d
   ```
5. Open:
   - Frontend: http://localhost:8083
   - API documentation: http://localhost:8003/docs
   - Storage console (local machine only): http://localhost:9003

## Main API

### Authentication
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`

### Videos
- `GET /api/v1/videos` — public feed; optional `q`, `limit`, `offset`.
- `POST /api/v1/videos/upload` — authenticated multipart upload. Required: `title`, `file`; optional: `description`, `visibility` (`public`, `unlisted`, `private`), `thumbnail`.
- `GET /api/v1/videos/mine` — authenticated user's videos.
- `GET /api/v1/videos/{id}` — video metadata (private videos require the owner session).
- `GET /api/v1/videos/{id}/play` — streamed playback with HTTP byte-range support.
- `GET /api/v1/videos/{id}/thumbnail` — cover image.
- `PATCH /api/v1/videos/{id}` — owner-only update of title, description and visibility.
- `DELETE /api/v1/videos/{id}` — owner-only deletion of the database record and stored media objects.

### Social interactions
- `GET /api/v1/videos/{id}/engagement` — likes, dislikes, comments, shares, views and the current user reaction.
- `PUT /api/v1/videos/{id}/reaction` — set `like`, `dislike` or `null` to remove a reaction.
- `GET /api/v1/videos/{id}/comments` — list comments and replies.
- `POST /api/v1/videos/{id}/comments` — add a comment; optional `parent_id` creates a reply.
- `PATCH /api/v1/comments/{id}` / `DELETE /api/v1/comments/{id}` — edit or delete your own comment; video owners can moderate comments under their videos.
- `POST /api/v1/videos/{id}/share` — create a unique share record and return a deep link.
- `POST /api/v1/videos/{id}/view` — increment the playback view counter.
- `GET /api/v1/channels/{handle}/subscription` — subscription state and subscriber count.
- `PUT` / `DELETE /api/v1/channels/{handle}/subscription` — subscribe or unsubscribe.

## Upload limits and formats

- Video: MP4, WebM, MOV; maximum 500 MB.
- Cover image: JPEG, PNG, WebP; maximum 5 MB.
- The browser checks the selected file before sending it; the API repeats the checks and validates the file signature.
- Nginx allows request bodies up to 520 MB so multipart uploads can reach the API.

## Useful commands

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
docker compose exec backend alembic current
docker compose down
```

## Current MVP limitations

Video transcoding, automatic cover generation, resumable/chunked uploads, upload cancellation, playlists, notifications and background processing are not implemented yet. Covers can be uploaded manually. Social features are an MVP: view counts are incremented when the watch page opens, and share counts track unique signed-in users rather than external share destinations. Do not expose the storage console or database publicly. For an Internet-facing deployment, put HTTPS in front of the frontend and configure firewall rules and backups.
