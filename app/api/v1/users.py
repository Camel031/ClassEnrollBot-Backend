from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.security import get_password_hash
from app.schemas import UserOut, UserUpdate

router = APIRouter()


@router.get("/me", response_model=UserOut)
async def get_current_user_info(current_user: CurrentUser) -> UserOut:
    """Get current user information."""
    return current_user


@router.patch("/me", response_model=UserOut)
async def update_current_user(
    user_data: UserUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> UserOut:
    """Update current user information."""
    if user_data.email is not None:
        current_user.email = user_data.email

    if user_data.password is not None:
        current_user.hashed_password = get_password_hash(user_data.password)

    await db.flush()
    await db.refresh(current_user)

    return current_user
