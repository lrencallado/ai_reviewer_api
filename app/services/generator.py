from app.dependencies import get_openai_client
from app.main import settings

def generate_response(user_query: str, context_chunks: list):
    if context_chunks:
        context = "\n".join([c["content"] for c in context_chunks])
        prompt = f"""
You are an expert reviewer assistant for Medical Technologist Licensure Examination. Use the context below to answer the question.

Context:
{context}

Question:
{user_query}
"""
    else:
        prompt = f"""
The user asked: "{user_query}"

This topic wasn't found in the provided reviewer materials. Please provide a general explanation that could still be helful for Medical Technologist Licensure Examination.
"""
    client = get_openai_client()
    response = client.chat.completions.create(
        model=settings.gpt_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4
    )
    return response.choices[0].message.content.strip()