# Authentication API

The authentication API is available under /api/v1/auth.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | /register | Create an account and start a session |
| POST | /login | Authenticate with email or username |
| POST | /refresh | Rotate the HttpOnly refresh cookie and issue a new access token |
| POST | /logout | Revoke the current refresh session |
| GET | /me | Return the authenticated user's profile |

Registration accepts email, username, display name and password. Usernames are normalized to lowercase. Passwords must contain at least 8 characters and are stored as Argon2id hashes.

Login and registration return a short-lived bearer access token in JSON. The opaque refresh token is set only as an HttpOnly cookie named youtube_refresh; it is not included in the response body. Browser requests to refresh and logout must include credentials.

## Access-token usage

Send the access token in the Authorization header:

    Authorization: Bearer <access_token>

The access token lifetime is configured by ACCESS_TOKEN_EXPIRE_MINUTES (default 15 minutes). Refresh sessions are configured by REFRESH_TOKEN_EXPIRE_DAYS (default 30 days).

## Refresh-token behavior

The raw refresh token is never stored in PostgreSQL. The database stores its SHA-256 hash, expiry, revocation time, token family, user-agent and client IP. Every successful refresh revokes the presented token and creates a replacement in the same family. Reuse of an already-revoked token revokes the remaining active sessions in that family.

The refresh cookie is HttpOnly, SameSite=Lax and scoped to /api/v1/auth. Secure is enabled when APP_ENV is not development, dev or test.

## Configuration

Set SECRET_KEY to a unique random value of at least 32 characters in production. Generate one with:

    python -c "import secrets; print(secrets.token_urlsafe(48))"

Do not reuse the example or development key in production. Email verification, password reset, OAuth, authentication rate limiting and CSRF/origin enforcement are not part of this milestone.
