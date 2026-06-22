import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "utils"))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from api.clients import router as clients_router
from api.process_reference_pack import router as reference_pack_router
from api.ideas import router as ideas_router
from api.scripts import router as scripts_router
from api.audio import router as audio_router
from db import create_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await create_pool()
    yield
    await app.state.pool.close()


app = FastAPI(title="Ad Agent API", lifespan=lifespan)

app.include_router(clients_router, prefix="/api")
app.include_router(reference_pack_router, prefix="/api")
app.include_router(ideas_router, prefix="/api")
app.include_router(scripts_router, prefix="/api")
app.include_router(audio_router, prefix="/api")
