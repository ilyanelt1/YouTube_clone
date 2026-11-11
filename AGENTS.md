# AI Agent Instructions

Build a YouTube-like video hosting application using FastAPI, PostgreSQL and React.

## Architecture
- Modular monolith for HTTP API; separate worker for media processing.
- PostgreSQL stores relational metadata; MinIO/S3 stores media binaries.
- Keep route handlers thin and business rules in services.
- Use Alembic for every schema change.

## Security
- Never commit secrets. Hash passwords with Argon2.
- Enforce authorization server-side for every protected operation.
- Keep private media in private buckets; authorize before issuing short-lived signed URLs.
- Validate upload size and actual media format. Generate storage keys server-side.
- Never log passwords, tokens or signed URLs.

## Quality and Git
- Add tests for critical behavior and security boundaries.
- Run tests and linters; never claim a command passed unless it was executed.
- Use small purposeful conventional commits. Do not rewrite history or modify unrelated files.

## AI workflow
Inspect relevant code/tests before editing. Report changed files, decisions, commands, test results and limitations. Preserve original AI conversation exports in native formats; never fabricate them.
