from fastapi import HTTPException, status

# ── Auth ────────────────────────────────────────────────────────────────────
CredentialsException = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

UserAlreadyExistsException = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="A user with this email already exists",
)

InvalidCredentialsException = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Incorrect email or password",
    headers={"WWW-Authenticate": "Bearer"},
)

# ── Resources ───────────────────────────────────────────────────────────────
UserNotFoundException = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="User not found",
)

ForbiddenException = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Not authorized to access this resource",
)

DocumentNotFoundException = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Document not found",
)
