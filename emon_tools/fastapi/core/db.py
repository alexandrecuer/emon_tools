"""
Module for initializing the database.

This module sets up the SQLAlchemy engine and provides a function
to initialize the database with initial data, specifically creating a
default superuser if one does not already exist. It is expected that
database tables are created via Alembic migrations.
"""

from sqlmodel import Session, select
from emon_tools.fastapi.core.database import engine
from emon_tools.fastapi import crud
from emon_tools.fastapi.core.config import settings
from emon_tools.fastapi.models.db import User, UserCreate


# make sure all SQLModel models are imported (app.models)
# before initializing DB otherwise, SQLModel might fail
# to initialize relationships properly
# for more details:
# https://github.com/fastapi/full-stack-fastapi-template/issues/28


def init_db(session: Session) -> None:
    """
    Initialize the database with initial data.

    This function checks if a superuser exists in the database using
    the default email provided in the settings. If the superuser is not
    found, it creates one using the provided credentials. Tables should
    be created via Alembic migrations prior to calling this function.

    Parameters:
        session (Session):
            The SQLModel database session used for executing queries.
    """
    # Tables should be created with Alembic migrations
    # But if you don't want to use migrations, create
    # the tables un-commenting the next lines
    # from sqlmodel import SQLModel

    # This works because the models are already imported
    # and registered from app.models
    # SQLModel.metadata.create_all(engine)
    # ✅ Ensure all tables are created 
    user = session.exec(
        select(User).where(User.email == settings.FIRST_SUPERUSER)
    ).first()
    if not user:
        user_in = UserCreate(
            email=settings.FIRST_SUPERUSER,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            is_superuser=True,
        )
        user = crud.create_user(session=session, user_create=user_in)
