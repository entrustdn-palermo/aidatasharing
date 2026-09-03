"""
Connection URL Parser for Backend
Converts connection URLs into MindsDB-compatible configuration
"""

from typing import Dict, Any, Tuple, Optional
from urllib.parse import urlparse, parse_qs
import re


class ConnectionParseError(Exception):
    """Exception raised when connection URL parsing fails"""
    pass


def parse_connection_url(url: str, connector_type: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Parse a connection URL into connection_config and credentials
    
    Args:
        url: Connection URL string
        connector_type: Type of connector (mysql, postgresql, s3, etc.)
    
    Returns:
        Tuple of (connection_config, credentials)
    
    Raises:
        ConnectionParseError: If URL parsing fails
    """
    try:
        if connector_type == 'mysql':
            return parse_mysql_url(url)
        elif connector_type == 'postgresql':
            return parse_postgresql_url(url)
        elif connector_type == 's3':
            return parse_s3_url(url)
        elif connector_type == 'mongodb':
            return parse_mongodb_url(url)
        elif connector_type == 'clickhouse':
            return parse_clickhouse_url(url)
        elif connector_type == 'api':
            return parse_api_url(url)
        else:
            raise ConnectionParseError(f"Unsupported connector type: {connector_type}")
    except Exception as e:
        if isinstance(e, ConnectionParseError):
            raise
        raise ConnectionParseError(f"Failed to parse connection URL: {str(e)}")


def parse_mysql_url(url: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Parse MySQL connection URL"""
    parsed = urlparse(url)
    
    if parsed.scheme != 'mysql':
        raise ConnectionParseError("URL must start with mysql://")
    
    if not all([parsed.hostname, parsed.path[1:], parsed.username]):
        raise ConnectionParseError("MySQL URL must include host, database, and username")
    
    # Apply SSL configuration for localhost development
    from app.core.config import settings
    
    port = parsed.port or 3306
    connection_config = {
        "host": parsed.hostname,
        "port": port,
        "database": parsed.path[1:]  # Remove leading slash
    }
    
    # Get SSL-aware configuration
    ssl_config = settings.get_ssl_config_for_connector(
        'mysql', parsed.hostname, port, connection_config
    )
    connection_config.update(ssl_config)
    
    credentials = {
        "user": parsed.username,
        "password": parsed.password or ""
    }
    
    return connection_config, credentials


def parse_postgresql_url(url: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Parse PostgreSQL connection URL"""
    parsed = urlparse(url)
    
    if parsed.scheme not in ['postgresql', 'postgres']:
        raise ConnectionParseError("URL must start with postgresql:// or postgres://")
    
    if not all([parsed.hostname, parsed.path[1:], parsed.username]):
        raise ConnectionParseError("PostgreSQL URL must include host, database, and username")
    
    # Apply SSL configuration for localhost development
    from app.core.config import settings
    
    port = parsed.port or 5432
    connection_config = {
        "host": parsed.hostname,
        "port": port,
        "database": parsed.path[1:]  # Remove leading slash
    }
    
    # Get SSL-aware configuration
    ssl_config = settings.get_ssl_config_for_connector(
        'postgresql', parsed.hostname, port, connection_config
    )
    connection_config.update(ssl_config)
    
    credentials = {
        "user": parsed.username,
        "password": parsed.password or ""
    }
    
    return connection_config, credentials


def parse_s3_url(url: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Parse S3 connection URL"""
    parsed = urlparse(url)
    
    if parsed.scheme != 's3':
        raise ConnectionParseError("URL must start with s3://")
    
    if not all([parsed.hostname, parsed.username, parsed.password]):
        raise ConnectionParseError("S3 URL must include bucket name, access key, and secret key")
    
    # Apply SSL configuration for development
    from app.core.config import settings
    
    # For S3, we'll use the bucket name as the host for SSL detection
    host = parsed.hostname
    
    connection_config = {
        "bucket_name": host,
        "region": parsed.path[1:] if parsed.path[1:] else "us-east-1"  # Remove leading slash, default region
    }
    
    # Get SSL-aware configuration
    ssl_config = settings.get_ssl_config_for_connector(
        's3', host, None, connection_config
    )
    connection_config.update(ssl_config)
    
    credentials = {
        "aws_access_key_id": parsed.username,
        "aws_secret_access_key": parsed.password
    }
    
    return connection_config, credentials


def parse_mongodb_url(url: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Parse MongoDB connection URL"""
    parsed = urlparse(url)
    
    if parsed.scheme != 'mongodb':
        raise ConnectionParseError("URL must start with mongodb://")
    
    if not all([parsed.hostname, parsed.path[1:]]):
        raise ConnectionParseError("MongoDB URL must include host and database")
    
    # Apply SSL configuration for development
    from app.core.config import settings
    
    host = parsed.hostname
    port = parsed.port or 27017
    
    connection_config = {
        "host": host,
        "port": port,
        "database": parsed.path[1:]  # Remove leading slash
    }
    
    # Get SSL-aware configuration
    ssl_config = settings.get_ssl_config_for_connector(
        'mongodb', host, port, connection_config
    )
    connection_config.update(ssl_config)
    
    credentials = {
        "username": parsed.username or "",
        "password": parsed.password or ""
    }
    
    return connection_config, credentials


def parse_clickhouse_url(url: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Parse ClickHouse connection URL"""
    parsed = urlparse(url)
    
    if parsed.scheme != 'clickhouse':
        raise ConnectionParseError("URL must start with clickhouse://")
    
    if not parsed.hostname:
        raise ConnectionParseError("ClickHouse URL must include host")
    
    # Apply SSL configuration for development
    from app.core.config import settings
    
    host = parsed.hostname
    port = parsed.port or 9000
    
    connection_config = {
        "host": host,
        "port": port,
        "database": parsed.path[1:] if parsed.path[1:] else "default"  # Remove leading slash, default database
    }
    
    # Get SSL-aware configuration
    ssl_config = settings.get_ssl_config_for_connector(
        'clickhouse', host, port, connection_config
    )
    connection_config.update(ssl_config)
    
    credentials = {
        "user": parsed.username or "default",
        "password": parsed.password or ""
    }
    
    return connection_config, credentials


def parse_api_url(url: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Parse API connection URL"""
    parsed = urlparse(url)
    
    if parsed.scheme not in ['http', 'https']:
        raise ConnectionParseError("API URL must start with http:// or https://")
    
    # Apply SSL configuration for development
    from app.core.config import settings
    
    host = parsed.hostname
    port = parsed.port
    
    base_url = f"{parsed.scheme}://{parsed.netloc}"
    query_params = parse_qs(parsed.query)
    
    # Get SSL-aware configuration
    ssl_config = settings.get_ssl_config_for_connector(
        'api', host, port, {'base_url': base_url}
    )
    
    # Use the potentially modified base_url from SSL configuration
    base_url = ssl_config.get('base_url', base_url)
    
    # Extract common API authentication parameters
    api_key = None
    auth_header = "Authorization"
    
    # Look for various API key parameter names
    for key_name in ['api_key', 'apikey', 'key', 'token', 'access_token']:
        if key_name in query_params:
            api_key = query_params[key_name][0]  # Take first value
            break
    
    # Remove auth params from the endpoint URL to keep it clean
    clean_query_params = {k: v for k, v in query_params.items() 
                         if k not in ['api_key', 'apikey', 'key', 'token', 'access_token']}
    
    # Reconstruct clean endpoint
    endpoint = parsed.path
    if clean_query_params:
        query_string = "&".join([f"{k}={v[0]}" for k, v in clean_query_params.items()])
        endpoint = f"{endpoint}?{query_string}"
    
    connection_config = {
        "base_url": base_url,
        "endpoint": endpoint,
        "method": "GET",
        "prefer_http": ssl_config.get('prefer_http', False),
        "ssl_verify": ssl_config.get('ssl_verify', True)
    }
    
    credentials = {
        "api_key": api_key or "",
        "auth_header": auth_header
    }
    
    return connection_config, credentials

