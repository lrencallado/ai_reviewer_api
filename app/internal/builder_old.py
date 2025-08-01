import json
import numpy as np
import faiss
from app.services.embedder import embed_text
from app.config import CHUNKS_FILE, INDEX_PATH

def build_faiss_index():
    with open(CHUNKS_FILE) as f:
        data = json.load(f)
        dim = 1536
        index = faiss.IndexFlatL2(dim)
        vectors = []

        for item in data:
            vec = embed_text(item["content"])
            vectors.append(vec)

        vectors_np = np.array(vectors).astype("float32")
        index.add(vectors_np)
        faiss.write_index(index, INDEX_PATH)
        print(f"Index written to {INDEX_PATH}")

if __name__ == "__main__":
    build_faiss_index()