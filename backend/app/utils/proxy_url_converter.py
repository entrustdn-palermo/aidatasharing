"""
Proxy URL Converter Utilities
Handles conversion of proxy URLs for proper routing
"""

import re
import logging
from typing import Dict, Any, Optional, Union
from urllib.parse import urlparse, urlunparse

logger = logging.getLogger(__name__)


def get_corrected_proxy_url(original_url: str, proxy_host: str = "localhost", proxy_port: int = 8080) -> str:
    """
    Convert a proxy URL to the correct format for local development
    
    Args:
        original_url: The original URL to convert
        proxy_host: The proxy host (default: localhost)
        proxy_port: The proxy port (default: 8080)
        
    Returns:
        Corrected URL string
    """
    try:
        if not original_url:
            return original_url
        
        # Parse the URL
        parsed = urlparse(original_url)
        
        # Convert HTTPS to HTTP for local development
        if parsed.scheme == 'https':
            scheme = 'http'
        else:
            scheme = parsed.scheme
        
        # Use provided proxy host and port
        netloc = f"{proxy_host}:{proxy_port}"
        
        # Reconstruct the URL
        corrected_url = urlunparse((
            scheme,
            netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment
        ))
        
        logger.debug(f"Converted URL: {original_url} -> {corrected_url}")
        return corrected_url
        
    except Exception as e:
        logger.error(f"Error converting proxy URL {original_url}: {e}")
        return original_url


def convert_proxy_urls_in_response(response_data: Union[Dict[str, Any], list], 
                                 proxy_host: str = "localhost", 
                                 proxy_port: int = 8080) -> Union[Dict[str, Any], list]:
    """
    Convert proxy URLs in response data
    
    Args:
        response_data: The response data containing URLs to convert
        proxy_host: The proxy host (default: localhost)
        proxy_port: The proxy port (default: 8080)
        
    Returns:
        Response data with converted URLs
    """
    try:
        if isinstance(response_data, dict):
            return _convert_urls_in_dict(response_data, proxy_host, proxy_port)
        elif isinstance(response_data, list):
            return _convert_urls_in_list(response_data, proxy_host, proxy_port)
        else:
            return response_data
            
    except Exception as e:
        logger.error(f"Error converting URLs in response: {e}")
        return response_data


def _convert_urls_in_dict(data: Dict[str, Any], proxy_host: str, proxy_port: int) -> Dict[str, Any]:
    """Convert URLs in dictionary data"""
    converted_data = {}
    
    for key, value in data.items():
        if isinstance(value, str) and _is_url(value):
            converted_data[key] = get_corrected_proxy_url(value, proxy_host, proxy_port)
        elif isinstance(value, dict):
            converted_data[key] = _convert_urls_in_dict(value, proxy_host, proxy_port)
        elif isinstance(value, list):
            converted_data[key] = _convert_urls_in_list(value, proxy_host, proxy_port)
        else:
            converted_data[key] = value
    
    return converted_data


def _convert_urls_in_list(data: list, proxy_host: str, proxy_port: int) -> list:
    """Convert URLs in list data"""
    converted_data = []
    
    for item in data:
        if isinstance(item, str) and _is_url(item):
            converted_data.append(get_corrected_proxy_url(item, proxy_host, proxy_port))
        elif isinstance(item, dict):
            converted_data.append(_convert_urls_in_dict(item, proxy_host, proxy_port))
        elif isinstance(item, list):
            converted_data.append(_convert_urls_in_list(item, proxy_host, proxy_port))
        else:
            converted_data.append(item)
    
    return converted_data


def _is_url(text: str) -> bool:
    """Check if text is a URL"""
    try:
        parsed = urlparse(text)
        return bool(parsed.scheme and parsed.netloc)
    except Exception:
        return False






def ensure_localhost_proxy_uses_http(url: str) -> str:
    """
    Ensure localhost/127.0.0.1 proxy URLs use HTTP instead of HTTPS for local development
    
    Args:
        url: The URL to check and convert
        
    Returns:
        URL with HTTP scheme if it's a localhost URL, otherwise unchanged
    """
    try:
        if not url:
            return url
            
        parsed = urlparse(url)
        
        # Check if it's a localhost or 127.0.0.1 URL
        is_localhost = (
            parsed.hostname in ['localhost', '127.0.0.1'] or 
            (parsed.hostname and parsed.hostname.startswith('192.168.')) or
            (parsed.hostname and parsed.hostname.startswith('10.')) or
            (parsed.hostname and parsed.hostname.startswith('172.'))
        )
        
        if is_localhost and parsed.scheme == 'https':
            # Convert to HTTP for local development
            converted_url = urlunparse((
                'http',
                parsed.netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment
            ))
            logger.info(f"Converted localhost HTTPS to HTTP: {url} -> {converted_url}")
            return converted_url
        
        return url
        
    except Exception as e:
        logger.error(f"Error converting localhost proxy URL {url}: {e}")
        return url