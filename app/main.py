from fastapi import FastAPI
from app.routers import auth, reviewer, users, upload
from app.database import create_db_and_tables
from contextlib import asynccontextmanager
from . import config
from functools import lru_cache

app = FastAPI(title="AI Reviewer Assistant")

# Initialize database using lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()
    yield

@lru_cache
def get_settings():
    return config.Settings()

settings = get_settings()

app.router.lifespan_context = lifespan

@app.get("/")
async def root():
    return { "message": "Hello World" }

# Register routers
app.include_router(auth.router)
# app.include_router(seed.router)
app.include_router(users.router)
app.include_router(reviewer.router)
app.include_router(upload.router)
