from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from core.exceptions import InvalidCredentialsException, UserAlreadyExistsException
from core.security import create_access_token, hash_password, verify_password
from models.db.user import User
from models.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse


async def register_user(db: AsyncSession, data: RegisterRequest) -> UserResponse:
    """
    Create a new user account.

    Raises UserAlreadyExistsException if the email is already registered.
    Returns the newly created user as a UserResponse.
    """
    # 1. Check for duplicate email
    result = await db.execute(select(User).where(User.email == data.email))
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise UserAlreadyExistsException

    # 2. Create user row
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
    )
    db.add(user)
    await db.flush()   # writes to DB within transaction, assigns id + timestamps
    await db.refresh(user)

    return UserResponse.model_validate(user)


async def login_user(db: AsyncSession, data: LoginRequest) -> TokenResponse:
    """
    Authenticate a user and return a JWT access token.

    Raises InvalidCredentialsException for unknown email or wrong password.
    Deliberately uses the same exception for both cases to avoid user enumeration.
    """
    # 1. Look up by email
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    # 2. Verify password — constant-time comparison via passlib
    if user is None or not verify_password(data.password, user.password_hash):
        raise InvalidCredentialsException

    # 3. Issue token
    token = create_access_token({"sub": str(user.id)})
    expires_in_seconds = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    return TokenResponse(access_token=token, expires_in=expires_in_seconds)
