from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.encryption import get_encryption
from app.db.models import NTNUAccount
from app.schemas import (
    NTNUAccountCreate,
    NTNUAccountOut,
    NTNUAccountUpdate,
    NTNULoginRequest,
    NTNULoginResponse,
)

router = APIRouter()


@router.get("", response_model=list[NTNUAccountOut])
async def list_ntnu_accounts(
    current_user: CurrentUser,
    db: DbSession,
) -> list[NTNUAccount]:
    """List all NTNU accounts for the current user."""
    result = await db.execute(
        select(NTNUAccount).where(NTNUAccount.user_id == current_user.id)
    )
    return list(result.scalars().all())


@router.post("", response_model=NTNUAccountOut, status_code=status.HTTP_201_CREATED)
async def create_ntnu_account(
    account_data: NTNUAccountCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> NTNUAccount:
    """Create a new NTNU account."""
    # Check if student_id already exists for this user
    result = await db.execute(
        select(NTNUAccount).where(
            NTNUAccount.user_id == current_user.id,
            NTNUAccount.student_id == account_data.student_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This student ID is already registered",
        )

    # Encrypt password
    encryption = get_encryption()
    encrypted_password = encryption.encrypt(account_data.password)

    # Create account
    account = NTNUAccount(
        user_id=current_user.id,
        student_id=account_data.student_id,
        encrypted_password=encrypted_password,
    )
    db.add(account)
    await db.flush()
    await db.refresh(account)

    return account


@router.get("/{account_id}", response_model=NTNUAccountOut)
async def get_ntnu_account(
    account_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> NTNUAccount:
    """Get a specific NTNU account."""
    result = await db.execute(
        select(NTNUAccount).where(
            NTNUAccount.id == account_id,
            NTNUAccount.user_id == current_user.id,
        )
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="NTNU account not found",
        )

    return account


@router.patch("/{account_id}", response_model=NTNUAccountOut)
async def update_ntnu_account(
    account_id: UUID,
    account_data: NTNUAccountUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> NTNUAccount:
    """Update an NTNU account."""
    result = await db.execute(
        select(NTNUAccount).where(
            NTNUAccount.id == account_id,
            NTNUAccount.user_id == current_user.id,
        )
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="NTNU account not found",
        )

    if account_data.password is not None:
        encryption = get_encryption()
        account.encrypted_password = encryption.encrypt(account_data.password)

    if account_data.is_active is not None:
        account.is_active = account_data.is_active

    await db.flush()
    await db.refresh(account)

    return account


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ntnu_account(
    account_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Delete an NTNU account."""
    result = await db.execute(
        select(NTNUAccount).where(
            NTNUAccount.id == account_id,
            NTNUAccount.user_id == current_user.id,
        )
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="NTNU account not found",
        )

    await db.delete(account)


@router.post("/{account_id}/login", response_model=NTNULoginResponse)
async def login_to_ntnu(
    account_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """Login to NTNU system using stored credentials."""
    from datetime import datetime, timedelta

    from app.core.encryption import get_encryption
    from app.core.exceptions import NTNULoginError
    from app.services.ntnu_browser_client import NTNUBrowserClient

    result = await db.execute(
        select(NTNUAccount).where(
            NTNUAccount.id == account_id,
            NTNUAccount.user_id == current_user.id,
        )
    )
    account = result.scalar_one_or_none()

    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="NTNU account not found",
        )

    # Decrypt password
    encryption = get_encryption()
    try:
        password = encryption.decrypt(account.encrypted_password)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to decrypt password",
        )

    # Attempt login using browser client
    browser_client = NTNUBrowserClient(account_id)
    try:
        login_result = await browser_client.login(
            student_id=account.student_id,
            password=password,
        )

        # Update last login time
        account.last_login_at = datetime.utcnow()
        await db.flush()

        # Session typically valid for ~30 minutes
        session_valid_until = datetime.utcnow() + timedelta(minutes=30)

        return {
            "success": True,
            "message": "Login successful",
            "session_valid_until": session_valid_until.isoformat(),
        }

    except NTNULoginError as e:
        return {
            "success": False,
            "message": str(e),
            "session_valid_until": None,
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Login failed: {str(e)}",
            "session_valid_until": None,
        }
    finally:
        await browser_client.close()
