"""统一数据库层：SQLAlchemy 连接工厂 + ORM 模型。

两端（bot 点歌插件 / web 管理后台）共用同一套表结构，通过环境变量
``DATABASE_URL`` 切换数据库：

- 缺省（未设置 ``DATABASE_URL``）：本地 SQLite ``data/song_requests.db``，零配置。
- PostgreSQL：``DATABASE_URL=postgresql+psycopg://user:pass@host:port/dbname``。

说明：
- 迁移时保留了既有 SQLite 库的全部在用表（songs / users / user_requests /
  play_history）。历史遗留的 ``song_requests`` 表（仅剩残留唯一索引、无任何代码使用）
  不纳入模型，避免造成困惑。
- 使用 SQLAlchemy 2.0 声明式映射；写库时调用方用 ``with SessionLocal() as s:``，读库用
  ``conn.execute(...)``（``engine`` 为同步连接，兼容现有 FastAPI/NoneBot2 同步代码）。
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

_ROOT = Path(__file__).resolve().parent
_DEFAULT_URL = f"sqlite:///{(_ROOT / 'data' / 'song_requests.db').as_posix()}"

# DATABASE_URL 可直接由环境变量给出；SQLite 场景常需要把 Windows 绝对路径写成
# sqlite:///D:/path/to.db，这里仅在未设置时给默认值。
DATABASE_URL = os.environ.get("DATABASE_URL") or _DEFAULT_URL

# SQLite 需要关闭同线程检查（NoneBot/FastAPI 都在各自的线程/事件循环里用）。
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    connect_args=_connect_args,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Song(Base):
    """歌曲库。``selected`` 为 web 后台「选用」标记（1=已选用，0=待选用）。"""

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
    created_at: Mapped[str] = mapped_column(String, nullable=False, default="")
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_songs_source_srcid"),)


class User(Base):
    """点歌用户。``is_banned`` 为封禁标记。"""

    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    is_banned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False, default="")


class UserRequest(Base):
    """用户点歌记录。同一用户对同一首歌仅一条，重复点歌更新时间为当前（置顶）。"""

    __tablename__ = "user_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    song_id: Mapped[int] = mapped_column(Integer, ForeignKey("songs.id"), nullable=False)
    time: Mapped[str] = mapped_column(String, nullable=False, default="")
    remark: Mapped[str] = mapped_column(String, nullable=False, default="")
    day: Mapped[str] = mapped_column(String, nullable=False, default="")
    day_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

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
    played_at: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String, nullable=False, default="")


class SongSelectedNotice(Base):
    """歌曲被选用后的待通知缓存。

    web 后台选用一首歌时写入一条（含该歌所有点歌用户），bot 定时任务读取未发送
    的记录，逐用户私聊通知后标记 sent=1。这样“被选用”与“发送”解耦：先缓存，后续
    由定时任务批量发送。
    """

    __tablename__ = "song_selected_notice"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    song_id: Mapped[int] = mapped_column(Integer, ForeignKey("songs.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False, default="")
    artist: Mapped[str] = mapped_column(String, nullable=False, default="")
    selected_at: Mapped[str] = mapped_column(String, nullable=False, default="")
    user_ids: Mapped[str] = mapped_column(String, nullable=False, default="[]")
    sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sent_at: Mapped[str] = mapped_column(String, nullable=False, default="")


def init_db() -> None:
    """按模型建表（幂等）。首次连接（PG）或本地首次使用会创建缺失表。"""
    Base.metadata.create_all(bind=engine)


def ping() -> str:
    """探测连接是否可用；返回数据库库名，便于排查是否用了正确的库。"""
    with engine.connect() as conn:
        # current_database() 是 PG 函数，SQLite 没有；用方言判断，跨库安全。
        if engine.dialect.name == "postgresql":
            return conn.execute(text("SELECT current_database()")).scalar() or "connected"
        # SQLite：返回文件路径作为标识
        return str(engine.url.database) if engine.url.database else "sqlite-memory"
