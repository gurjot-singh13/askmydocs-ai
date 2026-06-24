# AskMyDocs AI — MVP Architecture & Phase 1 Implementation Plan

> Lean MVP: no background queues, no cache layer, no observability stack.
> Every layer is synchronous and deployable with a single `docker compose up`.

---

## MVP Scope Decisions

| Removed | Replacement / Reason |
|---|---|
| Celery | Ingestion runs synchronously inside the upload request |
| Redis | No queue needed; no rate limiter in MVP |
| Prometheus + Grafana | Python `logging` to stdout is sufficient for MVP |
| Sentry | Unhandled exceptions logged via FastAPI exception handlers |
| Refresh tokens | Single JWT access token; re-login on expiry (simpler auth) |

| Kept | Purpose |
|---|---|
| FastAPI | Async API server |
| PostgreSQL | Relational metadata, conversations, citations |
| Qdrant | Dense vector storage with payload filtering |
| Gemini 2.5 Flash | Answer generation + streaming |
| text-embedding-004 | 768-dim document + query embeddings |
| LangChain | Chain orchestration, prompt templating |
| BM25 (rank_bm25) | Keyword retrieval leg of hybrid search |
| RRF | Score-agnostic fusion of vector + BM25 results |
| Citations | Structural marker-based citation with file + chunk source |

---

## MVP Request Flows

### Upload flow (synchronous)

```
POST /api/documents/upload
  → JWT verify
  → save file to ./uploads/{user_id}/{uuid}.{ext}
  → insert documents row (status=PROCESSING)
  → Parser   → raw text
  → Chunker  → List[Chunk] (512 tok / 64 overlap)
  → Embedder → List[List[float]] (batch, text-embedding-004)
  → Qdrant   → upsert points with payload {user_id, doc_id, chunk_index}
  → BM25     → rebuild user's in-memory BM25 index
  → PostgreSQL → insert document_chunks rows
  → update documents row (status=READY)
  → return 200 document object
```

*Why synchronous:* For MVP file sizes (< 10 MB, < 200 pages) embedding takes 2–8 seconds.
A loading spinner on the frontend is acceptable. Queue infrastructure adds 3+ days of work.

### Chat flow (SSE streaming)

```
POST /api/chat/query  →  text/event-stream response
  → JWT verify
  → load conversation history from PostgreSQL
  → embed question (text-embedding-004)
  → Qdrant ANN search  → top-20, filtered by user_id + optional doc_id
  → BM25 search        → top-20 from user's index
  → RRF fusion         → merged + ranked, take top-5
  → Context builder    → assemble chunks with [Source N: file.pdf, p.3] markers
  → LangChain chain    → system prompt + context + history + question
  → Gemini 2.5 Flash   → stream tokens via SSE  event: token
  → parse [Source N]   → resolve to chunk_id + file_name + page_number
  → persist message + citations to PostgreSQL
  → SSE  event: citations  +  event: done
```

---

## MVP File Structure

