# YouTube Clone

YouTube-inspired video hosting platform built with FastAPI, PostgreSQL and React.

## Status
Initial scaffold. Authentication, media upload/processing, playback, social features and moderation are planned next.

## Stack
Python 3.12, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, MinIO, Redis/Celery, FFmpeg, React, TypeScript, Vite, Docker Compose and Nginx.

## Local start
1. Copy `.env.example` to `.env` and replace development secrets.
2. Run `docker compose up --build -d`.
3. API docs: http://localhost:8000/docs
4. MinIO console: http://localhost:9001

Development scaffold only; not production-ready. Migrations, bucket initialization, authentication, workers and production hardening are not implemented yet.
