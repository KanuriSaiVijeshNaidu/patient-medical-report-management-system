import logging
from typing import Any, Dict, Optional
from uuid import UUID

logger = logging.getLogger("audit.service")

PROHIBITED_DETAIL_KEYS = {
    "password", "token", "access_token", "jwt", "otp", "raw_otp", 
    "aadhaar", "raw_aadhaar", "secret", "private_key",
    "signed_url", "download_url", "file_content", "content", "file_bytes",
    "raw_token", "share_token", "token_hash", "grant_token", "qr_payload"
}


class AuditService:
    """Centralized service for emitting validated, sanitized security and audit events."""

    @staticmethod
    def sanitize_details(details: Optional[Dict[str, Any]], request_id: Optional[str] = None) -> Dict[str, Any]:
        """Ensures prohibited sensitive keys are purged and request_id is attached."""
        clean = {}
        if details:
            for k, v in details.items():
                if k.lower() in PROHIBITED_DETAIL_KEYS:
                    clean[k] = "[REDACTED]"
                else:
                    clean[k] = v
        if request_id:
            clean["request_id"] = request_id
        return clean

    @classmethod
    def log_security_event(
        cls,
        client: Any,
        action: str,
        entity_type: str,
        entity_id: str,
        ip_address: str,
        actor_user_id: Optional[UUID] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ) -> Optional[str]:
        """Calls record_security_audit_event RPC in PostgreSQL using trusted server connection."""
        if not client:
            logger.warning("AuditService.log_security_event skipped: Supabase client not configured.")
            return None

        clean_details = cls.sanitize_details(details, request_id)

        try:
            params = {
                "p_actor_user_id": str(actor_user_id) if actor_user_id else None,
                "p_action": action,
                "p_entity_type": entity_type,
                "p_entity_id": str(entity_id),
                "p_ip_address": ip_address,
                "p_user_agent": user_agent or "unknown",
                "p_details": clean_details,
            }
            res = client.rpc("record_security_audit_event", params).execute()
            return res.data
        except Exception as e:
            logger.error("Failed to write security audit event '%s': %s", action, e)
            return None


audit_service = AuditService()