```
askmydocs/
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── dependencies.py
│   ├── api/
│   │   ├── auth.py
│   │   ├── documents.py
│   │   ├── chat.py
│   │   ├── conversations.py
│   │   └── users.py
│   ├── services/
│   │   ├── auth_service.py
│   │   ├── document_service.py
│   │   ├── ingestion_service.py
│   │   └── chat_service.py
│   ├── pipeline/
│   │   ├── parser.py
│   │   ├── chunker.py
│   │   ├── embedder.py
│   │   ├── indexer.py
│   │   ├── retriever.py
│   │   ├── reranker.py
│   │   └── context_builder.py
│   ├── models/
│   │   ├── db/
│   │   │   ├── base.py
│   │   │   ├── user.py
│   │   │   ├── document.py
│   │   │   ├── chunk.py
│   │   │   ├── conversation.py
│   │   │   ├── message.py
│   │   │   └── citation.py
│   │   └── schemas/
│   │       ├── auth.py
│   │       ├── document.py
│   │       ├── chat.py
│   │       └── user.py
│   ├── core/
│   │   ├── security.py
│   │   └── exceptions.py
│   ├── db/
│   │   ├── session.py
│   │   └── migrations/
│   │       └── versions/
│   ├── storage/
│   │   └── local.py
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_auth.py
│   │   └── test_documents.py
│   ├── requirements.txt
│   └── alembic.ini
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── (auth)/
│   │   │   │   ├── login/page.tsx
│   │   │   │   └── register/page.tsx
│   │   │   ├── (app)/
│   │   │   │   ├── layout.tsx
│   │   │   │   ├── dashboard/page.tsx
│   │   │   │   ├── upload/page.tsx
│   │   │   │   ├── chat/[conversationId]/page.tsx
│   │   │   │   └── settings/page.tsx
│   │   │   ├── layout.tsx
│   │   │   └── page.tsx
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── AppShell.tsx
│   │   │   │   ├── Sidebar.tsx
│   │   │   │   └── AuthLayout.tsx
│   │   │   ├── auth/
│   │   │   │   ├── LoginForm.tsx
│   │   │   │   └── RegisterForm.tsx
│   │   │   ├── documents/
│   │   │   │   ├── DocumentCard.tsx
│   │   │   │   ├── DocumentGrid.tsx
│   │   │   │   ├── DocumentStatusBadge.tsx
│   │   │   │   └── DropzoneUploader.tsx
│   │   │   ├── chat/
│   │   │   │   ├── MessageThread.tsx
│   │   │   │   ├── UserMessage.tsx
│   │   │   │   ├── AssistantMessage.tsx
│   │   │   │   ├── CitationCard.tsx
│   │   │   │   └── ChatInput.tsx
│   │   │   └── ui/
│   │   │       ├── Spinner.tsx
│   │   │       ├── EmptyState.tsx
│   │   │       └── ProgressBar.tsx
│   │   ├── hooks/
│   │   │   ├── useAuth.ts
│   │   │   ├── useDocuments.ts
│   │   │   ├── useChat.ts
│   │   │   └── useSSEStream.ts
│   │   ├── lib/
│   │   │   ├── api.ts
│   │   │   └── auth.ts
│   │   ├── store/
│   │   │   ├── authStore.ts
│   │   │   └── documentStore.ts
│   │   └── types/
│   │       ├── auth.ts
│   │       ├── document.ts
│   │       └── chat.ts
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   └── next.config.ts
│
├── docker-compose.yml              # postgres + qdrant + backend + frontend
└── .env.example
```

---

## Phase 1: Authentication — File-by-File Implementation Plan

**Goal:** Users can register, log in, log out, and all other routes are protected.
**Output:** Working auth system, JWT middleware, and the frontend auth pages.
**Estimated time:** 2–3 days

---

### Backend

---

#### `backend/config.py`

**Purpose:** Central settings object loaded from environment variables.
All secrets and connection strings live here and nowhere else.

**What to implement:**
- Pydantic `BaseSettings` class named `Settings`
- Fields:
  - `DATABASE_URL: str` — PostgreSQL async URL (`postgresql+asyncpg://...`)
  - `SECRET_KEY: str` — HS256 signing secret (min 32 chars, no default)
  - `ALGORITHM: str = "HS256"`
  - `ACCESS_TOKEN_EXPIRE_MINUTES: int = 60`
  - `GOOGLE_API_KEY: str`
  - `QDRANT_URL: str = "http://localhost:6333"`
  - `UPLOAD_DIR: str = "./uploads"`
  - `MAX_FILE_SIZE_MB: int = 50`
- `model_config = SettingsConfigDict(env_file=".env")`
- Module-level singleton: `settings = Settings()`

**Imports needed:** `pydantic_settings`

---

#### `backend/core/security.py`

**Purpose:** All cryptographic operations in one place — password hashing and JWT.

**What to implement:**

1. **Password hashing**
   - `hash_password(plain: str) -> str`
     Uses `CryptContext(schemes=["bcrypt"])` from `passlib`. Returns the bcrypt hash.
   - `verify_password(plain: str, hashed: str) -> bool`
     Calls `pwd_context.verify(plain, hashed)`. Returns bool.

