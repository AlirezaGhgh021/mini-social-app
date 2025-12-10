from fastapi import File, UploadFile, Form, Depends, FastAPI, HTTPException, Body

from app.schemas import PostCreate, PostResponse, UserCreate, UserUpdate, UserRead
from app.db import User, Post, create_db_and_tables, get_async_session, Like, Comment
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
from sqlalchemy import select, func
from app.images import imagekit
from imagekitio.models.UploadFileRequestOptions import UploadFileRequestOptions
import shutil
import os
from uuid import UUID
import tempfile
from app.users import auth_backend, current_active_user, fastapi_users
from typing import Optional
from sqlalchemy.orm import joinedload

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()
    yield


app = FastAPI(lifespan=lifespan)

app.include_router(fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"])
app.include_router(fastapi_users.get_register_router(UserRead, UserCreate), prefix='/auth', tags=["auth"])
app.include_router(fastapi_users.get_reset_password_router(), prefix='/auth', tags=["auth"])
app.include_router(fastapi_users.get_verify_router(UserRead), prefix='/auth', tags=["auth"])
app.include_router(fastapi_users.get_users_router(UserRead, UserUpdate), prefix='/users', tags=["users"])

@app.post('/upload')
async def upload_file(
        file: UploadFile = File(...),
        caption: str = Form(...),
        user: User = Depends(current_active_user),
        session: AsyncSession = Depends(get_async_session)
):
    temp_file_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
            temp_file_path = temp_file.name
            shutil.copyfileobj(file.file, temp_file)
        upload_result = imagekit.upload_file(
            file = open(temp_file_path, "rb"),
            file_name = file.filename,
            options= UploadFileRequestOptions(
                use_unique_file_name=True,
                tags=['backend-upload'],
                folder='/posts'
            )
        )

        if upload_result.response_metadata.http_status_code == 200:
            post = Post(
                user_id = user.id,
                caption=caption,
                url=upload_result.url,
                file_type='video' if file.content_type.startswith('video/') else 'image',
                file_name= upload_result.name
            )
            session.add(post)
            await session.commit()
            await session.refresh(post)
            return post
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)
        file.file.close()

optional_current_user = fastapi_users.current_user(active=True, optional=True)

@app.get('/feed')
async def get_feed(
        session: AsyncSession = Depends(get_async_session),
        user: Optional[User] = Depends(optional_current_user)
):
    # EAGER LOAD EVERYTHING — NO LAZY LOADING
    result = await session.execute(
        select(Post)
        .options(
            joinedload(Post.user),
            joinedload(Post.likes).joinedload(Like.user)
        )
        .order_by(Post.created_at.desc())
    )

    # THIS IS THE ONLY LINE THAT WORKS — .unique() IS REQUIRED
    posts = result.unique().scalars().all()

    posts_data = []
    for p in posts:
        posts_data.append({
            "id": str(p.id),
            "caption": p.caption or "",
            "url": p.url,
            "file_type": p.file_type,
            "file_name": p.file_name,
            "created_at": p.created_at.isoformat(),
            "is_owner": user is not None and p.user_id == user.id,
            "email": p.user.email.split("@")[0] if p.user else "unknown",
            "like_count": len(p.likes),
            "is_liked": user is not None and any(l.user_id == user.id for l in p.likes),
            "comments": []  # we'll add real comments next
        })

    return {"posts": posts_data}

@app.delete('/posts/{post_id}')
async def delete_post(
    post_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    user: User = Depends(current_active_user)
):
    result = await session.execute(select(Post).where(Post.id == post_id))
    post = result.scalars().first()

    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if post.user_id != user.id:
        raise HTTPException(status_code=403, detail="You do not have permission to perform this action")

    await session.delete(post)
    await session.commit()

    return {"success": True, "message": "Post deleted successfully"}

# ────────────────────── LIKE ENDPOINTS ──────────────────────
@app.post("/posts/{post_id}/like")
async def like_post(
    post_id: UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    # Check if post exists
    post = await session.get(Post, post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # Check if already liked
    existing = await session.execute(
        select(Like).where(Like.user_id == user.id, Like.post_id == post_id)
    )
    if existing.scalars().first():
        return {"detail": "Already liked"}

    like = Like(user_id=user.id, post_id=post_id)
    session.add(like)
    await session.commit()
    return {"detail": "Liked successfully"}


@app.delete("/posts/{post_id}/like")
async def unlike_post(
    post_id: UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    result = await session.execute(
        select(Like).where(Like.user_id == user.id, Like.post_id == post_id)
    )
    like = result.scalars().first()

    if not like:
        raise HTTPException(status_code=404, detail="Not liked yet")

    await session.delete(like)
    await session.commit()
    return {"detail": "Unliked"}

# ----------------comment endpoints
@app.post("/posts/{post_id}/comment")
async def add_comment(
    post_id: UUID,
    content: str = Body(..., embed=True),
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    post = await session.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Post not found")

    comment = Comment(post_id=post_id, user_id=user.id, content=content)
    session.add(comment)
    await session.commit()
    await session.refresh(comment)

    return {
        "id": str(comment.id),
        "content": comment.content,
        "user_email": user.email.split("@")[0],
        "created_at": comment.created_at.isoformat(),
        "is_owner": True
    }

@app.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: UUID,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session)
):
    comment = await session.get(Comment, comment_id)
    if not comment:
        raise HTTPException(404, "Comment not found")
    if comment.user_id != user.id:
        raise HTTPException(403, "Not your comment")

    await session.delete(comment)
    await session.commit()
    return {"detail": "Comment deleted"}