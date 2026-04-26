from contextlib import contextmanager

import mysql.connector

from ..config.settings import HostConfig


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
            collation=config.collation,
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
    cursor = None
    try:
        # use_pure=True is required for SSCursor in mysql-connector-python
        cnx = mysql.connector.connect(
            host=config.host,
            port=config.port,
            user=config.user,
            password=config.password.get_secret_value(),
            database=config.database,
            charset=config.charset,
            collation=config.collation,
            connect_timeout=config.connect_timeout,
            use_pure=True
        )
        if not cnx.is_connected():
            raise ConnectionError(f"Failed to connect to {config.host} (Streaming)")

        cnx.ping(reconnect=True, attempts=3, delay=1)

        cursor = cnx.cursor(buffered=False)

        yield cnx, cursor

    except mysql.connector.Error as err:
        raise ConnectionError(f"MariaDB Streaming Error [{err.errno}]: {err.msg}") from err
    finally:
        if cursor is not None:
            import contextlib
            with contextlib.suppress(mysql.connector.Error):
                cursor.close()
        if cnx and cnx.is_connected():
            cnx.close()
