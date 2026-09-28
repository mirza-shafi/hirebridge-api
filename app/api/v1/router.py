from fastapi import APIRouter

from app.api.v1.routes import (
    applications,
    files,
    health,
    jobs,
    me,
    resume_versions,
    resumes,
    runs,
    webhooks,
)

api_router = APIRouter()
api_router.include_router(me.router)
api_router.include_router(runs.router)
api_router.include_router(files.router)
api_router.include_router(resumes.router)
api_router.include_router(resume_versions.router)
api_router.include_router(jobs.router)
api_router.include_router(applications.router)
api_router.include_router(webhooks.router)

system_router = APIRouter()
system_router.include_router(health.router)
