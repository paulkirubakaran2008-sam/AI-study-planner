import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from . import models  # noqa: F401  (register tables)
from .config import get_settings
from .database import Base, SessionLocal, engine
from .routers import auth, insights, planner as planner_router, subjects
from .services import demo_service

settings = get_settings()
logging.basicConfig(level=logging.INFO if settings.is_production else logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("study-planner")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate_for_runtime()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        demo_service.purge_old_demos(db)
    log.info("Started (env=%s, db=%s, ai=%s)", settings.environment, engine.dialect.name, "on" if settings.ai_api_key else "off")
    yield


app = FastAPI(title="AI Study Planner API", version="1.0.0", lifespan=lifespan,
              docs_url=None if settings.is_production else "/docs", redoc_url=None, openapi_url=None if settings.is_production else "/openapi.json")

app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=False, allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                   allow_headers=["Authorization", "Content-Type"], max_age=600)


@app.middleware("http")
async def limit_body(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > settings.max_request_bytes:
        return JSONResponse({"detail": "Request too large"}, status_code=413)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    first = exc.errors()[0]
    field = ".".join(str(p) for p in first["loc"] if p not in ("body", "query"))
    return JSONResponse({"detail": f"{field}: {first['msg']}" if field else first["msg"]}, status_code=422)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error: %s", exc)
    headers = {}
    origin = request.headers.get("origin", "").rstrip("/")
    if origin in settings.cors_list:        # error responses bypass CORSMiddleware, so add the header ourselves
        headers = {"Access-Control-Allow-Origin": origin, "Vary": "Origin"}
    return JSONResponse({"detail": "Something went wrong on our side. Please try again."}, status_code=500, headers=headers)


@app.get("/health")
def health():
    with engine.connect() as c:
        c.execute(text("SELECT 1"))
    return {"status": "ok", "ai": bool(settings.ai_api_key)}


for r in (auth.router, subjects.router, planner_router.router, insights.router):
    app.include_router(r)
