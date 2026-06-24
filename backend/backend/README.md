# AskMyDocs — Backend (Phase 1A: Authentication)

FastAPI backend with JWT authentication. Three endpoints working in Postman.

## Prerequisites

- Python 3.12+
- PostgreSQL 14+ running locally (or via Docker)

## Quick Start

### 1. Create and activate a virtual environment

```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Create your database

```bash
# If using psql directly:
psql -U postgres -c "CREATE DATABASE askmydocs;"
```

### 4. Configure environment

```bash
cp .env.example .env
```

Open `.env` and set these three required values:

```env
DATABASE_URL=postgresql+asyncpg://postgres:yourpassword@localhost:5432/askmydocs
SECRET_KEY=generate-with-python-c-import-secrets-print-secrets-token-hex-32
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

Generate a real SECRET_KEY:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 5. Run database migrations

```bash
alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, create users table
```

### 6. Start the server

```bash
uvicorn main:app --reload --port 8000
```

Server is running at: http://localhost:8000
Interactive docs at: http://localhost:8000/docs

---

## Testing in Postman

### Register

```
POST  http://localhost:8000/api/auth/register
Content-Type: application/json

{
    "email": "test@example.com",
    "password": "secret123",
    "full_name": "Test User"
}
```

Expected response `201`:
```json
{
    "id": "uuid-here",
    "email": "test@example.com",
    "full_name": "Test User",
    "is_active": true,
    "created_at": "2025-01-01T00:00:00Z"
}
```

---

### Login

```
POST  http://localhost:8000/api/auth/login
Content-Type: application/json

{
    "email": "test@example.com",
    "password": "secret123"
}
```

Expected response `200`:
```json
{
    "access_token": "eyJ...",
    "token_type": "bearer",
    "expires_in": 3600
}
```

Copy the `access_token` value.

---

### Get current user (/me)

```
GET   http://localhost:8000/api/auth/me
Authorization: Bearer eyJ...    ← paste your token here
```

Expected response `200`:
```json
{
    "id": "uuid-here",
    "email": "test@example.com",
    "full_name": "Test User",
    "is_active": true,
    "created_at": "2025-01-01T00:00:00Z"
}
```

---

### Logout

```
POST  http://localhost:8000/api/auth/logout
Authorization: Bearer eyJ...
```

Expected response `200`:
```json
{ "message": "Successfully logged out" }
```

---

## Error Cases to Verify

| Request | Expected |
|---|---|
| Register same email twice | `400 A user with this email already exists` |
| Register with 7-char password | `422 Password must be at least 8 characters` |
| Register with no digit in password | `422 Password must contain at least one digit` |
| Login with wrong password | `401 Incorrect email or password` |
| GET /me with no Authorization header | `401 Not authenticated` |
| GET /me with garbage token | `401 Could not validate credentials` |

---

## Project Structure

```
backend/
├── main.py                  ← FastAPI app factory
├── config.py                ← Pydantic settings (reads .env)
├── dependencies.py          ← get_current_user, get_current_active_user
├── requirements.txt
├── alembic.ini
├── .env.example
│
├── api/
│   └── auth.py              ← Route handlers: register, login, logout, me
│
├── services/
│   └── auth_service.py      ← register_user(), login_user() business logic
│
├── models/
│   ├── db/
│   │   ├── base.py          ← Base, UUIDPrimaryKeyMixin, TimestampMixin
│   │   └── user.py          ← User ORM model
│   └── schemas/
│       └── auth.py          ← Pydantic request/response schemas
│
├── core/
│   ├── security.py          ← hash_password, verify_password, JWT encode/decode
│   └── exceptions.py        ← Named HTTP exceptions
│
└── db/
    ├── session.py           ← Async engine, session factory, get_db dependency
    └── migrations/
        ├── env.py           ← Alembic async config
        └── versions/
            └── 0001_create_users_table.py
```
