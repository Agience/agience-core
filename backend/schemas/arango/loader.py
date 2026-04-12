# schemas/arango/loader.py
"""
ArangoDB initialization and health check functions.
"""
import logging
import time
from arango.database import StandardDatabase
from schemas.arango.initialize import init_arangodb, get_arangodb_connection
from core import config

logger = logging.getLogger(__name__)

def init_arango_db(max_retries: int = 15, retry_delay: float = 5.0) -> StandardDatabase:
    """
    Initialize ArangoDB: create database, collections, and indexes.
    Called during app startup with retry logic.
    
    Args:
        max_retries: Maximum number of connection attempts
        retry_delay: Initial delay between retries (doubles each attempt, capped at 30s)
    """
    host = config.ARANGO_HOST
    port = config.ARANGO_PORT
    logger.info(f"🔌 ArangoDB target: {host}:{port} (database: {config.ARANGO_DATABASE})")

    last_error = None
    delay = retry_delay
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"🔌 Connecting to ArangoDB (attempt {attempt}/{max_retries})...")
            
            db = init_arangodb(
                host=host,
                port=port,
                username=config.ARANGO_USERNAME,
                password=config.ARANGO_PASSWORD,
                db_name=config.ARANGO_DATABASE
            )
            logger.info(" ArangoDB initialized")
            
            return db
            
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(f"⏳ ArangoDB not ready yet ({type(e).__name__}: {e}), retrying in {delay:.0f}s...")
                time.sleep(delay)
                delay = min(delay * 2, 30)  # Exponential backoff, capped at 30s
            else:
                logger.error(f" ArangoDB failed to connect after {max_retries} attempts")
                raise
    
    if last_error:
        raise last_error
    raise RuntimeError("Failed to initialize ArangoDB")


def check_arango_health() -> dict:
    """
    Health check for ArangoDB.
    Returns status dict with connection state.
    """
    try:
        db = get_arangodb_connection(
            host=config.ARANGO_HOST,
            port=config.ARANGO_PORT,
            username=config.ARANGO_USERNAME,
            password=config.ARANGO_PASSWORD,
            db_name=config.ARANGO_DATABASE
        )
        # Simple query to verify connection
        _ = db.version()
        return {"arango_status": True}
    except Exception as e:
        logger.error("ArangoDB health check failed", exc_info=e)
        return {"arango_status": False, "error": str(e)}