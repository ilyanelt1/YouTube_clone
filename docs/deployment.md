# Production deployment

Инструкция рассчитана на один Ubuntu-сервер с публичным IPv4-адресом и доменом. Production-стек отделён от локального `docker-compose.yml`: он использует Caddy для HTTPS, не публикует PostgreSQL, Redis, MinIO и backend в интернет и сохраняет данные в Docker volumes.

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

Скрипт запросит домен и контактный email, сгенерирует независимые случайные секреты через OpenSSL и создаст `.env.production` с правами `600`. Проверьте домен и email в файле перед запуском. Отдельный `DATABASE_URL` в файле не нужен: Compose собирает DSN из `POSTGRES_USER`, `POSTGRES_PASSWORD` и `POSTGRES_DB` при запуске контейнеров.

**Не коммитьте и не отправляйте файл `.env.production`.** Он содержит ключ подписи токенов, пароли PostgreSQL, Redis и S3. В репозитории находится только безопасный шаблон `.env.production.example`.

## 3. Проверьте конфигурацию и запустите сервисы

```bash
docker compose --env-file .env.production -f docker-compose.production.yml config --quiet
docker compose --env-file .env.production -f docker-compose.production.yml up --build -d
```

Проверить состояние и логи:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml ps
docker compose --env-file .env.production -f docker-compose.production.yml logs -f caddy backend
```

После того как DNS обновится, откройте `https://ВАШ_ДОМЕН`. Caddy автоматически запросит и обновит TLS-сертификат. Для выпуска сертификата домен должен указывать на этот сервер, а входящие TCP-порты 80 и 443 должны быть доступны извне.

## 4. Лимиты ресурсов

Production Compose задаёт суммарный жёсткий бюджет контейнеров: **0.25 CPU и 512 MB RAM**. Лимиты распределены между всеми сервисами, включая одноразовый контейнер миграций:

| Сервис | CPU | RAM |
|---|---:|---:|
| PostgreSQL | 0.06 | 128 MB |
| S3-хранилище | 0.04 | 96 MB |
| Redis | 0.01 | 16 MB |
| Миграции | 0.03 | 48 MB |
| Backend | 0.07 | 176 MB |
| Frontend | 0.02 | 24 MB |
| Caddy | 0.02 | 24 MB |
| **Итого** | **0.25** | **512 MB** |

Это верхние пределы, а не резервирование памяти. При такой небольшой квоте возможны замедление или OOM при одновременной загрузке/обработке больших файлов; не увеличивайте лимиты отдельных сервисов без пересчёта общего бюджета.

## 5. Что запускается

- Caddy — единственная точка входа с опубликованными портами 80/443; автоматически завершает HTTPS и проксирует запросы на frontend.
- Frontend — Nginx со статикой и проксированием `/api/` к backend.
- Backend — FastAPI; в production refresh-cookie получает флаг `Secure`.
- Migrate — применяет Alembic-миграции и должен завершиться успешно до запуска backend.
- PostgreSQL, Redis и S3-хранилище доступны только во внутренней Docker-сети.
- PostgreSQL, Redis, S3-объекты и данные Caddy хранятся в именованных Docker volumes.

Bucket `youtube-videos` создаётся backend автоматически при первом обращении к хранилищу. Скрипт не импортирует и не переносит старые данные MinIO.

## 6. Создайте администратора

Сначала зарегистрируйте обычный аккаунт через интерфейс. Затем назначьте ему роль из доверенной консоли сервера:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml exec backend python -m app.cli ИМЯ_ПОЛЬЗОВАТЕЛЯ admin
```

Не выдавайте административную роль через публичную регистрацию.

## 7. Резервное копирование

Резервная копия PostgreSQL не содержит видео и обложки из S3-хранилища. Сохраняйте базу и volume `minio_data` отдельно, храните копии вне VPS и регулярно проверяйте восстановление.

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

## 8. Обновление

Перед обновлением сделайте резервную копию PostgreSQL и объектов. Затем получите новую версию кода и пересоберите сервисы:

```bash
git pull
docker compose --env-file .env.production -f docker-compose.production.yml up --build -d
```

Проверьте состояние контейнеров, логи миграций и открытие видео после обновления.

## 9. Ограничения этой конфигурации

Это одноузловой production baseline для MVP, а не отказоустойчивая инфраструктура: один сервер, один экземпляр сервисов, локальные Docker volumes. До серьёзной публичной нагрузки дополнительно настройте off-site backup и тест восстановления, мониторинг/оповещения, обновление и фиксацию образов по digest, ротацию секретов и ограничение частоты запросов. Фоновое транскодирование и обработка видео в проекте не добавляются.
