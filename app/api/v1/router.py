from fastapi import APIRouter

from app.api.v1 import auth, users, ntnu_accounts, courses, notifications

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(ntnu_accounts.router, prefix="/ntnu-accounts", tags=["NTNU Accounts"])
api_router.include_router(courses.router, prefix="/courses", tags=["Courses"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
