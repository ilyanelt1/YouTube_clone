from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_optional_current_user
from app.db.session import get_db
from app.models import (
    Channel,
    ChannelSubscription,
    Comment,
    Notification,
    User,
    Video,
    VideoReaction,
    VideoRepost,
    VideoShare,
    VideoViewHistory,
)

from app.services.video_access import get_accessible_video

router = APIRouter(tags=["social"])


class ReactionInput(BaseModel):
    reaction: Literal["like", "dislike"] | None


class CommentInput(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    parent_id: UUID | None = None


class CommentRead(BaseModel):
    id: UUID
    video_id: UUID
    parent_id: UUID | None
    body: str
    author_name: str
    author_handle: str
    created_at: datetime
    updated_at: datetime


class CommentList(BaseModel):
    items: list[CommentRead]
    total: int


def serialize_comment(comment: Comment) -> CommentRead:
    return CommentRead(
        id=comment.id,
        video_id=comment.video_id,
        parent_id=comment.parent_id,
        body=comment.body,
        author_name=comment.author.display_name,
        author_handle=comment.author.username,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


@router.post("/videos/{video_id}/view")
def record_view(
    video_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_optional_current_user)],
) -> dict:
    get_accessible_video(video_id, db, user)
    db.execute(update(Video).where(Video.id == video_id).values(view_count=Video.view_count + 1))
    if user is not None:
        history = db.get(VideoViewHistory, (user.id, video_id))
        if history is None:
            db.add(VideoViewHistory(user_id=user.id, video_id=video_id))
        else:
            history.watched_at = datetime.now(UTC)
    db.commit()
    return {"views": db.scalar(select(Video.view_count).where(Video.id == video_id)) or 0}


@router.get("/videos/{video_id}/engagement")
def get_engagement(
    video_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_optional_current_user)],
) -> dict:
    get_accessible_video(video_id, db, user)
    likes = (
        db.scalar(
            select(func.count())
            .select_from(VideoReaction)
            .where(VideoReaction.video_id == video_id, VideoReaction.reaction == "like")
        )
        or 0
    )
    dislikes = (
        db.scalar(
            select(func.count())
            .select_from(VideoReaction)
            .where(VideoReaction.video_id == video_id, VideoReaction.reaction == "dislike")
        )
        or 0
    )
    comments = (
        db.scalar(select(func.count()).select_from(Comment).where(Comment.video_id == video_id))
        or 0
    )
    shares = (
        db.scalar(
            select(func.count()).select_from(VideoShare).where(VideoShare.video_id == video_id)
        )
        or 0
    )
    reposts = (
        db.scalar(
            select(func.count()).select_from(VideoRepost).where(VideoRepost.video_id == video_id)
        )
        or 0
    )
    viewer_reposted = False
    if user is not None:
        viewer_reposted = db.get(VideoRepost, (video_id, user.id)) is not None
    viewer_reaction = None
    if user is not None:
        viewer_reaction = db.scalar(
            select(VideoReaction.reaction).where(
                VideoReaction.video_id == video_id, VideoReaction.user_id == user.id
            )
        )
    return {
        "likes": likes,
        "dislikes": dislikes,
        "comments": comments,
        "shares": shares,
        "reposts": reposts,
        "viewer_reposted": viewer_reposted,
        "views": get_accessible_video(video_id, db, user).view_count,
        "viewer_reaction": viewer_reaction,
    }


