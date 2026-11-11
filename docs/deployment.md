# Deployment

Current Compose configuration is a development scaffold. Production Ubuntu deployment still requires a deployment script, generated secrets, database migrations, MinIO bucket initialization, worker/media tooling, health checks, TLS, firewall guidance and backup/restore instructions.

Never deploy using example passwords from `.env.example`.
