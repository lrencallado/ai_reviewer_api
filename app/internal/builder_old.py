import json
import numpy as np
import faiss
from app.services.embedder import embed_text
from app.config import settings

def build_faiss_index():
    with open(settings.chunks_file) as f:
        data = json.load(f)
        dim = 1536
        index = faiss.IndexFlatL2(dim)
        vectors = []

        for item in data:
            vec = embed_text(item["content"])
            vectors.append(vec)

        vectors_np = np.array(vectors).astype("float32")
        index.add(vectors_np)
        faiss.write_index(index, settings.index_path)
        print(f"Index written to {settings.index_path}")

if __name__ == "__main__":
    build_faiss_index()