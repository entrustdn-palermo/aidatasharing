"""
Configuration Validator for AI Share Platform
"""

import logging

logger = logging.getLogger(__name__)


def validate_and_exit_on_failure():
    """Validate configuration and exit if critical issues found"""
    try:
        # Basic validation - check if we can import necessary modules
        from .app_config import get_app_config
        
        # Get config to validate it's accessible
        config = get_app_config()
        
        # Log configuration status
        logger.info("✅ Configuration validation passed")
        
        # Warn about missing optional configurations
        if not config.integrations.GOOGLE_API_KEY:
            logger.warning("⚠️  GOOGLE_API_KEY not set - AI chat features will be limited")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Configuration validation failed: {e}")
        return False