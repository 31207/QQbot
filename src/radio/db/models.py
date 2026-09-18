"""ORM 模型（PostgreSQL）。

时间字段统一用 DateTime（Python 侧写入 datetime），``day`` / ``week`` 是周期键（TEXT）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    return datetime.now()


class Base(DeclarativeBase):
    pass


class Song(Base):
    """歌曲库。``selected`` 为 web 后台「选用」标记。"""

    __tablename__ = "songs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String, nullable=False, default="")
    source_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    name: Mapped[str] = mapped_column(String, nullable=False, default="")
    artist: Mapped[str] = mapped_column(String, nullable=False, default="")
    album: Mapped[str] = mapped_column(String, nullable=False, default="")
    cover: Mapped[str] = mapped_column(String, nullable=False, default="")
    duration: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    url: Mapped[str] = mapped_column(String, nullable=False, default="")
    link: Mapped[str] = mapped_column(String, nullable=False, default="")
    is_banned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    play_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_songs_source_srcid"),)


class User(Base):
    """点歌用户。``is_banned`` 为封禁标记。"""

    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    is_banned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)


class UserRequest(Base):
    """用户点歌记录。同一用户对同一首歌仅一条，重复点歌更新时间（置顶）并累计当日/本周次数。"""

    __tablename__ = "user_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    song_id: Mapped[int] = mapped_column(Integer, ForeignKey("songs.id"), nullable=False)
    time: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    remark: Mapped[str] = mapped_column(String, nullable=False, default="")
    day: Mapped[str] = mapped_column(String, nullable=False, default="")
    day_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    week: Mapped[str] = mapped_column(String, nullable=False, default="")
    week_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("user_id", "song_id", name="uq_ur_user_song"),
        Index("idx_ur_user", "user_id"),
        Index("idx_ur_song", "song_id"),
    )


class PlayHistory(Base):
    """播放/选用历史（web 后台选用即写入一条）。"""

    __tablename__ = "play_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    song_id: Mapped[int] = mapped_column(Integer, ForeignKey("songs.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    note: Mapped[str] = mapped_column(String, nullable=False, default="")
    played_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)


class SongSelectedNotice(Base):
    """歌曲被选用后的待通知缓存。

    web 后台选用歌曲时写入（含该歌所有点歌用户），bot 定时任务逐用户私聊通知。
    ``failed_user_ids`` 记录本轮发送失败的用户（只重试失败者），``attempts`` 累计
    尝试轮次，达到上限后放弃并标记已发送，避免每周重复打扰已收到通知的用户。
    """

    __tablename__ = "song_selected_notice"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    song_id: Mapped[int] = mapped_column(Integer, ForeignKey("songs.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False, default="")
    artist: Mapped[str] = mapped_column(String, nullable=False, default="")
    selected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)
    user_ids: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    failed_user_ids: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    rejected_user_ids: Mapped[str] = mapped_column(
        String, nullable=False, default="[]", server_default="[]"
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
