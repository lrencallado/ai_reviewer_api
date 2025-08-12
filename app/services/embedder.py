from app.dependencies import get_openai_client
from app.config import SETTINGS

def embed_text(text: str):
    client = get_openai_client()
    response = client.embeddings.create(
        model=SETTINGS.embedding_model,
        input=[text]
    )
    return response.data[0].embedding