2. **JWT**
   - `create_access_token(data: dict) -> str`
     Takes a `data` dict (must include `"sub"` key = user UUID as string).
     Adds `"exp"` field: `datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)`.
     Encodes with `jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)`.
     Returns the token string.
   - `decode_access_token(token: str) -> dict`
     Calls `jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])`.
     Raises `HTTPException(401)` on `JWTError` or `ExpiredSignatureError`.
     Returns the decoded payload dict.

**Imports needed:** `passlib.context`, `jose` (python-jose), `datetime`, `config.settings`

---

#### `backend/core/exceptions.py`

**Purpose:** Named HTTP exceptions so error handling is consistent and readable.

**What to implement:**
- `CredentialsException` — `HTTPException(status_code=401, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})`
- `UserAlreadyExistsException` — `HTTPException(status_code=400, detail="Email already registered")`
- `UserNotFoundException` — `HTTPException(status_code=404, detail="User not found")`
- `ForbiddenException` — `HTTPException(status_code=403, detail="Not authorized to access this resource")`
- `DocumentNotFoundException` — `HTTPException(status_code=404, detail="Document not found")`

Each is a module-level instance (not a class), so call sites do `raise CredentialsException`.

---

#### `backend/db/session.py`

**Purpose:** SQLAlchemy async engine and session factory.

**What to implement:**
1. Create async engine:
   ```
   engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
   ```
2. Create session factory:
   ```
   AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
   ```
3. `Base = declarative_base()` — imported by all ORM models
4. `async def get_db() -> AsyncGenerator[AsyncSession, None]`
   - Opens a session, yields it, commits on success, rolls back on exception, always closes.
   - This is the FastAPI dependency used in every route.

**Imports needed:** `sqlalchemy.ext.asyncio`

---

#### `backend/models/db/base.py`

**Purpose:** Shared mixin to avoid repeating `id`, `created_at`, `updated_at` in every model.

**What to implement:**
- `TimestampMixin` — adds:
  - `created_at: Mapped[datetime]` with `server_default=func.now()`
  - `updated_at: Mapped[datetime]` with `server_default=func.now()`, `onupdate=func.now()`
- `UUIDMixin` — adds:
  - `id: Mapped[uuid.UUID]` as primary key with `default=uuid.uuid4`

---

#### `backend/models/db/user.py`

**Purpose:** SQLAlchemy ORM model for the `users` table.

**What to implement:**
- Class `User(UUIDMixin, TimestampMixin, Base)` with `__tablename__ = "users"`
- Columns:
  - `email: Mapped[str]` — `String(255)`, unique, not null, indexed
  - `password_hash: Mapped[str]` — `String(255)`, not null
  - `full_name: Mapped[Optional[str]]` — `String(255)`
  - `is_active: Mapped[bool]` — `default=True`
- Relationships (add in later phases):
  - `documents` → back-populates from `Document.user`
  - `conversations` → back-populates from `Conversation.user`

---

#### `backend/models/schemas/auth.py`

**Purpose:** Pydantic v2 schemas for auth request/response validation.

**What to implement:**
- `RegisterRequest` — fields: `email: EmailStr`, `password: str` (min 8 chars, validated), `full_name: Optional[str]`
- `LoginRequest` — fields: `email: EmailStr`, `password: str`
- `TokenResponse` — fields: `access_token: str`, `token_type: str = "bearer"`, `expires_in: int`
- `UserResponse` — fields: `id: UUID`, `email: str`, `full_name: Optional[str]`, `created_at: datetime`
  - `model_config = ConfigDict(from_attributes=True)` so it can be built from ORM objects

Password validation in `RegisterRequest`: use `@field_validator("password")` to check min length 8, at least one digit, raise `ValueError` with a clear message if invalid.

---

#### `backend/dependencies.py`

**Purpose:** FastAPI dependency injection functions shared across all routes.

**What to implement:**
1. `get_db` — re-exported from `db.session` for convenience
2. `get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User`
   - `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")`
   - Calls `decode_access_token(token)` → extracts `sub` (user UUID string)
   - Queries PostgreSQL: `SELECT * FROM users WHERE id = :user_id AND is_active = true`
   - Raises `CredentialsException` if token invalid or user not found
   - Returns the `User` ORM object