@router.put("/videos/{video_id}/reaction")
def set_reaction(
    video_id: UUID,
    payload: ReactionInput,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    get_accessible_video(video_id, db, user)
    reaction = db.scalar(
        select(VideoReaction).where(
            VideoReaction.video_id == video_id, VideoReaction.user_id == user.id
        )
    )
    previous_reaction = reaction.reaction if reaction is not None else None
    if payload.reaction is None:
        if reaction is not None:
            db.delete(reaction)
    elif reaction is None:
        db.add(VideoReaction(video_id=video_id, user_id=user.id, reaction=payload.reaction))
    else:
        reaction.reaction = payload.reaction
    if payload.reaction == "like" and previous_reaction != "like":
        video = get_accessible_video(video_id, db, user)
        if video.channel.owner_id != user.id:
            notification_exists = db.scalar(
                select(Notification.id)
                .where(
                    Notification.recipient_id == video.channel.owner_id,
                    Notification.actor_id == user.id,
                    Notification.video_id == video_id,
                    Notification.kind == "video_like",
                )
                .limit(1)
            )
            if notification_exists is None:
                db.add(
                    Notification(
                        recipient_id=video.channel.owner_id,
                        actor_id=user.id,
                        video_id=video_id,
                        kind="video_like",
                        message=f"@{user.username} оценил(а) ваше видео",
                    )
                )
    db.commit()
    return get_engagement(video_id, db, user)


@router.get("/videos/{video_id}/comments", response_model=CommentList)
def list_comments(
    video_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_optional_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CommentList:
    get_accessible_video(video_id, db, user)
    base = select(Comment).where(Comment.video_id == video_id).order_by(Comment.created_at.asc())
    total = db.scalar(select(func.count(Comment.id)).where(Comment.video_id == video_id)) or 0
    items = db.scalars(base.offset(offset).limit(limit)).all()
    return CommentList(items=[serialize_comment(item) for item in items], total=total)


@router.post("/videos/{video_id}/comments", response_model=CommentRead, status_code=201)
def add_comment(
    video_id: UUID,
    payload: CommentInput,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> CommentRead:
    get_accessible_video(video_id, db, user)
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail="Comment cannot be empty")
    if payload.parent_id is not None:
        parent = db.get(Comment, payload.parent_id)
        if parent is None or parent.video_id != video_id or parent.parent_id is not None:
            raise HTTPException(status_code=422, detail="Invalid parent comment")
    comment = Comment(video_id=video_id, user_id=user.id, parent_id=payload.parent_id, body=body)
    db.add(comment)
    db.flush()
    if payload.parent_id is not None:
        parent = db.get(Comment, payload.parent_id)
        if parent is not None and parent.user_id != user.id:
            db.add(
                Notification(
                    recipient_id=parent.user_id,
                    actor_id=user.id,
                    video_id=video_id,
                    comment_id=comment.id,
                    kind="comment_reply",
                    message=f"@{user.username} ответил(а) на ваш комментарий",
                )
            )
    else:
        video = get_accessible_video(video_id, db, user)
        owner_id = video.channel.owner_id
        if owner_id != user.id:
            db.add(
                Notification(
                    recipient_id=owner_id,
                    actor_id=user.id,
                    video_id=video_id,
                    comment_id=comment.id,
                    kind="new_comment",
                    message=f"@{user.username} оставил(а) комментарий к вашему видео",
                )
            )
    db.commit()
    db.refresh(comment)
    return serialize_comment(comment)


@router.patch("/comments/{comment_id}", response_model=CommentRead)
def edit_comment(
    comment_id: UUID,
    payload: CommentInput,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> CommentRead:
    comment = db.get(Comment, comment_id)
    if comment is None or comment.user_id != user.id:
        raise HTTPException(status_code=404, detail="Comment not found")
    body = payload.body.strip()
    if not body:
        raise HTTPException(status_code=422, detail="Comment cannot be empty")
    comment.body = body
    db.commit()
    db.refresh(comment)
    return serialize_comment(comment)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_comment(
    comment_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    comment = db.get(Comment, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    video = db.get(Video, comment.video_id)
    if comment.user_id != user.id and (video is None or video.channel.owner_id != user.id):
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.parent_id is None:
        db.execute(delete(Comment).where(Comment.parent_id == comment.id))
    db.delete(comment)
    db.commit()


@router.post("/videos/{video_id}/share")
def share_video(
    video_id: UUID,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    get_accessible_video(video_id, db, user)
    existing = db.get(VideoShare, (video_id, user.id))
    if existing is None:
        db.add(VideoShare(video_id=video_id, user_id=user.id))
        db.commit()
    shares = (
        db.scalar(
            select(func.count()).select_from(VideoShare).where(VideoShare.video_id == video_id)
        )
        or 0
    )
    return {"shares": shares, "share_url": f"{str(request.base_url).rstrip('/')}/?video={video_id}"}


@router.put("/videos/{video_id}/repost")
def repost_video(
    video_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    get_accessible_video(video_id, db, user)
    if db.get(VideoRepost, (video_id, user.id)) is None:
        db.add(VideoRepost(video_id=video_id, user_id=user.id))
        db.commit()
    return get_engagement(video_id, db, user)


@router.delete("/videos/{video_id}/repost")
def undo_repost(
    video_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    get_accessible_video(video_id, db, user)
    repost = db.get(VideoRepost, (video_id, user.id))
    if repost is not None:
        db.delete(repost)
        db.commit()
    return get_engagement(video_id, db, user)


@router.put("/channels/{handle}/subscription")
def subscribe(
    handle: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    channel = db.scalar(select(Channel).where(Channel.handle == handle))
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    if channel.owner_id == user.id:
        raise HTTPException(status_code=400, detail="You cannot subscribe to your own channel")
    subscription = db.get(ChannelSubscription, (user.id, channel.id))
    if subscription is None:
        db.add(ChannelSubscription(subscriber_id=user.id, channel_id=channel.id))
        db.add(
            Notification(
                recipient_id=channel.owner_id,
                actor_id=user.id,
                kind="new_subscriber",
                message=f"@{user.username} подписался(ась) на ваш канал",
            )
        )
        db.commit()
    return _subscription_status(handle, db, user)


@router.delete("/channels/{handle}/subscription")
def unsubscribe(
    handle: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    channel = db.scalar(select(Channel).where(Channel.handle == handle))
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    subscription = db.get(ChannelSubscription, (user.id, channel.id))
    if subscription is not None:
        db.delete(subscription)
        db.commit()
    return _subscription_status(handle, db, user)


@router.get("/channels/{handle}/subscription")
def get_subscription_status(
    handle: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User | None, Depends(get_optional_current_user)],
) -> dict:
    return _subscription_status(handle, db, user)


def _subscription_status(handle: str, db: Session, user: User | None) -> dict:
    channel = db.scalar(select(Channel).where(Channel.handle == handle))
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    subscribers = (
        db.scalar(
            select(func.count())
            .select_from(ChannelSubscription)
            .where(ChannelSubscription.channel_id == channel.id)
        )
        or 0
    )
    subscribed = False
    if user is not None:
        subscribed = db.get(ChannelSubscription, (user.id, channel.id)) is not None
    return {"subscribed": subscribed, "subscribers": subscribers}
