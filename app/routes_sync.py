from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("/delta")
def run_delta_sync(request: Request, db: Session = Depends(get_db)):
    _ = request
    _ = db
    return {"ok": True, "listsSynced": 0, "tasksSynced": 0, "mode": "local-only"}
