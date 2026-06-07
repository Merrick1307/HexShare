from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
from user_agents import parse as parse_ua

from app.domain import AuditLog
from app.ports.storage_port import StoragePort


class AuditService:
    """Records audit events for link creation and access."""

    def __init__(self, storage: StoragePort) -> None:
        self._storage = storage

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @staticmethod
    def _parse_device(user_agent: str | None) -> str:
        """Parse User-Agent string into a human-readable device name."""
        if not user_agent:
            return "Unknown Device"
        ua = parse_ua(user_agent)
        device = ua.device.family
        browser = ua.browser.family
        os = ua.os.family
        if device and device.lower() != "other":
            return f"{device} / {browser}"
        return f"{os} / {browser}"

    @staticmethod
    async def _lookup_location(ip_address: str | None) -> str:
        """Derive city and country from IP address using ip-api.com."""
        if not ip_address or ip_address in ("127.0.0.1", "localhost"):
            return "Unknown Location"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(
                    f"http://ip-api.com/json/{ip_address}",
                    params={"fields": "status,city,country"},
                )
                data = response.json()
                if data.get("status") == "success":
                    city = data.get("city", "")
                    country = data.get("country", "")
                    return f"{city}, {country}".strip(", ")
        except Exception:
            pass
        return "Unknown Location"

    async def log_link_created(
        self,
        *,
        tenant_id: str,
        link_id: str,
        document_id: str,
        actor: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        """Log a link.created audit event."""
        device, location = await asyncio.gather(
            asyncio.to_thread(self._parse_device, user_agent),
            self._lookup_location(ip_address),
        )
        log = AuditLog(
            id=self._storage.generate_id("aud"),
            tenant_id=tenant_id,
            event_type="link.created",
            link_id=link_id,
            document_id=document_id,
            actor=actor,
            ip_address=ip_address,
            device=device,
            location=location,
            timestamp=self._now(),
        )
        await self._storage.save_audit_log(log)

    async def log_link_accessed(
        self,
        *,
        tenant_id: str,
        link_id: str,
        document_id: str,
        actor: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        """Log a link.accessed audit event."""
        device, location = await asyncio.gather(
            asyncio.to_thread(self._parse_device, user_agent),
            self._lookup_location(ip_address),
        )
        log = AuditLog(
            id=self._storage.generate_id("aud"),
            tenant_id=tenant_id,
            event_type="link.accessed",
            link_id=link_id,
            document_id=document_id,
            actor=actor or "anonymous",
            ip_address=ip_address,
            device=device,
            location=location,
            timestamp=self._now(),
        )
        await self._storage.save_audit_log(log)