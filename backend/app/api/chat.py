"""
POST /api/chat  — ask a question over the ingested document corpus
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_rag_pipeline
from app.rag.pipeline import RAGPipeline

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    question: str
    n_results: int = 8


@router.post("")
async def chat(request: ChatRequest, rag: RAGPipeline = Depends(get_rag_pipeline)):
    response = await rag.query(request.question, n_results=request.n_results)
    return {
        "answer": response.answer,
        "is_out_of_corpus": response.is_out_of_corpus,
        "citations": [
            {
                "filename": c.filename,
                "page": c.page,
                "period": c.period,
                "fund_name": c.fund_name,
                "chunk_text": c.chunk_text,
                "file_path": c.file_path,
            }
            for c in response.citations
        ],
    }
