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
- Video reposts with per-user duplicate protection, share links with unique per-user share counts, playback view counters and channel subscriptions.\n- Public channel pages with creator video catalogs and a personalized subscriptions feed.\n- Signed-in watch history, saved favorites and user-managed playlists with public, unlisted and private visibility.\n- Video search by title/description with channel, popularity, publication date and duration filters.\n- In-app notifications for new subscribers, new videos from followed channels, likes, comments and comment replies.
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
- `GET /api/v1/videos` — public feed and search; optional `q`, `channel`, `sort` (`newest`, `oldest`, `popular`), `duration` (`short`, `long`), `limit`, `offset`.
- `POST /api/v1/videos/upload` — authenticated multipart upload. Required: `title`, `file`; optional: `description`, `visibility` (`public`, `unlisted`, `private`), `thumbnail`, client-detected `duration_seconds`.
- `GET /api/v1/videos/mine` — authenticated user's videos.
- `GET /api/v1/videos/{id}` — video metadata (private videos require the owner session).
- `GET /api/v1/videos/{id}/play` — streamed playback with HTTP byte-range support.
- `GET /api/v1/videos/{id}/thumbnail` — cover image.
- `PATCH /api/v1/videos/{id}` — owner-only update of title, description and visibility.
- `DELETE /api/v1/videos/{id}` — owner-only deletion of the database record and stored media objects.


### Channels and personal library
- `GET /api/v1/channels/{handle}` — public channel profile, subscriber count and public videos.
- `GET /api/v1/feed/subscriptions` — latest public videos from subscribed channels.
- `GET /api/v1/users/me/history` / `DELETE /api/v1/users/me/history` — signed-in watch history and clear history.
- `GET /api/v1/users/me/favorites` — saved videos.
- `PUT` / `DELETE /api/v1/videos/{id}/favorite` — save or remove a favorite.
- `GET /api/v1/playlists/mine`, `POST /api/v1/playlists` — list and create playlists.
- `GET` / `PATCH` / `DELETE /api/v1/playlists/{id}` — view, update and delete a playlist.
- `POST` / `DELETE /api/v1/playlists/{id}/videos/{video_id}` — add or remove a playlist item.
- `GET /api/v1/notifications` — recent notifications and unread count.
- `POST /api/v1/notifications/{id}/read` / `POST /api/v1/notifications/read-all` — mark notifications as read.

### Social interactions
- `GET /api/v1/videos/{id}/engagement` — likes, dislikes, comments, shares, views and the current user reaction.
- `PUT /api/v1/videos/{id}/reaction` — set `like`, `dislike` or `null` to remove a reaction.
- `GET /api/v1/videos/{id}/comments` — list comments and replies.
- `POST /api/v1/videos/{id}/comments` — add a comment; optional `parent_id` creates a reply.
- `PATCH /api/v1/comments/{id}` / `DELETE /api/v1/comments/{id}` — edit or delete your own comment; video owners can moderate comments under their videos.
- `PUT` / `DELETE /api/v1/videos/{id}/repost` — repost a video or undo your repost.
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

Video transcoding, automatic cover generation, resumable/chunked uploads, upload cancellation, realtime push notifications, playlist collaboration and background processing are not implemented yet. Covers can be uploaded manually. Social features are an MVP: view counts are incremented when the watch page opens, and share counts track unique signed-in users rather than external share destinations. Reposts are stored per user and counted, but are not yet shown in a dedicated public repost feed. Notifications are in-app and refreshed when the notification panel is opened. Do not expose the storage console or database publicly. For an Internet-facing deployment, put HTTPS in front of the frontend and configure firewall rules and backups.
