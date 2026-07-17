from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings
from modules.activities.api.routes import router as activities_router
from modules.garmin_integration.api.routes import router as garmin_router

settings = get_settings()

app = FastAPI(title="Performance OS API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(garmin_router)
app.include_router(activities_router)


@app.get("/health")
def health():
    return {"status": "ok"}
