from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.db import Base, engine
from app.routes_epic import router as epic_router
from app.routes_event import router as event_router
from app.routes_todo import router as todo_router
from app.routes_trigger import router as trigger_router
from app.trigger_engine import TriggerEngine

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)

    trigger_engine = TriggerEngine(interval_seconds=settings.trigger_engine_interval_seconds)
    trigger_engine.start()
    app.state.trigger_engine = trigger_engine

    try:
        yield
    finally:
        trigger_engine.shutdown()


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    session_cookie=settings.session_cookie_name,
    https_only=not settings.debug,
    same_site="lax",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(epic_router)
app.include_router(event_router)
app.include_router(todo_router)
app.include_router(trigger_router)


@app.get("/api/health")
def health():
    return {"ok": True}


frontend_dir = Path(settings.frontend_dir)
assets_dir = frontend_dir / "assets"
if assets_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")


@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    if full_path.startswith("api/"):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    index_html = frontend_dir / "index.html"
    if index_html.exists():
        return FileResponse(index_html)
    return JSONResponse(
        status_code=503,
        content={"detail": "Frontend build not found. Run frontend build and restart the server."},
    )
