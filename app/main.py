from fastapi import FastAPI
from app.routes import router

app = FastAPI(
    title="Ventusky Forecast API",
    description="API de pronóstico meteorológico basada en Ventusky.",
    version="1.0.0",
)

app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok"}
