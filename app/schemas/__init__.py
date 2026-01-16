from app.schemas.user import (
    Token,
    TokenPayload,
    UserCreate,
    UserLogin,
    UserOut,
    UserUpdate,
)
from app.schemas.ntnu_account import (
    NTNUAccountCreate,
    NTNUAccountOut,
    NTNUAccountUpdate,
    NTNULoginRequest,
    NTNULoginResponse,
)
from app.schemas.course import (
    TrackedCourseCreate,
    TrackedCourseOut,
    TrackedCourseUpdate,
    CourseSearchResult,
)
from app.schemas.notification import NotificationOut

__all__ = [
    "Token",
    "TokenPayload",
    "UserCreate",
    "UserLogin",
    "UserOut",
    "UserUpdate",
    "NTNUAccountCreate",
    "NTNUAccountOut",
    "NTNUAccountUpdate",
    "NTNULoginRequest",
    "NTNULoginResponse",
    "TrackedCourseCreate",
    "TrackedCourseOut",
    "TrackedCourseUpdate",
    "CourseSearchResult",
    "NotificationOut",
]
