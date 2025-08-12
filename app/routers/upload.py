# app/routers/upload.py
from fastapi import APIRouter, UploadFile, File, HTTPException
from PyPDF2 import PdfReader  # or PyPDF2/PdfReader depending on your package
import pdfplumber
from pdf2image import convert_from_path
import pytesseract
from PIL import Image
import json
import hashlib
import os
import re
import tempfile
import faiss
import numpy as np
from openai import OpenAI  # using the same client you already used elsewhere
from app.config import SETTINGS
from app.dependencies import get_openai_client

# Output files
CHUNKS_NLE_FILE = SETTINGS.chunks_path + "/chunks_nle.json"
INDEX_NLE_PATH = SETTINGS.index_path + "index_nle.faiss"

router = APIRouter(prefix="/upload", tags=["Upload PDF"])
openai_client = get_openai_client()

# ---------- Utilities ----------

def normalize_whitespace(text: str) -> str:
    """Normalize whitespace and fix common OCR artifacts."""
    if not text:
        return ""
    t = text.replace("\r", "\n")
    t = re.sub(r"\n{2,}", "\n\n", t)  # collapse multiple blank lines
    t = re.sub(r"[ \t]+", " ", t)     # collapse spaces
    return t.strip()

def save_uploaded_file_tmp(upload_file: UploadFile) -> str:
    """Save incoming UploadFile to a temporary path (returns path)."""
    suffix = os.path.splitext(upload_file.filename)[1] or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = upload_file.file.read()
        tmp.write(content)
        tmp_path = tmp.name
    return tmp_path

# ---------- Extraction strategies ----------

