import mysql.connector
from mysql.connector import errorcode
from .settings import HostConfig
from contextlib import contextmanager

class ConnectionError(Exception):
    """Custom exception for database connection issues."""
    pass

@contextmanager
def get_connection(config: HostConfig):
    """
    Standard buffered connection factory.
    Suitable for lightweight metadata queries.
    """
    cnx = None
    try:
        cnx = mysql.connector.connect(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password.get_secret_value(),
            database=config.database,
            charset=config.charset,
            connect_timeout=config.connect_timeout,
            buffered=True
        )
        if not cnx.is_connected():
            raise ConnectionError(f"Failed to connect to {config.host}")
        
        # Ping to verify connection
        cnx.ping(reconnect=True, attempts=3, delay=1)
        
        yield cnx
    except mysql.connector.Error as err:
        raise ConnectionError(f"MariaDB Error [{err.errno}]: {err.msg}") from err
    finally:
        if cnx and cnx.is_connected():
            cnx.close()

@contextmanager
def get_streaming_connection(config: HostConfig):
    """
    Unbuffered streaming connection factory using SSCursor.
    Required for large table data migration to avoid OOM.
    """
    cnx = None
    try:
        # use_pure=True is required for SSCursor in mysql-connector-python
        cnx = mysql.connector.connect(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password.get_secret_value(),
            database=config.database,
            charset=config.charset,
            connect_timeout=config.connect_timeout,
            use_pure=True 
        )
        if not cnx.is_connected():
            raise ConnectionError(f"Failed to connect to {config.host} (Streaming)")

        cnx.ping(reconnect=True, attempts=3, delay=1)
        
        # Create SSCursor for unbuffered fetching
        # Note: SSCursor is used at the cursor level, not connection level in some drivers,
        # but in mysql-connector-python with use_pure=True, we use cursor(buffered=False)
        # or specifically the SSCursor if importing it.
        # Actually, the plan says "SSCursor".
        from mysql.connector.cursor import SSCursor
        cursor = cnx.cursor(cursor_class=SSCursor)
        
        yield cnx, cursor
        
        cursor.close()
    except mysql.connector.Error as err:
        raise ConnectionError(f"MariaDB Streaming Error [{err.errno}]: {err.msg}") from err
    finally:
        if cnx and cnx.is_connected():
            cnx.close()
