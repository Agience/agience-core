# app/core/dependencies.py
import logging
from typing import Generator
from arango.database import StandardDatabase

from core import config
from schemas.arango.initialize import get_arangodb_connection

logger = logging.getLogger(__name__)


def get_arango_db() -> Generator[StandardDatabase, None, None]:
    """Get ArangoDB connection for dependency injection."""
    db = get_arangodb_connection(
        host=config.ARANGO_HOST,
        port=config.ARANGO_PORT,
        username=config.ARANGO_USERNAME,
        password=config.ARANGO_PASSWORD,
        db_name=config.ARANGO_DATABASE
    )
    try:
        yield db
    finally:
        pass  # ArangoDB client handles connection pooling
