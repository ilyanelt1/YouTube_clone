# Production deployment

Инструкция рассчитана на один Ubuntu-сервер с публичным IPv4-адресом, доменом и уже работающим системным Nginx. Production-стек отделён от локального `docker-compose.yml`: системный Nginx принимает HTTP/HTTPS на 80/443 и проксирует запросы в frontend-контейнер через `127.0.0.1:8080`. PostgreSQL, Redis, MinIO-compatible object storage и backend не публикуют порты наружу. PostgreSQL и S3-объекты хранятся в Docker volumes; Redis используется как временный in-memory store без сохранения на диск.

## 1. Подготовьте сервер и DNS

1. Установите Docker Engine и плагин Docker Compose v2.
2. Создайте DNS-запись `A` для домена приложения, указывающую на публичный IP сервера. При наличии IPv6 настройте корректную `AAAA`-запись или удалите ошибочную.
3. Разрешите входящие порты SSH, TCP 80 и TCP 443. UDP 443 можно открыть для HTTP/3. Не открывайте наружу порты PostgreSQL, Redis, S3 или панели хранилища.

Пример для UFW (сначала убедитесь, что SSH уже разрешён):

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
sudo ufw enable
```

## 2. Получите проект и создайте секреты

Клонируйте репозиторий и перейдите в его каталог. Затем выполните:

```bash
bash scripts/init-production-env.sh
```

Скрипт запросит домен и контактный email, сгенерирует независимые случайные секреты через OpenSSL и создаст `.env.production` с правами `600`. Проверьте домен и email в файле перед запуском.

**Не коммитьте и не отправляйте файл `.env.production`.** Он содержит ключ подписи токенов, пароли PostgreSQL, Redis и S3. В репозитории находится только безопасный шаблон `.env.production.example`.

## 3. Подготовьте системный Nginx

Порт 80 и 443 уже занят системным Nginx, поэтому Docker не должен пытаться занять эти порты. Сначала убедитесь, что DNS домена приложения указывает на этот VPS. Создайте отдельный сайт, не перезаписывая конфигурации других сайтов:

```bash
sudo nano /etc/nginx/sites-available/youtube-clone
```

Вставьте конфигурацию, заменив `video.example.com` на значение `DOMAIN` из `.env.production`:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name video.example.com;

    client_max_body_size 520m;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

Включите сайт и проверьте конфигурацию:

```bash
sudo ln -s /etc/nginx/sites-available/youtube-clone /etc/nginx/sites-enabled/youtube-clone
sudo nginx -t
sudo systemctl reload nginx
```

Если для домена ещё не настроен HTTPS, установите Certbot и получите сертификат через существующий Nginx:

```bash
sudo apt update
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d video.example.com --email admin@example.com --agree-tos --redirect
```

В команде Certbot укажи домен из `DOMAIN` и email из `ACME_EMAIL` в `.env.production`. Если HTTPS для этого домена уже настроен в Nginx, повторно Certbot запускать не нужно — достаточно добавить proxy location в существующий HTTPS server block.

## 4. Проверьте конфигурацию и запустите сервисы

```bash
docker compose --env-file .env.production -f docker-compose.production.yml config --quiet
docker compose --env-file .env.production -f docker-compose.production.yml pull db minio redis
docker compose --env-file .env.production -f docker-compose.production.yml build --pull backend frontend
docker compose --env-file .env.production -f docker-compose.production.yml up -d --remove-orphans
```

Параметр `--remove-orphans` удалит старый контейнер Caddy, который больше не используется этим Compose, но не удалит volumes с данными PostgreSQL или видео.

Проверьте frontend напрямую через локальный порт:

```bash
curl -I http://127.0.0.1:8080/
```

Проверить состояние и логи:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml ps -a
docker compose --env-file .env.production -f docker-compose.production.yml logs --tail=100 backend frontend migrate minio redis
```

После настройки Nginx откройте `https://ВАШ_ДОМЕН`.

