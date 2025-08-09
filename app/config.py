import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from functools import lru_cache

BASE_DIR = Path(__file__).resolve().parent

class Settings(BaseSettings):
    openai_api_key: str
    embedding_model: str = "text-embedding-3-small"
    gpt_model: str = "gpt-3.5-turbo"
    index_path: str = "faiss_index/"
    chunks_file: str = "app/data/chunks.json"
    chunks_path: str = "app/data/"
    secret_key: str = "super-secret"
    algorithm: str = "HS256"
    access_token_expires_minutes: int
    database_url: str
    model_config = SettingsConfigDict(env_file=".env")


@lru_cache
def get_settings():
    return Settings()

settings = get_settings()
