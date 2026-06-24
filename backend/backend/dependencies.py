import uuid

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import CredentialsException, ForbiddenException
from core.security import decode_access_token
from db.session import get_db
from models.db.user import User

# tokenUrl must point to an endpoint that accepts application/x-www-form-urlencoded
# with "username" and "password" fields — that is what Swagger's Authorize popup sends.
# /api/auth/token is that endpoint; /api/auth/login keeps accepting JSON for the frontend.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Decode the JWT, look up the user in PostgreSQL, and return the ORM object.
    Raises 401 if the token is invalid or the user row is not found.
    """
    try:
        payload = decode_access_token(token)
        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            raise CredentialsException
        user_id = uuid.UUID(user_id_str)
    except (ValueError, AttributeError):
        raise CredentialsException

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise CredentialsException

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Extends get_current_user by verifying the account is active.
    Raises 403 for deactivated accounts.
    """
    if not current_user.is_active:
        raise ForbiddenException
    return current_user
