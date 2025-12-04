from fastapi import File, UploadFile, Form, Depends, FastAPI, HTTPException

from app.schemas import PostCreate, PostResponse
from app.db import Post, create_db_and_tables, get_async_session
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
from sqlalchemy import select
from app.images import imagekit
from imagekitio.models.UploadFileRequestOptions import UploadFileRequestOptions
import shutil
import os
import uuid
import tempfile

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()
    yield


app = FastAPI(lifespan=lifespan)

@app.post('/upload')
async def upload_file(
        file: UploadFile = File(...),
        caption: str = Form(...),
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

@app.get('/feed')
async def get_feed(
        session: AsyncSession = Depends(get_async_session)
):
    result = await session.execute(select(Post).order_by(Post.created_at.desc()))
    posts = [row[0] for row in result.all()]

    posts_data = []
    for post in posts:
        posts_data.append(
            {
                'id': str(post.id),
                'caption': post.caption,
                'url': post.url,
                'file_type': post.file_type,
                'file_name': post.file_name,
                'created_at': post.created_at.isoformat()
            }
        )
    return {'posts': posts_data}

# text_posts = {
#     1: {"title": "First post ever", "content": "Finally launched my mini social app!"},
#     2: {"title": "Morning vibes", "content": "Coffee in one hand, FastAPI in the other"},
#     3: {"title": "Just shipped", "content": "My backend is now live and running"},
#     4: {"title": "Late night coding", "content": "Sleep is for people without deadlines"},
#     5: {"title": "Learning in public", "content": "Building a social app from scratch, one endpoint at a time"},
#     6: {"title": "FastAPI is love", "content": "This framework makes backend development actually fun"},
#     7: {"title": "Hello world", "content": "Officially joining the dev community today"},
#     8: {"title": "Weekend project", "content": "Turned an idea into a working API in 48 hours"},
#     9: {"title": "Feeling proud", "content": "From zero to a working social platform"},
#     10: {"title": "Next step", "content": "Adding likes and comments tomorrow"}
# }

@app.get('/posts')
def get_all_posts(limit: int = None):
    if limit:
        return list(text_posts.values())[:limit]
    return text_posts

@app.get('/posts/{id}')
def get_post(id: int):
    if id not in text_posts:
        raise HTTPException(status_code=404, detail='post not found')
    return text_posts.get(id)

@app.post('/posts')
def create_post(post: PostCreate) -> PostResponse:
    new_post = {'title': post.title, 'content': post.content}
    text_posts[max(text_posts.keys()) + 1] = new_post
    return new_post

