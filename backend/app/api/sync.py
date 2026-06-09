"""
POST /api/sync        — trigger full pipeline, stream progress via SSE
GET  /api/sync/status — last sync summary (for polling fallback)
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.api.deps import (
    get_db, get_crawler, get_classifier, get_extractor, get_rag_pipeline,
)
from app.config import settings
from app.crawler.base import ProgressEvent
from app.models.file_record import DownloadedFile, FileType

router = APIRouter(prefix="/api/sync", tags=["sync"])

# Simple in-memory last-sync summary (sufficient for this scope)
_last_sync: dict = {}


async def _run_pipeline(db: Session, queue: asyncio.Queue) -> None:
    """
    Full pipeline in order:
    1. Crawl   — download new files
    2. Classify — label each UNKNOWN file
    3. Extract  — extract statement data from capital_statements
    4. Ingest   — chunk + embed reports and statements into ChromaDB
    """
    async def emit(event: ProgressEvent) -> None:
        await queue.put({"event": event.type, "data": event.message})

    downloaded_ids: list[int] = []

    # ---- 1. Crawl --------------------------------------------------------
    crawler = get_crawler(db)
    original_sync = crawler.sync

    # Wrap sync so we capture newly downloaded file IDs
    async def tracked_sync(progress=None):
        result = await original_sync(progress=progress)
        return result

    crawl_result = await crawler.sync(progress=emit)
    await queue.put({"event": "info", "data": f"Crawl done: {crawl_result.downloaded} new, {crawl_result.skipped} skipped"})

    # ---- 2. Classify unknown files ----------------------------------------
    classifier = get_classifier()
    unknown_files = db.query(DownloadedFile).filter_by(file_type=FileType.UNKNOWN).all()
    await queue.put({"event": "info", "data": f"Classifying {len(unknown_files)} file(s)…"})

    for record in unknown_files:
        path = Path(record.file_path)
        try:
            result = await classifier.classify(
                file_path=path,
                filename=record.filename,
                portal_document_type=None,
            )
            record.file_type = result.file_type
            record.classifier_confidence = result.confidence
            db.commit()
            await queue.put({"event": "classified", "data": f"{record.filename} → {result.file_type.value} ({result.method}, conf={result.confidence:.2f})"})
        except Exception as exc:
            await queue.put({"event": "error", "data": f"Classify failed for {record.filename}: {exc}"})

    # ---- 3. Extract statements -------------------------------------------
    from app.models.statement import ExtractedStatement
    extractor = get_extractor()

    statements_to_extract = (
        db.query(DownloadedFile)
        .filter_by(file_type=FileType.CAPITAL_STATEMENT)
        .filter(~DownloadedFile.statements.any())  # not yet extracted
        .all()
    )
    await queue.put({"event": "info", "data": f"Extracting {len(statements_to_extract)} statement(s)…"})

    for record in statements_to_extract:
        path = Path(record.file_path)
        try:
            data = await extractor.extract(path)
            stmt = ExtractedStatement(
                file_id=record.id,
                fund_name=data.fund_name,
                statement_date=data.statement_date,
                current_value=data.current_value,
                raw_extracted_json=json.dumps(data.raw_fields),
            )
            db.add(stmt)
            db.commit()
            await queue.put({"event": "extracted", "data": f"{record.filename}: {data.fund_name} {data.statement_date} ${data.current_value:,.0f}" if data.current_value else f"{record.filename}: {data.fund_name} {data.statement_date}"})
        except Exception as exc:
            await queue.put({"event": "error", "data": f"Extract failed for {record.filename}: {exc}"})

    # ---- 4. Ingest into ChromaDB -----------------------------------------
    rag = get_rag_pipeline()
    files_to_ingest = (
        db.query(DownloadedFile)
        .filter(DownloadedFile.file_type.in_([FileType.REPORT, FileType.CAPITAL_STATEMENT]))
        .all()
    )
    await queue.put({"event": "info", "data": f"Ingesting {len(files_to_ingest)} file(s) into vector store…"})

    total_chunks = 0
    for record in files_to_ingest:
        path = Path(record.file_path)
        if not path.exists():
            continue
        try:
            meta = {
                "file_id": record.id,
                "filename": record.filename,
                "file_path": str(path),
                "doc_type": record.file_type.value,
            }
            added = await rag.ingest(path, meta)
            total_chunks += added
        except Exception as exc:
            await queue.put({"event": "error", "data": f"Ingest failed for {record.filename}: {exc}"})

    await queue.put({"event": "info", "data": f"Vector store updated: {total_chunks} new chunk(s)"})

    # ---- Done ------------------------------------------------------------
    summary = {
        "downloaded": crawl_result.downloaded,
        "skipped": crawl_result.skipped,
        "errors": crawl_result.errors,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _last_sync.update(summary)
    await queue.put({"event": "done", "data": json.dumps(summary)})
    await queue.put(None)  # sentinel


@router.post("")
async def trigger_sync(db: Session = Depends(get_db)):
    """
    Trigger full pipeline and stream progress as Server-Sent Events.
    The client reads the stream until it receives the 'done' event.
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def producer():
        try:
            await _run_pipeline(db, queue)
        except Exception as exc:
            await queue.put({"event": "error", "data": str(exc)})
            await queue.put(None)

    asyncio.create_task(producer())

    async def event_generator():
        while True:
            item = await queue.get()
            if item is None:
                break
            yield {"event": item["event"], "data": item["data"]}

    return EventSourceResponse(event_generator())


@router.get("/status")
async def sync_status():
    """Returns the summary from the last completed sync."""
    if not _last_sync:
        return {"synced": False}
    return {"synced": True, **_last_sync}