def is_text_pdf(path: str) -> bool:
    """
    Heuristic: try reading pages with pdfplumber or pypdf and see if there's meaningful text.
    If many pages have text -> treat as text-based.
    """
    try:
        with pdfplumber.open(path) as pdf:
            non_empty = 0
            pages = min(len(pdf.pages), 6)
            for i in range(pages):
                text = pdf.pages[i].extract_text() or ""
                if len(text.strip()) > 30:
                    non_empty += 1
            # if at least half of first pages contain text -> text-based pdf
            return non_empty >= max(1, pages // 2)
    except Exception:
        # fallback quick check with pypdf
        try:
            reader = PdfReader(path)
            non_empty = 0
            pages = min(len(reader.pages), 6)
            for i in range(pages):
                ptext = reader.pages[i].extract_text() or ""
                if len(ptext.strip()) > 30:
                    non_empty += 1
            return non_empty >= max(1, pages // 2)
        except Exception:
            return False

def extract_text_from_pdf(path: str) -> list[str]:
    """Extract per-page text using pdfplumber (best) or pypdf fallback."""
    texts = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                texts.append(page.extract_text() or "")
        return texts
    except Exception:
        reader = PdfReader(path)
        for page in reader.pages:
            texts.append(page.extract_text() or "")
        return texts

def extract_text_via_ocr(path: str, dpi: int = 200, lang: str = "eng") -> list[str]:
    """
    Convert each page to an image via pdf2image and run pytesseract OCR.
    Returns list of page texts.
    """
    texts = []
    # convert_from_path is CPU/memory heavy; keep DPI moderate
    images = convert_from_path(path, dpi=dpi)
    for img in images:
        # Optional: pre-process image (binarize, resize) for better OCR
        txt = pytesseract.image_to_string(img, lang=lang)
        texts.append(txt)
    return texts

# ---------- Parsers (transform) ----------

def parse_numbered_mcq_from_text(text: str) -> list[dict]:
    """
    Parse MCQs of this pattern (across multiple lines):
    1. Question text...
    A. option1
    B. option2
    C. option3
    D. option4
    Answer: B
    """
    results = []
    # Normalize quotes, replace weird hyphens, ensure consistent newlines
    t = normalize_whitespace(text)
    # Split into lines for scanning
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    q_re = re.compile(r"^(\d+)\.\s+(.*)")                   # "1. Question"
    opt_re = re.compile(r"^([A-Da-d])[\.\)]\s*(.*)")       # "A. Option" or "A) Option"
    ans_re = re.compile(r"^(?:Answer|ANS|Ans)[:\s]+(.+)", re.IGNORECASE)

    current = None
    for line in lines:
        qm = q_re.match(line)
        om = opt_re.match(line)
        am = ans_re.match(line)
        if qm:
            # push previous
            if current:
                results.append(current)
            current = {"question": qm.group(2).strip(), "options": [], "type": "mock", "exam_type": "NLE", "topic": "General Nursing"}
        elif om and current:
            current["options"].append(om.group(2).strip())
        elif am and current:
            # store answer as the full text or letter depending on format
            current["answer"] = am.group(1).strip()
        else:
            # maybe continuation of question text
            if current and not current.get("options"):
                current["question"] += " " + line
            # else ignore / treat as commentary
    if current:
        results.append(current)
    return results

def parse_inline_mcq(text: str) -> list[dict]:
    """
    Parse questions that are inline like:
    'What is ...? A. opt1 B. opt2 C. opt3 D. opt4 (Answer: B)'
    This is a simpler regex-based parser.
    """
    results = []
    t = normalize_whitespace(text)
    # Find question followed by options and optional answer in same block
    pattern = re.compile(
        r"(?P<q>[^A-D]+?)\s*(?:A[\.\)]\s*(?P<A>[^B]+?)\s*B[\.\)]\s*(?P<B>[^C]+?)\s*C[\.\)]\s*(?P<C>[^D]+?)\s*D[\.\)]\s*(?P<D>[^A]+?))(?:Answer[:\s]*(?P<ans>[A-Da-d]))?",
        re.DOTALL
    )
    for m in pattern.finditer(t):
        q = m.group("q").strip()
        opts = [m.group("A").strip(), m.group("B").strip(), m.group("C").strip(), m.group("D").strip()]
        ans = m.group("ans").strip() if m.group("ans") else None
        results.append({"question": q, "options": opts, "answer": ans, "type": "mock", "exam_type": "NLE", "topic": "General Nursing"})
    return results

# Fallback parser: if regex fails, use the AI to parse the block
def ai_parse_block_to_structured(block_text: str, openai_client: OpenAI) -> list[dict]:
    """
    Sends the block_text to OpenAI and requests structured JSON back.
    WARNING: costy for many pages — use as fallback.
    """
    prompt = f"""
You are a parser that converts unstructured nursing exam text into JSON.
Return a JSON array where each element is either:
- a mock (MCQ): {{ "type":"mock", "question": "...", "options": ["..."], "answer": "...", "topic": "..." }}
- or an ask chunk: {{ "type":"ask", "content":"...", "topic": "..." }}

Input text:
\"\"\"{block_text} \"\"\"

If no structured items are found return [].
"""
    # careful: batch blocks for fewer calls. Example uses Chat Completions or Responses API
    resp = openai_client.chat.completions.create(
        model="gpt-4o-mini",  # choose your available model
        messages=[
            {"role":"system", "content":"You are a strict JSON formatter."},
            {"role":"user", "content": prompt}
        ],
        temperature=0
    )
    text = resp.choices[0].message.content
    # Attempt to parse JSON out of response — guard aggressively
    try:
        # Try to extract JSON substring
        j = re.search(r"(\[.*\])", text, re.DOTALL)
        if j:
            data = json.loads(j.group(1))
            # normalize minimal fields
            out = []
            for item in data:
                if item.get("type") == "mock":
                    item.setdefault("exam_type", "NLE")
                    item.setdefault("topic", "General Nursing")
                else:
                    item.setdefault("type", "ask")
                    item.setdefault("exam_type", "NLE")
                    item.setdefault("topic", "General Nursing")
                out.append(item)
            return out
    except Exception:
        pass
    return []

# ---------- Chunk helpers & dedupe ----------
def add_hash_and_id(chunk: dict, exam_type: str = "NLE"):
    """Normalize chunk with id and hash fields."""
    if chunk.get("type") == "mock":
        base = chunk.get("question", "")
        content_for_hash = base
        chunk["id"] = chunk.get("id", f"{exam_type}-mock-{hashlib.sha256(content_for_hash.encode()).hexdigest()[:8]}")
    else:
        base = chunk.get("content", "")
        content_for_hash = base
        chunk["id"] = chunk.get("id", f"{exam_type}-ask-{hashlib.sha256(content_for_hash.encode()).hexdigest()[:8]}")
    chunk["hash"] = hashlib.sha256(content_for_hash.encode()).hexdigest()
    chunk.setdefault("exam_type", exam_type)
    chunk.setdefault("topic", chunk.get("topic", "General Nursing"))
    return chunk

def write_chunks_to_file(new_chunks: list, target_file: str = CHUNKS_NLE_FILE):
    """Append deduplicated chunks to target JSON file."""
    if not os.path.exists(target_file):
        with open(target_file, "w") as f:
            json.dump([], f)

    with open(target_file, "r") as f:
        existing = json.load(f)

    existing_hashes = {c.get("hash") for c in existing if isinstance(c, dict) and "hash" in c}
    added = 0
    for ch in new_chunks:
        if not isinstance(ch, dict):
            continue
        ch = add_hash_and_id(ch)
        if ch["hash"] not in existing_hashes:
            existing.append(ch)
            existing_hashes.add(ch["hash"])
            added += 1

    with open(target_file, "w") as f:
        json.dump(existing, f, indent=2)
    return added

# ---------- FAISS build function reuse ----------
def build_faiss_index(source_file: str = CHUNKS_NLE_FILE, index_path: str = INDEX_NLE_PATH):
    """
    Build FAISS index for 'ask' chunks only - reuse existing function or this version.
    """
    if not os.path.exists(source_file):
        return
    with open(source_file, "r") as f:
        chunks = json.load(f)
    texts = [c["content"] for c in chunks if isinstance(c, dict) and c.get("type") == "ask"]
    if not texts:
        return
    vectors = [openai_client.embeddings.create(input=text, model="text-embedding-ada-002").data[0].embedding for text in texts]
    dimension = len(vectors[0])
    index = faiss.IndexFlatL2(dimension)
    index.add(np.array(vectors).astype("float32"))
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    faiss.write_index(index, index_path)

# ---------- Main endpoint ----------

@router.post("/nle")
async def upload_nle_pdf(file: UploadFile = File(...), use_ai_fallback: bool = True):
    """
    Upload endpoint:
     - saves file to tmp
     - detects whether text-based or scanned
     - extracts page texts (or OCR)
     - runs parsers to produce structured chunks
     - optionally calls AI fallback for leftover big blocks
     - deduplicates and writes chunks_nle.json
     - builds FAISS index
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    tmp_path = save_uploaded_file_tmp(file)

    try:
        # 1) choose extraction strategy
        if is_text_pdf(tmp_path):
            page_texts = extract_text_from_pdf(tmp_path)
        else:
            page_texts = extract_text_via_ocr(tmp_path)

        # Normalize/page-wise
        page_texts = [normalize_whitespace(p) for p in page_texts if normalize_whitespace(p)]

        structured_chunks = []
        ai_client = openai_client if use_ai_fallback else None

        # 2) run parsers per page
        for page_text in page_texts:
            # Try number-based MCQ parser first
            mcqs = parse_numbered_mcq_from_text(page_text)
            if mcqs:
                structured_chunks.extend(mcqs)
                continue

            # Try inline MCQ parser
            inline = parse_inline_mcq(page_text)
            if inline:
                structured_chunks.extend(inline)
                continue

            # If no MCQ detected, treat as an 'ask' chunk (knowledge paragraph)
            # but also optionally run AI fallback for complex pages
            structured_chunks.append({"content": page_text, "type": "ask", "exam_type": "NLE", "topic": "General Nursing"})

            # optionally call ai fallback only if configured and if content is long/complex
            if use_ai_fallback and ai_client and len(page_text) > 800:  # tune threshold
                parsed_by_ai = ai_parse_block_to_structured(page_text, ai_client)
                if parsed_by_ai:
                    # replace the simple 'ask' with ai parsed items
                    structured_chunks.pop()  # remove last ask
                    structured_chunks.extend(parsed_by_ai)

        # 3) deduplicate and add
        added = write_chunks_to_file(structured_chunks, CHUNKS_NLE_FILE)

        # 4) rebuild faiss index (ask chunks)
        build_faiss_index(CHUNKS_NLE_FILE, INDEX_NLE_PATH)

        return {"message": f"Processed upload. chunks parsed: {len(structured_chunks)}, added: {added}"}

    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass
