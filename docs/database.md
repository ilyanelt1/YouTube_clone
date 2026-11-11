# Database design

The scaffold does not create application tables yet. All schema changes will be introduced through Alembic migrations.

Planned entities: users, roles, videos, video access grants, likes, comments, subscriptions, playlists, playlist items, views, reports, moderation actions and refresh-token sessions.

PostgreSQL stores relational metadata and authorization state. MinIO stores binary media; database rows store object keys and processing metadata, never video bytes.

Constraints to implement: unique email, one like per user/video, no self-subscription, foreign keys and indexes for feed/channel/search queries.
