"""
GET /api/files          — all downloaded files
GET /api/files/{id}     — single file metadata
GET /api/files/{id}/open — redirect to the raw file for download
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.file_record import DownloadedFile

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("")
def list_files(db: Session = Depends(get_db)):
    files = db.query(DownloadedFile).order_by(DownloadedFile.download_date.desc()).all()
    return [_serialize(f) for f in files]


@router.get("/{file_id}")
def get_file(file_id: int, db: Session = Depends(get_db)):
    f = db.get(DownloadedFile, file_id)
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    return _serialize(f)


@router.get("/{file_id}/open")
def open_file(file_id: int, db: Session = Depends(get_db)):
    """Serve the raw PDF so the frontend can open/download it."""
    f = db.get(DownloadedFile, file_id)
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    path = Path(f.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not on disk")
    return FileResponse(path=str(path), filename=f.filename, media_type="application/pdf")


def _serialize(f: DownloadedFile) -> dict:
    return {
        "id": f.id,
        "portal_file_id": f.portal_file_id,
        "filename": f.filename,
        "deal_name": f.deal_name,
        "file_type": f.file_type.value,
        "classifier_confidence": f.classifier_confidence,
        "download_date": f.download_date.isoformat() if f.download_date else None,
    }
