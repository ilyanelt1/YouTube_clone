# Testing strategy

Critical scenarios to automate:
1. Registration, login and invalid credentials.
2. Role-based access for user, moderator and administrator.
3. Video upload lifecycle and invalid file rejection.
4. Playback authorization for public and private videos.
5. Grant and revoke private-video access.
6. Unique likes per user/video.
7. Comment creation, ownership and moderation.
8. Reports and moderator actions.
9. Liveness via `/health` and readiness via `/ready`, including PostgreSQL connectivity and the unavailable-database response.

The readiness probe executes `SELECT 1` against PostgreSQL and returns HTTP 503 when the database cannot be reached. Redis is intentionally excluded: temporary Redis outages must not make the API unready because view counting has a fail-open fallback.

Use isolated test configuration and disposable test data.
