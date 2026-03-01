from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/login")
def login(request: Request, db: Session = Depends(get_db)):
    _ = db
    request.session["ready"] = True
    return RedirectResponse(url="/")


@router.get("/callback")
def callback(
    request: Request,
    db: Session = Depends(get_db),
):
    _ = db
    request.session["ready"] = True
    return RedirectResponse(url="/")


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    _ = db
    request.session["ready"] = True
    return {
        "session": {
            "name": "",
            "email": "",
        },
        "graph": {"mode": "local-only"},
    }
