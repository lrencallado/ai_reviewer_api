from fastapi import APIRouter, HTTPException, Security
from pydantic import BaseModel
from app.services.embedder import embed_text
from app.services.faiss_search import VectorSearch
from app.services.generator import generate_response
from typing import Annotated
from app.models import User
from app.dependencies import get_current_user
import json
import random

router = APIRouter(prefix="/reviewer", tags=["Reviewer"])

class QueryRequest(BaseModel):
    question: str

@router.post("/ask")
async def ask_question(
    current_user: Annotated[User, Security(get_current_user, scopes=["admin"])],
    payload: QueryRequest
):
    try:
        embedding = embed_text(payload.question)
        searcher = VectorSearch(dim=1536)
        relevant_chunks = searcher.search(embedding)
        answer = generate_response(payload.question, relevant_chunks)
        return {
            "answer": answer,
            "source": "reviewer" if relevant_chunks else "fallback",
            "context": relevant_chunks if relevant_chunks else None
        }
    except Exception as e:
        raise  HTTPException(status_code=500, detail=str(e))
    
@router.get("/mock")
async def get_mock_question(
    current_user: Annotated[User, Security(get_current_user, scopes=["admin"])],
    type:  str
):
    try:
        with open(f"chunks_{type}.json") as f:
            chunks = json.load(f)
        mocks = [c for c in chunks if isinstance(c, dict) and c.get("type") == "mock"]
        if not mocks:
            raise HTTPException(status_code=404, detail="No mock questions available")
        return random.choice(mocks)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))