3. `get_current_active_user` — thin wrapper over `get_current_user` that double-checks `user.is_active`, raises `ForbiddenException` if not. Used in all protected routes.

---

#### `backend/services/auth_service.py`

**Purpose:** Business logic for registration and login. Routes call this, not the DB directly.

**What to implement:**

1. `async def register_user(db: AsyncSession, data: RegisterRequest) -> User`
   - Check if email exists: `SELECT id FROM users WHERE email = :email`
   - If exists → raise `UserAlreadyExistsException`
   - Hash password: `hash_password(data.password)`
   - Create `User` ORM instance, `db.add(user)`, `await db.commit()`, `await db.refresh(user)`
   - Return `User`

2. `async def login_user(db: AsyncSession, data: LoginRequest) -> TokenResponse`
   - Query user by email
   - If not found or `not verify_password(data.password, user.password_hash)` → raise `CredentialsException`
   - Call `create_access_token({"sub": str(user.id)})`
   - Return `TokenResponse(access_token=token, expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)`

---

#### `backend/api/auth.py`

**Purpose:** Route handlers for all `/api/auth/*` endpoints.

**What to implement:**

Router: `router = APIRouter(prefix="/api/auth", tags=["auth"])`

1. `POST /register` → calls `auth_service.register_user` → returns `UserResponse` (201)
2. `POST /login` → calls `auth_service.login_user` → returns `TokenResponse` (200)
3. `POST /logout` → `Depends(get_current_active_user)` → returns `{"message": "Logged out"}` (200)
   *No server-side token invalidation in MVP — client discards the token.*
4. `GET /me` → `Depends(get_current_active_user)` → returns `UserResponse` (200)

Each route only handles HTTP concerns (status codes, schema conversion). No business logic.

---

#### `backend/main.py`

**Purpose:** FastAPI application factory. Wires everything together.

**What to implement:**
1. Create `app = FastAPI(title="AskMyDocs API", version="0.1.0")`
2. Add `CORSMiddleware`:
   - `allow_origins=["http://localhost:3000"]` (extend from env later)
   - `allow_credentials=True`
   - `allow_methods=["*"]`
   - `allow_headers=["*"]`
3. Include routers: `app.include_router(auth_router)`
4. `@app.on_event("startup")`: create all tables via `async_engine` if they don't exist (dev only; Alembic takes over in later phases)
5. `GET /health` → returns `{"status": "ok"}` — used by Docker healthcheck
6. Global exception handler for unhandled `Exception` → logs to stdout, returns `500`

---

#### `backend/db/migrations/` (Alembic)

**Purpose:** Track schema changes as versioned migration scripts.

**What to implement:**
- Run `alembic init db/migrations` to scaffold
- Edit `alembic.ini`: set `script_location = db/migrations`
- Edit `env.py`:
  - Import `Base` from `models.db.base`
  - Set `target_metadata = Base.metadata`
  - Configure async engine using `settings.DATABASE_URL`
- Generate initial migration: `alembic revision --autogenerate -m "create_users_table"`
- Verify the generated script creates the `users` table with all columns and the email index
- Run: `alembic upgrade head`

---

#### `backend/tests/conftest.py`

**Purpose:** Pytest fixtures shared across all test files.

**What to implement:**
1. `@pytest.fixture` `test_db` — creates an in-memory or test PostgreSQL database, runs migrations, yields `AsyncSession`, rolls back after each test
2. `@pytest.fixture` `client` — `AsyncClient` wrapping the FastAPI app with `base_url="http://test"`
3. `@pytest.fixture` `test_user` — inserts a user with known credentials into the test DB, returns the user object
4. `@pytest.fixture` `auth_headers` — logs in as `test_user`, returns `{"Authorization": "Bearer <token>"}`

---

#### `backend/tests/test_auth.py`

**Purpose:** Integration tests for all auth endpoints.

**Test cases to implement:**
1. `test_register_success` — POST valid payload → assert 201, response has `id`, `email`
2. `test_register_duplicate_email` — register same email twice → assert second returns 400
3. `test_register_weak_password` — password < 8 chars → assert 422
4. `test_login_success` — valid credentials → assert 200, response has `access_token`
5. `test_login_wrong_password` — wrong password → assert 401
6. `test_login_nonexistent_user` — unknown email → assert 401
7. `test_get_me_authenticated` — GET /me with valid token → assert 200, correct user data
8. `test_get_me_no_token` — GET /me without header → assert 401
9. `test_get_me_invalid_token` — GET /me with garbage token → assert 401
10. `test_logout` — POST /logout with valid token → assert 200

