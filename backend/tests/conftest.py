import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
