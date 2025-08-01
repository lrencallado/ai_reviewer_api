import json
from app.routers.upload import build_faiss_index

if __name__ == "__main__":
    build_faiss_index("chunks_nle.json", "faiss_index/index_nle.faiss")
    print("FAISS index built for NLE chunks.")