---

#### `backend/requirements.txt`

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlalchemy[asyncio]==2.0.36
asyncpg==0.29.0
alembic==1.13.3
pydantic[email]==2.9.2
pydantic-settings==2.5.2
passlib[bcrypt]==1.7.4
python-jose[cryptography]==3.3.0
python-multipart==0.0.12
httpx==0.27.2
pytest==8.3.3
pytest-asyncio==0.24.0
anyio==4.6.2
```

---

### Frontend

---

#### `frontend/src/types/auth.ts`

**Purpose:** TypeScript interfaces for all auth-related data shapes.

**What to implement:**
```typescript
interface User {
  id: string
  email: string
  full_name: string | null
  created_at: string
}

interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

interface RegisterRequest {
  email: string
  password: string
  full_name?: string
}

interface LoginRequest {
  email: string
  password: string
}

interface AuthState {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
}
```

---

#### `frontend/src/lib/auth.ts`

**Purpose:** Token storage and retrieval. The single source of truth for where the JWT lives.

**What to implement:**
- `saveToken(token: string): void` — writes to `sessionStorage` (not `localStorage` — clears on tab close, slightly safer for MVP)
- `getToken(): string | null` — reads from `sessionStorage`
- `clearToken(): void` — removes from `sessionStorage`
- `isTokenExpired(token: string): boolean` — base64-decodes the JWT payload, checks `exp` vs `Date.now() / 1000`

**Note:** `sessionStorage` is used in MVP for simplicity. For a production build, an httpOnly cookie set by the backend is more secure.

---

#### `frontend/src/lib/api.ts`

**Purpose:** Axios instance with JWT injection and 401 handling.

**What to implement:**
1. Create `apiClient = axios.create({ baseURL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000" })`
2. **Request interceptor:** reads `getToken()`, if present adds `Authorization: Bearer <token>` header
3. **Response interceptor:** on 401 response → call `clearToken()` → `window.location.href = "/login"`
4. Export typed helper functions:
   - `api.get<T>(url, config?)` — wraps `apiClient.get`, returns `response.data`
   - `api.post<T>(url, data?, config?)` — wraps `apiClient.post`
   - `api.patch<T>(url, data?, config?)`
   - `api.delete<T>(url, config?)`

---

#### `frontend/src/store/authStore.ts`

**Purpose:** Zustand store for global auth state.

**What to implement:**
```typescript
interface AuthStore extends AuthState {
  setAuth: (user: User, token: string) => void
  clearAuth: () => void
  setLoading: (loading: boolean) => void
}
```
- `setAuth`: sets `user`, `token`, `isAuthenticated: true`, calls `saveToken(token)`
- `clearAuth`: resets to initial state, calls `clearToken()`
- Initial state: reads `getToken()` on first call — if token exists and not expired, `isAuthenticated: true`; user is `null` until `/me` is called to hydrate

---

#### `frontend/src/hooks/useAuth.ts`

**Purpose:** Composable hook used by components and pages.

**What to implement:**
1. `register(data: RegisterRequest): Promise<void>` — POST `/api/auth/register` → on success, call `login`
2. `login(data: LoginRequest): Promise<void>` — POST `/api/auth/login` → calls `setAuth(user, token)` → GET `/api/auth/me` to hydrate user → `router.push("/dashboard")`
3. `logout(): void` — POST `/api/auth/logout` (best-effort) → `clearAuth()` → `router.push("/login")`
4. `hydrateUser(): Promise<void>` — GET `/api/auth/me` → sets user in store. Called on app mount if token exists.
5. Returns `{ user, isAuthenticated, isLoading, login, register, logout }`

---

#### `frontend/src/components/layout/AuthLayout.tsx`

**Purpose:** Centered card wrapper for login and register pages.

**What to implement:**
- Full-viewport dark background (`bg-background`)
- Centered card: `max-w-md`, `rounded-xl`, `border`, `shadow-lg`, `p-8`
- App logo + name at top of card
- `children` rendered inside card
- No sidebar, no topbar

---

#### `frontend/src/components/auth/RegisterForm.tsx`

**Purpose:** Registration form with validation.

**What to implement:**
- Use `react-hook-form` + `zod` resolver
- Schema: `email` (valid email), `password` (min 8, regex for digit), `confirm_password` (must match `password`), `full_name` (optional, max 100)
- Fields: Full name input, Email input, Password input, Confirm password input
- `PasswordStrengthIndicator` inline below password field — simple bar showing Weak / Fair / Strong based on length + complexity
- Submit button — shows `<Spinner />` while `isLoading`
- Error display: field-level errors inline, API error in a top-level `<Alert variant="destructive">`
- "Already have an account? Sign in" link to `/login`
- On submit: calls `useAuth().register(data)`

---

#### `frontend/src/components/auth/LoginForm.tsx`

**Purpose:** Login form.

**What to implement:**
- `react-hook-form` + `zod`: `email` (EmailStr), `password` (required, min 1)
- Fields: Email, Password (with show/hide toggle)
- Submit button with loading state
- API error displayed as `<Alert>`
- "Don't have an account? Register" link to `/register`
- On submit: calls `useAuth().login(data)`

---

#### `frontend/src/app/(auth)/register/page.tsx`

**Purpose:** Register page — thin wrapper that composes layout + form.

**What to implement:**
- Server-side redirect check: if already authenticated → redirect to `/dashboard`
- Renders `<AuthLayout>` wrapping `<RegisterForm />`
- Page `<title>`: "Create account — AskMyDocs"

---

#### `frontend/src/app/(auth)/login/page.tsx`

**Purpose:** Login page.

**What to implement:**
- Same pattern as register: redirect if authenticated, wrap `LoginForm` in `AuthLayout`
- Reads optional `?redirect=` query param — after login, `router.push(redirect ?? "/dashboard")`
- Page `<title>`: "Sign in — AskMyDocs"

---

#### `frontend/src/app/(app)/layout.tsx`

**Purpose:** Protected layout — wraps all authenticated pages. Renders `<AppShell>`.

**What to implement:**
- Client component (`"use client"`)
- On mount: call `hydrateUser()` if token exists
- While loading: full-screen `<Spinner />`
- If `!isAuthenticated` after load attempt: `router.push("/login?redirect=" + pathname)`
- If authenticated: renders `<AppShell>{children}</AppShell>`

This pattern ensures every page inside `(app)/` is protected without repeating auth logic per page.

---

#### `frontend/src/components/layout/AppShell.tsx`

**Purpose:** The persistent shell for all authenticated pages — sidebar + main content area.

**What to implement:**
- Outer layout: `flex h-screen overflow-hidden bg-background`
- `<Sidebar />` on the left (fixed width `w-64`, full height)
- Main area: `flex-1 overflow-y-auto` — renders `{children}`
- Sidebar contains: app logo, nav links (Dashboard, Upload, Settings), user email + logout button at bottom

---

#### `frontend/src/app/layout.tsx`

**Purpose:** Root Next.js layout.

**What to implement:**
- Sets `<html lang="en" className="dark">` — enforces dark theme project-wide
- Loads font: Geist Sans via `next/font/google`
- Wraps with any global providers (Toaster for `sonner` notifications)
- Sets global metadata: `title`, `description`

---

#### `frontend/.env.local` (document, do not commit)

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

### Infrastructure

---

#### `docker-compose.yml`

**Purpose:** One command to run all services locally.

**What to implement:**

Services:
1. `postgres`
   - Image: `postgres:16-alpine`
   - Environment: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
   - Volume: `postgres_data:/var/lib/postgresql/data`
   - Port: `5432:5432`
   - Healthcheck: `pg_isready`

2. `qdrant`
   - Image: `qdrant/qdrant:latest`
   - Volume: `qdrant_data:/qdrant/storage`
   - Port: `6333:6333`

3. `backend`
   - Build: `./backend`
   - Command: `uvicorn main:app --host 0.0.0.0 --port 8000 --reload`
   - Depends on: `postgres` (condition: `service_healthy`), `qdrant`
   - Env file: `.env`
   - Volume: `./backend:/app` (for hot reload)
   - Port: `8000:8000`

4. `frontend`
   - Build: `./frontend`
   - Command: `npm run dev`
   - Depends on: `backend`
   - Env file: `./frontend/.env.local`
   - Port: `3000:3000`

Named volumes: `postgres_data`, `qdrant_data`

---

#### `backend/Dockerfile`

**Purpose:** Containerize the FastAPI backend.

**What to implement:**
- Base: `python:3.12-slim`
- `WORKDIR /app`
- Copy `requirements.txt` → `pip install --no-cache-dir -r requirements.txt`
- Copy rest of source
- `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]`

---

#### `.env.example`

```
# PostgreSQL
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/askmydocs

# Auth
SECRET_KEY=your-secret-key-min-32-chars-here
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Google AI
GOOGLE_API_KEY=your-google-api-key

# Qdrant
QDRANT_URL=http://localhost:6333

# File storage
UPLOAD_DIR=./uploads
MAX_FILE_SIZE_MB=50
```

---

## Phase 1 Completion Checklist

```
Backend
  [ ] config.py — Settings with all env vars
  [ ] core/security.py — hash_password, verify_password, create_access_token, decode_access_token
  [ ] core/exceptions.py — 5 named HTTP exceptions
  [ ] db/session.py — async engine, session factory, get_db dependency
  [ ] models/db/base.py — UUIDMixin, TimestampMixin
  [ ] models/db/user.py — User ORM model
  [ ] models/schemas/auth.py — RegisterRequest, LoginRequest, TokenResponse, UserResponse
  [ ] dependencies.py — get_current_user, get_current_active_user
  [ ] services/auth_service.py — register_user, login_user
  [ ] api/auth.py — 4 routes: register, login, logout, me
  [ ] main.py — app factory, CORS, router include, startup, health
  [ ] db/migrations/ — alembic init + initial migration for users table
  [ ] tests/conftest.py — test_db, client, test_user, auth_headers fixtures
  [ ] tests/test_auth.py — 10 test cases passing
  [ ] requirements.txt

Frontend
  [ ] types/auth.ts — User, TokenResponse, AuthState interfaces
  [ ] lib/auth.ts — saveToken, getToken, clearToken, isTokenExpired
  [ ] lib/api.ts — axios instance, request/response interceptors, typed helpers
  [ ] store/authStore.ts — Zustand store with setAuth, clearAuth
  [ ] hooks/useAuth.ts — register, login, logout, hydrateUser
  [ ] components/layout/AuthLayout.tsx — centered card layout
  [ ] components/auth/RegisterForm.tsx — react-hook-form + zod + strength meter
  [ ] components/auth/LoginForm.tsx — react-hook-form + zod
  [ ] app/(auth)/register/page.tsx
  [ ] app/(auth)/login/page.tsx
  [ ] app/(app)/layout.tsx — auth guard + AppShell
  [ ] components/layout/AppShell.tsx — sidebar + main area
  [ ] app/layout.tsx — dark theme, font, providers

Infrastructure
  [ ] docker-compose.yml — postgres, qdrant, backend, frontend
  [ ] backend/Dockerfile
  [ ] .env.example
  [ ] Verify: docker compose up → all 4 services healthy
  [ ] Verify: POST /api/auth/register → 201
  [ ] Verify: POST /api/auth/login → token
  [ ] Verify: GET /api/auth/me with token → user object
  [ ] Verify: GET /api/auth/me without token → 401
  [ ] Verify: frontend register → login → redirect to /dashboard (blank page, no crash)
```

---

## Phase 1 → Phase 2 Handoff

When Phase 1 checklist is complete, Phase 2 starts from this exact foundation:

- `get_current_active_user` dependency is used unchanged in document routes
- `User.id` (UUID) is the foreign key for all document and conversation records
- `AsyncSession` from `get_db` is the DB interface for all new services
- `AppShell` is extended with a Documents nav link
- `authStore` is extended with no changes — document state goes in its own `documentStore`
