# YouTube Clone

YouTube-inspired video hosting platform built with FastAPI, PostgreSQL and React.

## Status
Initial scaffold. Authentication, media upload/processing, playback, social features and moderation are planned next.

## Stack
Python 3.13, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 17, S3-compatible object storage, Redis/Celery, FFmpeg, React, TypeScript, Vite, Docker Compose and Nginx.

## Local start
1. Copy `.env.example` to `.env` and replace development secrets.
2. Run `docker compose up --build -d`.
3. Frontend: http://localhost:8083
4. API docs: http://localhost:8003/docs
5. S3-compatible endpoint: http://localhost:9002
6. Storage console: http://localhost:9003

Development scaffold only; migrations, bucket initialization, authentication, workers and production hardening are not implemented yet.
