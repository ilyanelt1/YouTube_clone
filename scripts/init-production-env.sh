#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env.production"

if [[ -e "$ENV_FILE" ]]; then
  printf 'Файл %s уже существует. Он не будет перезаписан.\n' "$ENV_FILE" >&2
  exit 1
fi

if ! command -v openssl >/dev/null 2>&1; then
  printf 'Не найден openssl. Установите его и повторите запуск.\n' >&2
  exit 1
fi

read -r -p "Домен приложения (например, video.example.com): " DOMAIN
read -r -p "Email для уведомлений Let's Encrypt: " ACME_EMAIL

if [[ ! "$DOMAIN" =~ ^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; then
  printf 'Похоже, домен указан некорректно.\n' >&2
  exit 1
fi

if [[ ! "$ACME_EMAIL" =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]]; then
  printf 'Похоже, email указан некорректно.\n' >&2
  exit 1
fi

SECRET_KEY="$(openssl rand -hex 32)"
POSTGRES_PASSWORD="$(openssl rand -hex 32)"
MINIO_ROOT_PASSWORD="$(openssl rand -hex 32)"
REDIS_PASSWORD="$(openssl rand -hex 32)"

umask 077
cat > "$ENV_FILE" <<EOF
APP_ENV=production
DOMAIN=$DOMAIN
ACME_EMAIL=$ACME_EMAIL

SECRET_KEY=$SECRET_KEY
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=30

POSTGRES_IMAGE=postgres:17-alpine
POSTGRES_DB=youtube
POSTGRES_USER=youtube
POSTGRES_PASSWORD=$POSTGRES_PASSWORD

MINIO_IMAGE=ghcr.io/seaweedfs/minio-compat:latest
MINIO_ROOT_USER=youtube-storage
MINIO_ROOT_PASSWORD=$MINIO_ROOT_PASSWORD
S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY=youtube-storage
S3_SECRET_KEY=$MINIO_ROOT_PASSWORD

REDIS_IMAGE=redis:7-alpine
REDIS_PASSWORD=$REDIS_PASSWORD
REDIS_URL=redis://:$REDIS_PASSWORD@redis:6379/0

CADDY_IMAGE=caddy:2-alpine
EOF

chmod 600 "$ENV_FILE"
printf '\nСоздан %s с уникальными секретами. Права доступа: 600.\n' "$ENV_FILE"
printf 'Файл не добавляйте в Git. Для замены домена или email отредактируйте его вручную.\n'
