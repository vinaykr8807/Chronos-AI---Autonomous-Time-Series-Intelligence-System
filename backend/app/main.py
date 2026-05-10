from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import settings
from app.services.dataset_store import DataSourceError

app = FastAPI(
    title="Autonomous Time-Series Intelligence API",
    version="0.1.0",
    description="Service-oriented backend for dataset discovery, EDA, adaptive ML pipelines, forecasting, and monitoring.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.exception_handler(DataSourceError)
async def datasource_error_handler(_: Request, exc: DataSourceError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "Autonomous Time-Series Intelligence API", "status": "online"}
