"""
Shared pytest fixtures for the communication agent test suite.

An in-memory SQLite database is used for all tests so no file is left on disk.
"""
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.database import Base, OutreachRecord, ReplyStatus

TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def test_engine():
    # StaticPool forces all connections to share one underlying SQLite connection,
    # which is required for in-memory databases to be visible across sessions.
    engine = create_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(test_engine):
    Session = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def sample_investor():
    return {
        "name": "Alice Investor",
        "email": "alice@example.com",
        "firm": "Alpha Capital",
        "focus_area": "longevity biotech",
        "notes": "Led three longevity deals",
    }


@pytest.fixture()
def seeded_record(db_session, sample_investor):
    record = OutreachRecord(
        name=sample_investor["name"],
        email=sample_investor["email"],
        firm=sample_investor["firm"],
        focus_area=sample_investor["focus_area"],
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record
