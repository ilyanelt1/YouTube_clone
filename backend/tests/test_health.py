from collections.abc import Generator
from unittest.mock import Mock

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app


def make_client(monkeypatch, db: Session) -> TestClient:
    def override_get_db() -> Generator[Session]:
        yield db

    monkeypatch.setitem(app.dependency_overrides, get_db, override_get_db)
    return TestClient(app)


def test_health_endpoint_reports_liveness() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_endpoint_checks_database(monkeypatch) -> None:
    db = Mock()
    with make_client(monkeypatch, db) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}
    db.execute.assert_called_once()


def test_readiness_endpoint_returns_service_unavailable_when_database_fails(
    monkeypatch,
) -> None:
    db = Mock()
    db.execute.side_effect = SQLAlchemyError("database is unavailable")

    with make_client(monkeypatch, db) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "Database is unavailable"}
