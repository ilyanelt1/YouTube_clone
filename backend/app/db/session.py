from collections.abc import Generator

import sqlalchemy as sa
import sqlalchemy.orm as orm

from app.core.config import get_settings


engine = sa.create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = orm.sessionmaker(
    bind=engine,
    class_=orm.Session,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[orm.Session]:
    with SessionLocal() as session:
        yield session
