import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import load_config
from .state import AppState
from .routers import klipper, materials, quality_check, sensors


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()
    state = AppState(config)
    app.state.app_state = state
    async with state:
        yield


def create_app() -> FastAPI:
    app = FastAPI(title="HEPiC Device", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(klipper.router,        prefix="/api/klipper",   tags=["klipper"])
    app.include_router(materials.router,      prefix="/api/materials", tags=["materials"])
    app.include_router(quality_check.router,  prefix="/api/qc",        tags=["quality_check"])
    app.include_router(sensors.router,        prefix="/ws",            tags=["sensors"])
    return app


app = create_app()


def main():
    import argparse
    import os
    import uvicorn

    parser = argparse.ArgumentParser(description="HEPiC device backend")
    parser.add_argument("--mock", action="store_true", help="Use mock hardware workers (no Pi needed)")
    args = parser.parse_args()

    if args.mock:
        os.environ["HEPIC_MOCK"] = "1"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    uvicorn.run("device.backend.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
