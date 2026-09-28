from fastapi import APIRouter

from app.api.v1.routes import health, me, runs, webhooks

api_router = APIRouter()
api_router.include_router(me.router)
api_router.include_router(runs.router)
api_router.include_router(webhooks.router)

system_router = APIRouter()
system_router.include_router(health.router)