Проверить liveness и readiness изнутри backend-контейнера:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"
docker compose --env-file .env.production -f docker-compose.production.yml exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/ready').read().decode())"
```

## 4. Что запускается

- Системный Nginx Ubuntu — внешняя точка входа на портах 80/443; HTTPS-сертификат обслуживается Certbot/Let's Encrypt на хосте.
- Frontend — Nginx со статикой и проксированием `/api/` к backend. Контейнер опубликован только на `127.0.0.1:8080`, внешний трафик приходит через системный Nginx.
- Backend — FastAPI; в production refresh-cookie получает флаг `Secure`.
- Migrate — одноразовый сервис Alembic. Он получает только настройки приложения, ключ подписи и URL PostgreSQL, ждёт готовности базы и должен завершиться успешно до запуска backend.
- Redis получает только собственный пароль. Backend получает только используемые им настройки. Полный `.env.production` не передаётся каждому контейнеру через `env_file`. Параметры `DOMAIN` и `ACME_EMAIL` используются при настройке системного Nginx/Certbot и не передаются Docker-контейнерам.
- PostgreSQL, Redis, backend и S3-compatible object storage доступны только во внутренней Docker-сети.
- PostgreSQL, Redis и S3-compatible storage имеют healthcheck. Backend стартует только после успешной проверки PostgreSQL, Redis и S3, а также после успешного завершения миграций.
- Backend healthcheck обращается к `/ready`; этот endpoint выполняет `SELECT 1` в PostgreSQL. `/health` — отдельная liveness-проверка процесса.
- Redis хранит временные ключи дедупликации просмотров с TTL 30 минут. Данные Redis не сохраняются на диск и очищаются после перезапуска контейнера; отдельный volume для Redis не подключён. Redis не входит в readiness, так как при его сбое API считает просмотры без дедупликации.
- PostgreSQL и S3-объекты хранятся в именованных Docker volumes.
- Загрузка видео выполняется синхронно через API. Нет worker, очереди задач, FFmpeg или автоматического транскодирования.

Bucket `youtube-videos` создаётся backend автоматически при первом обращении к хранилищу. Скрипт не импортирует и не переносит старые данные object storage.

**Важно при первом production-запуске:** SeaweedFS MinIO-compatible требует отдельный пустой volume. Не подключайте к нему файловый volume от настоящего MinIO: форматы хранения несовместимы. Если нужно перенести существующие объекты, поднимите старое и новое хранилища с разными volumes и скопируйте данные через S3 API (например, `mc mirror`), затем проверьте количество объектов и чтение файлов до переключения приложения.

## 5. Создайте администратора

Сначала зарегистрируйте обычный аккаунт через интерфейс. Затем назначьте ему роль из доверенной консоли сервера:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml exec backend python -m app.cli ИМЯ_ПОЛЬЗОВАТЕЛЯ admin
```

Не выдавайте административную роль через публичную регистрацию.

## 6. Резервное копирование

Резервная копия PostgreSQL не содержит видео и обложки из S3-хранилища. Redis — временное хранилище, его данные резервировать не нужно. Сохраняйте базу и volume `minio_data` отдельно, храните копии вне VPS и регулярно проверяйте восстановление.

Пример дампа PostgreSQL:

```bash
mkdir -p backups
set -a
. ./.env.production
set +a
docker compose --env-file .env.production -f docker-compose.production.yml exec -T db \
  pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > "backups/postgres-$(date +%F-%H%M%S).sql"
```

Перед резервным копированием файлового volume согласуйте snapshot или остановку сервиса хранилища; не копируйте работающий volume как обычный каталог без согласованного способа snapshot/backup.

## 7. Обновление

Перед обновлением сделайте резервную копию PostgreSQL и объектов. Затем получите новую версию кода и пересоберите сервисы:

```bash
git pull origin main
docker compose --env-file .env.production -f docker-compose.production.yml up --build -d
```

Проверьте состояние контейнеров, логи миграций и открытие видео после обновления.

## 8. Ресурсы и размер демо-каталога

В Compose заданы лимиты памяти для постоянно работающих контейнеров: PostgreSQL 160 МиБ, object storage 96 МиБ, Redis 24 МиБ, backend 128 МиБ и frontend 24 МиБ — суммарно 432 МиБ. Одноразовый контейнер миграций имеет лимит 48 МиБ на время запуска. Суммарный CPU limit постоянно работающих контейнеров — около 0.45 CPU.

Это лимиты контейнеров, а не рекомендуемый объём физической памяти VPS: операционной системе, Docker daemon и прочим процессам нужен дополнительный запас. На диске отдельно должны помещаться Docker images, PostgreSQL volume, MinIO data и резервные копии. Compose не задаёт лимит объёма MinIO volume.

Для первого наполнения используй 5–7 коротких роликов примерно на 150–250 МБ суммарно, преимущественно MP4/WebM 720p или 1080p. Не бери 4K и не загружай сразу сотни роликов: проект не сжимает и не транскодирует файлы, а отдаёт загруженный оригинал. Подборка открытых короткометражек и требования к атрибуции описаны в [demo-media.md](demo-media.md).

## Ограничения этой конфигурации

Это одноузловой production baseline для MVP, а не отказоустойчивая инфраструктура: один сервер, один экземпляр сервисов, локальные Docker volumes. До серьёзной публичной нагрузки дополнительно настройте off-site backup и тест восстановления, мониторинг/оповещения, обновление и фиксацию образов по digest, ротацию секретов и ограничение частоты запросов. Rate limiting и CSRF/origin-защита пока не реализованы. Фоновое транскодирование и обработка видео в проекте не добавляются.
