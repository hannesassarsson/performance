from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.config import get_settings

settings = get_settings()

# Railway's DATABASE_URL is postgres://... — SQLAlchemy 2.x wants postgresql://
_db_url = settings.database_url.replace("postgres://", "postgresql://", 1)

engine = create_engine(_db_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
