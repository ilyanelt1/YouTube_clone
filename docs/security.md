# Security baseline

- Keep secrets in environment variables; never commit real credentials.
- Hash passwords with Argon2id through pwdlib. Plaintext passwords must never be persisted or logged.
- Access tokens are short-lived JWTs signed with HS256. Validate the signature, issuer, token type and expiry.
- Refresh tokens are opaque random values. Store only their SHA-256 hashes in PostgreSQL.
- Send refresh tokens in an HttpOnly, SameSite=Lax cookie scoped to the authentication API. Enable Secure outside local development.
- Rotate refresh tokens on every refresh. Reuse of a revoked token revokes the active sessions in that token family.
- Revoke refresh sessions on logout and reject inactive users.
- Enforce authorization server-side for every protected operation.
- Keep private media in private buckets and authorize before issuing short-lived signed URLs.
- Validate upload size and actual media format. Generate storage keys server-side.
- Never log passwords, access tokens, refresh tokens or signed URLs. Audit moderation actions.
- Add rate limiting and CSRF/origin protections before exposing authentication publicly.
