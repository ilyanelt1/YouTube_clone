# Architecture

The MVP uses a modular monolith for the HTTP API and a separately deployable worker for asynchronous media processing. This limits operational complexity while preserving module boundaries.

- React + TypeScript: frontend SPA.
- FastAPI: HTTP API and application services.
- PostgreSQL: users, roles, video metadata, access grants, comments, likes, subscriptions, playlists and moderation records.
- MinIO: original/processed videos and thumbnails.
- Redis/Celery: asynchronous media jobs.
- FFmpeg: probing, transcoding and thumbnail generation.
- Nginx: frontend hosting and API reverse proxy.

Private media stays in private object storage. The API authorizes a viewer before issuing a short-lived signed URL. Object keys are generated server-side.

Planned backend modules: identity, videos, interactions, channels, moderation and media.
