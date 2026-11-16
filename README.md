# YouTube Clone

YouTube-inspired video hosting platform built with FastAPI, PostgreSQL and React.

## Status

Project scaffold and database foundation are implemented: FastAPI health endpoint, SQLAlchemy models, PostgreSQL 17, initial Alembic migration and Docker Compose migration service. Registration and authentication API are being added in the current milestone.

## Stack

Python 3.14, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 17, S3-compatible object storage, Redis/Celery, FFmpeg, React, TypeScript, Vite, Docker Compose and Nginx.

## Local start

1. Install Python 3.14 for local backend development.
2. Copy .env.example to .env and replace development secrets.
3. Run docker compose up --build -d.
4. Frontend: http://localhost:8083
5. API docs: http://localhost:8003/docs
6. S3-compatible endpoint: http://localhost:9002
7. Storage console: http://localhost:9003

Development scaffold only. Media upload, processing workers, playback, social features and production hardening are not implemented yet.
