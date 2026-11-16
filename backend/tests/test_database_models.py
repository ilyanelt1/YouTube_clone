from sqlalchemy.orm import configure_mappers

import app.models  # noqa: F401
from app.db.base import Base


def test_initial_database_tables_are_registered() -> None:
    expected = {
        "users",
        "roles",
        "user_roles",
        "channels",
        "videos",
        "video_access_grants",
    }
    assert expected.issubset(Base.metadata.tables)


def test_orm_relationships_are_valid() -> None:
    configure_mappers()


def test_video_access_grants_prevent_duplicate_user_video_pairs() -> None:
    table = Base.metadata.tables["video_access_grants"]
    assert {column.name for column in table.primary_key.columns} == {"video_id", "user_id"}
