from uuid import uuid4

from app.services.view_deduplication import make_view_key


def test_anonymous_view_key_uses_ip_and_user_agent_without_storing_them() -> None:
    video_id = uuid4()
    first = make_view_key(video_id, None, "192.0.2.1", "Browser A")
    same_viewer = make_view_key(video_id, None, "192.0.2.1", "Browser A")
    different_ip = make_view_key(video_id, None, "192.0.2.2", "Browser A")
    different_agent = make_view_key(video_id, None, "192.0.2.1", "Browser B")

    assert first == same_viewer
    assert first != different_ip
    assert first != different_agent
    assert "192.0.2.1" not in first
    assert "Browser A" not in first


def test_authenticated_view_key_uses_user_id_only() -> None:
    video_id = uuid4()
    user_id = uuid4()

    first = make_view_key(video_id, user_id, "192.0.2.1", "Browser A")
    same_user = make_view_key(video_id, user_id, "192.0.2.2", "Browser B")
    other_user = make_view_key(video_id, uuid4(), "192.0.2.1", "Browser A")

    assert first == same_user
    assert first != other_user
