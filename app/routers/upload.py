from fastapi import APIRouter, UploadFile, File, HTTPException
from PyPDF2 import PdfReader
import json
import hashlib
import os
import re
import faiss
import numpy as np
from app.config import CHUNKS_PATH, EMBEDDING_MODEL, INDEX_PATH
from app.dependencies import get_openai_client

router = APIRouter(prefix="/upload", tags=["Upload PDF"])

def parse_pdf(file: UploadFile) -> list:
    reader = PdfReader(file.file)
    pages = [page.extract_text() for page in reader.pages]
    return [chunk.strip() for page in pages for chunk in page.split("\n\n") if chunk.strip()]

def extract_mock_questions(chunks: list) -> list:
    mock_items = []
    q_pattern = re.compile(r"^\d+\.\s+(.*)")
    option_pattern = re.compile(r"^([A-Da-d])\.\s+(.*)")

    current_question = None

    for line in chunks:
        q_match = q_pattern.match(line)
        o_match = option_pattern.match(line)

        if q_match:
            if current_question:
                mock_items.append(current_question)
            current_question = {
                "question": q_match.group(1),
                "options": [],
                "type": "mock",
                "exam_type": "NLE"
            }
        elif o_match and current_question:
            current_question["options"].append(f"{o_match.group(1)}. {o_match.group(2)}")

    if current_question:
        mock_items.append(current_question)

    return mock_items

def deduplicate_and_add(new_chunks: list, chunk_type: str, exam_type: str, target_file: str):
    if not os.path.exists(target_file):
        with open(target_file, "w") as f:
            json.dump([], f)

    with open(target_file, "r") as f:
        existing_chunks = json.load(f)

    existing_set = {chunk.get("hash") for chunk in existing_chunks if isinstance(chunk, dict) and "hash" in chunk}

    for chunk in new_chunks:
        if not isinstance(chunk, dict):
            base_content = chunk
            is_mock = False
        elif chunk.get("type") == "mock":
            base_content = chunk["question"]
            is_mock = True
        else:
            base_content = chunk["content"] if "content" in chunk else chunk
            is_mock = False

        content_hash = hashlib.sha256(base_content.encode()).hexdigest()
        if content_hash not in existing_set:
            if is_mock:
                chunk["id"] = f"{exam_type}-mock-{content_hash[:8]}"
                chunk["hash"] = content_hash
                entry = chunk
            else:
                entry = {
                    "id": f"{exam_type}-ask-{content_hash[:8]}",
                    "content": base_content,
                    "type": "ask",
                    "exam_type": exam_type,
                    "hash": content_hash
                }
            existing_chunks.append(entry)

    with open(target_file, "w") as f:
        json.dump(existing_chunks, f, indent=2)

def build_faiss_index(source_file: str, index_path: str):
    with open(source_file) as f:
        chunks = json.load(f)

    texts = [c["content"] for c in chunks if c.get("type") == "ask"]
    if not texts:
        return

    openai = get_openai_client()
    vectors = [openai.embeddings.create(input=text, model=EMBEDDING_MODEL).data[0].embedding for text in texts]

    dimension = len(vectors[0])
    index = faiss.IndexFlatL2(dimension)
    index.add(np.array(vectors).astype("float32"))

    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    faiss.write_index(index, index_path)

@router.post("/nle")
async def upload_nle_pdf(
    file: UploadFile = File(...),
    chunk_type: str = None
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    parsed_chunks = parse_pdf(file)
    chunks_nle_file = CHUNKS_PATH + "chunks_nle.json"
    faiss_index_filename = "index_nle.faiss"

    if not chunk_type:
        mock_chunks = extract_mock_questions(parsed_chunks)
        ask_chunks = [c for c in parsed_chunks if not any(c.startswith(f"{i}.") for i in range(1, 1000))]
        deduplicate_and_add(mock_chunks, chunk_type="mock", exam_type="NLE", target_file=chunks_nle_file)
        deduplicate_and_add(ask_chunks, chunk_type="ask", exam_type="NLE", target_file=chunks_nle_file)
    else:
        structured = extract_mock_questions(parsed_chunks) if chunk_type == "mock" else parsed_chunks
        deduplicate_and_add(structured, chunk_type=chunk_type, exam_type="NLE", target_file=chunks_nle_file)

    build_faiss_index(chunks_nle_file, INDEX_PATH + faiss_index_filename)

    return {"message": f"Uploaded and indexed chunks to {chunks_nle_file}"}