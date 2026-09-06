"""
File utility functions for sanitization and preview generation.
"""

import re
from typing import Optional


def sanitize_filename(filename: Optional[str], default: str = "download") -> str:
    """Sanitize a filename for use in Content-Disposition headers.
    Strips path separators, control characters, and limits length.
    """
    if not filename:
        return default
    filename = filename.replace("/", "_").replace("\\", "_")
    filename = re.sub(r'[\x00-\x1f\x7f-\x9f"]', "", filename)
    if len(filename) > 255:
        name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
        filename = name[:250] + ("." + ext if ext else "")
    return filename or default
