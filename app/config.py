import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = "text-embedding-3-small"
GPT_MODEL = os.getenv("GPT_MODEL")
INDEX_PATH = "faiss_index/"
CHUNKS_FILE = "app/data/chunks.json"
CHUNKS_PATH = "app/data/"
SECRET_KEY = os.getenv("SECRET_KEY", "super-secret")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES")
DATABASE_URL = os.getenv("DATABASE_URL")