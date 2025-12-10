# app/db.py

import uuid
from datetime import datetime
from collections.abc import AsyncGenerator

from fastapi import Depends
from fastapi_users.db import SQLAlchemyUserDatabase, SQLAlchemyBaseUserTableUUID
from sqlalchemy import (
    Column,
    Text,
    String,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.types import Uuid  # ← This is the universal UUID type


DATABASE_URL = "sqlite+aiosqlite:///./test.db"


class Base(DeclarativeBase):
    pass


# ────────────────────────── USER ──────────────────────────
class User(SQLAlchemyBaseUserTableUUID, Base):
    posts = relationship("Post", back_populates="user", cascade="all, delete-orphan")
    liked_posts = relationship("Like", back_populates="user")


# ────────────────────────── POST ──────────────────────────
class Post(Base):
    __tablename__ = "posts"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("user.id"), nullable=False)

    caption = Column(Text, nullable=True)
    url = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    user = relationship("User", back_populates="posts")
    likes = relationship("Like", back_populates="post")
    comments = relationship("Comment", back_populates="post", cascade="all, delete-orphan")

# ────────────────────────── LIKE ──────────────────────────
class Like(Base):
    __tablename__ = "likes"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(Uuid, ForeignKey("user.id"), nullable=False)
    post_id = Column(Uuid, ForeignKey("posts.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("user_id", "post_id", name="unique_like"),)

    user = relationship("User", back_populates="liked_posts")
    post = relationship("Post", back_populates="likes")

# ----------comments------------
class Comment(Base):
    __tablename__ = "comments"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    post_id = Column(Uuid, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Uuid, ForeignKey("user.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    post = relationship("Post", back_populates="comments")
# ──────────────────────── ENGINE & SESSION ────────────────────────
engine = create_async_engine(DATABASE_URL, connect_args={"check_same_thread": False})
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User)