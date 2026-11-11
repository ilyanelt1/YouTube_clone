# Security plan

- Keep secrets in environment variables.
- Hash passwords with Argon2.
- Validate JWT signature, expiry and token type.
- Enforce role and resource ownership checks in backend services.
- Authorize private-video access before generating signed URLs.
- Keep buckets private; enforce upload limits and inspect actual media format with FFprobe.
- Generate object keys server-side; rate-limit authentication and upload initialization.
- Never log credentials, tokens or signed URLs. Audit moderation actions.
