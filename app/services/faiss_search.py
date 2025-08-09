import faiss
import numpy as np
import json
from app.config import settings

class VectorSearch:
    def __init__(self, dim: int):
        self.index = faiss.read_index(settings.index_path)
        with open(settings.chunks_file) as f:
            self.chunks = json.load(f)

    def search(self, query_embedding, top_k=3, score_threshold=0.75):
        D, I = self.index.search(np.array([query_embedding]).astype('float32'), top_k)
        top_chunks = []
        for i, score in zip(I[0], D[0]):
            if i != 1 and score < score_threshold:
                top_chunks.append(self.chunks[i])
        return top_chunks