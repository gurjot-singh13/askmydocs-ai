from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from dependencies import get_current_active_user
from models.db.user import User
from models.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from services import auth_service

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(
    data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """
    Create a new account.

    - **email**: must be a valid email address and unique
    - **password**: minimum 8 characters, must contain at least one digit
    - **full_name**: optional display name
    """
    return await auth_service.register_user(db, data)


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate via JSON — use this from Postman or the frontend",
)
async def login(
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Exchange email + password (JSON body) for a JWT access token.

    This endpoint accepts **application/json** and is intended for the
    frontend and Postman.  Swagger UI's **Authorize** button requires a
    form-encoded endpoint — use ``POST /api/auth/token`` for that.
    """
    return await auth_service.login_user(db, data)


@router.post(
    "/token",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Swagger Authorize — OAuth2 form-encoded login",
    include_in_schema=True,
)
async def token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    OAuth2-compatible token endpoint used exclusively by **Swagger UI**.

    Swagger's **Authorize** popup sends credentials as
    ``application/x-www-form-urlencoded`` with ``username`` and ``password``
    fields (OAuth2 spec).  This endpoint accepts that format and delegates to
    the same ``login_user`` service as the JSON ``/login`` endpoint.

    The ``username`` field is treated as the user's email address.
    """
    login_data = LoginRequest(email=form_data.username, password=form_data.password)
    return await auth_service.login_user(db, login_data)


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Invalidate the current session (client-side)",
)
async def logout(
    _current_user: User = Depends(get_current_active_user),
) -> dict:
    """
    Signal a logout.

    In this MVP, tokens are stateless — there is no server-side token store to
    invalidate.  The client must discard the token after calling this endpoint.
    """
    return {"message": "Successfully logged out"}


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Return the authenticated user's profile",
)
async def me(
    current_user: User = Depends(get_current_active_user),
) -> UserResponse:
    """
    Return the profile of the currently authenticated user.
    Requires a valid ``Authorization: Bearer <token>`` header.
    """
    return UserResponse.model_validate(current_user)
