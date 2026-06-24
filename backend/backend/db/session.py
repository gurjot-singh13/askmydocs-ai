from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import settings

# ── Engine ───────────────────────────────────────────────────────────────────
# pool_pre_ping=True silently reconnects if a stale connection is reused
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,           # set echo=True locally to log SQL
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# ── Session factory ──────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,  # avoids lazy-load errors after commit
    autoflush=False,
    autocommit=False,
)


# ── FastAPI dependency ───────────────────────────────────────────────────────
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield a database session for the duration of one request.
    Commits on success, rolls back on any exception, always closes.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
