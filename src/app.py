from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.routers.router import router
from src.tasks.broker import broker


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not broker.is_worker_process:
        await broker.startup()

    yield

    if not broker.is_worker_process:
        await broker.shutdown()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(router)
