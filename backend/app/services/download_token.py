"""
Download Token Service — deep module for HMAC download-token lifecycle.

Extracted from StorageService to give callers a focused 3-method seam
instead of importing a 39-method storage module just to generate a token.
"""

import hashlib
import hmac
import secrets
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class DownloadTokenService:
    """HMAC-signed download-token generation, validation, and expiry cleanup.

    Designed as a singleton — instantiate via ``download_token_service``.
    """

    def _get_hmac_key(self) -> bytes:
        """Get the HMAC signing key from settings, with a fallback for development."""
        key = getattr(settings, 'SECRET_KEY', None)
        if key:
            return key.encode('utf-8') if isinstance(key, str) else key
        # Fallback: derive a stable key from ENCRYPTION_KEY
        enc_key = getattr(settings, 'ENCRYPTION_KEY', None)
        if enc_key:
            if isinstance(enc_key, str):
                enc_key = enc_key.encode('utf-8')
            return hashlib.sha256(enc_key).digest()
        # Last resort for development only
        logger.warning("No SECRET_KEY or ENCRYPTION_KEY configured — download tokens are NOT secure!")
        return b"dev-fallback-key-change-in-production"

    def generate(
        self,
        dataset_id: int,
        user_id: Optional[int] = None,
        expires_in_hours: int = 24,
    ) -> str:
        """Generate a secure HMAC-signed download token for a dataset."""
        random_part = secrets.token_urlsafe(32)
        expiry = datetime.utcnow() + timedelta(hours=expires_in_hours)
        expiry_ts = int(expiry.timestamp())

        user_str = str(user_id) if user_id else "anon"
        payload = f"{dataset_id}-{user_str}-{expiry_ts}"

        token_data = f"{payload}-{random_part}"
        sig = hmac.new(
            self._get_hmac_key(), token_data.encode(), hashlib.sha256
        ).hexdigest()[:16]

        return f"{payload}.{random_part}.{sig}"

    def validate(self, token: str) -> bool:
        """Validate an HMAC-signed download token.

        Returns ``True`` when the token is well-formed, unexpired, and
        its HMAC signature matches.
        """
        if not token or not isinstance(token, str):
            return False

        try:
            parts = token.split(".")
            if len(parts) != 3:
                return False

            payload, random_part, provided_sig = parts

            dash_count = payload.count("-")
            if dash_count < 2:
                return False

            *_, user_id_str, expiry_ts_str = payload.rsplit("-", 2)

            # Validate dataset_id is numeric
            dataset_id_str = payload.split("-")[0]
            try:
                int(dataset_id_str)
            except ValueError:
                return False

            if user_id_str != "anon":
                try:
                    int(user_id_str)
                except ValueError:
                    return False

            try:
                expiry_ts = int(expiry_ts_str)
            except ValueError:
                return False

            if datetime.utcnow().timestamp() > expiry_ts:
                return False

            if len(random_part) < 40:
                return False

            if len(provided_sig) != 16:
                return False

            token_data = f"{payload}-{random_part}"
            expected_sig = hmac.new(
                self._get_hmac_key(), token_data.encode(), hashlib.sha256
            ).hexdigest()[:16]

            return hmac.compare_digest(provided_sig, expected_sig)

        except Exception as e:
            logger.error(f"Token validation error: {str(e)}")
            return False

    def cleanup_expired(self, db_session) -> Dict[str, Any]:
        """Mark expired pending/in-progress download records.

        Returns a summary dict with the count of records updated.
        This is a lightweight operation that doesn't touch storage backends.
        """
        from app.models.dataset import DatasetDownload

        try:
            expired = (
                db_session.query(DatasetDownload)
                .filter(
                    DatasetDownload.expires_at < datetime.utcnow(),
                    DatasetDownload.download_status.in_(["pending", "in_progress"]),
                )
                .all()
            )

            for record in expired:
                record.download_status = "expired"

            db_session.commit()
            logger.info(f"🧹 Marked {len(expired)} expired download(s)")
            return {"expired_count": len(expired)}
        except Exception as e:
            logger.error(f"Failed to cleanup expired downloads: {e}")
            db_session.rollback()
            return {"expired_count": 0, "error": str(e)}


# Singleton
download_token_service = DownloadTokenService()
