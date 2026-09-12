from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models.

    Every model module (app/models/*.py) must import this Base so that
    Alembic's autogenerate / env.py can discover all tables via
    Base.metadata.
    """

    pass
