from app.dependencies import get_openai_client
from app.config import EMBEDDING_MODEL

def embed_text(text: str):
    client = get_openai_client()
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=[text]
    )
    return response.data[0].embedding