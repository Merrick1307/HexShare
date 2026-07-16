from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.auth.tenant_auth import TenantPrincipal
from app.core.authz import ResourceAction
from app.domain import (
    ExternalAccessGrant,
    ExternalAccessGrantType,
    ExternalAccessResourceType,
    ExternalParty,
    ExternalPartyEmail,
    ExternalPartyStatus,
    ExternalRoomEvent,
    ExternalRoomEventType,
    ExternalRoomSession,
)
from app.ports.storage_port import StoragePort


@dataclass(frozen=True)
class ExternalRoomSessionTokens:
    access_token: str
    refresh_token: str
    expires_in: int
    refresh_expires_in: int
    token_type: str = "Bearer"


@dataclass(frozen=True)
class ExternalRoomPrincipal:
    tenant_id: str
    external_party_id: str
    session_id: str
    grant_id: str
    room_id: str
    permissions: int
    email: str
    display_name: str | None = None
    can_download: bool = False
    can_print: bool = False

    def as_tenant_principal(self) -> TenantPrincipal:
        return TenantPrincipal(
            tenant_id=self.tenant_id,
            user_id=self.external_party_id,
            token=None,
            roles=("external_party",),
            policy={self.room_id: self.permissions},
        )


@dataclass(frozen=True)
class ProvisionedRoomAccess:
    party: ExternalParty
    grant: ExternalAccessGrant
    invite_token: str
    invite_expires_at: datetime


class ExternalRoomAccessService:
    def __init__(
        self,
        *,
        storage: StoragePort,
        jwt_secret: str | None = None,
        issuer: str | None = None,
        audience: str | None = None,
        access_ttl_seconds: int | None = None,
        refresh_ttl_seconds: int | None = None,
        invite_ttl_seconds: int | None = None,
    ) -> None:
        self._storage = storage
        self._jwt_secret = jwt_secret or os.getenv("HEXSHARE_JWT_SECRET")
        if not self._jwt_secret:
            raise RuntimeError("Missing HEXSHARE_JWT_SECRET for external room access service")
        public_url = (os.getenv("HEXSHARE_PUBLIC_URL") or "http://localhost:8099").rstrip("/")
        self._issuer = issuer or public_url
        self._audience = audience or os.getenv("HEXSHARE_AUTH_AUDIENCE", "hexshare-external")
        self._access_ttl_seconds = int(os.getenv("HEXSHARE_EXTERNAL_ROOM_ACCESS_TTL_SECONDS", access_ttl_seconds or 3600))
        self._refresh_ttl_seconds = int(os.getenv("HEXSHARE_EXTERNAL_ROOM_REFRESH_TTL_SECONDS", refresh_ttl_seconds or 60 * 60 * 24 * 7))
        self._invite_ttl_seconds = int(os.getenv("HEXSHARE_EXTERNAL_ROOM_INVITE_TTL_SECONDS", invite_ttl_seconds or 60 * 60 * 24 * 7))

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC).replace(tzinfo=None)

    @staticmethod
    def _normalize_email(email: str | None) -> str | None:
        if email is None:
            return None
        normalized = email.strip().lower()
        return normalized or None

    @staticmethod
    def _hash(value: str | None) -> str | None:
        if not value:
            return None
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _room_permissions(*, can_download: bool) -> int:
        mask = int(ResourceAction.READ)
        if can_download:
            mask |= int(ResourceAction.EXPORT)
        return mask

    def _encode_token(self, *, token_use: str, payload: dict, expires_at: datetime) -> str:
        exp = expires_at.replace(tzinfo=UTC)
        claims = {
            "iss": self._issuer,
            "aud": self._audience,
            "token_use": token_use,
            "iat": int(datetime.now(UTC).timestamp()),
            "exp": int(exp.timestamp()),
            **payload,
        }
        return jwt.encode(claims, self._jwt_secret, algorithm="HS256")

    def _decode_token(self, token: str, *, expected_use: str) -> dict:
        try:
            payload = jwt.decode(
                token,
                self._jwt_secret,
                algorithms=["HS256"],
                audience=self._audience,
                options={"require": ["exp", "iat", "tenant_id"]},
            )
        except jwt.PyJWTError as exc:
            # Malformed / truncated / expired tokens become a domain error so
            # callers return a clean 4xx instead of an unhandled 500.
            raise ValueError("invalid_token") from exc
        if payload.get("token_use") != expected_use:
            raise ValueError("invalid_token_use")
        return payload

    async def _upsert_external_party(
        self,
        *,
        tenant_id: str,
        created_by: str,
        email: str,
        display_name: str | None,
    ) -> tuple[ExternalParty, ExternalPartyEmail]:
        now = self._now()
        normalized_email = self._normalize_email(email)
        if not normalized_email:
            raise ValueError("email_required")
        label = (display_name or "").strip() or None
        party = await self._storage.get_external_party_by_email(
            tenant_id=tenant_id,
            email_normalized=normalized_email,
        )
        if party is None:
            party = ExternalParty(
                id=self._storage.generate_id("ep"),
                tenant_id=tenant_id,
                display_name=label,
                status=ExternalPartyStatus.ACTIVE,
                created_by=created_by,
                created_at=now,
                updated_at=now,
                archived_at=None,
            )
        elif label and party.display_name != label:
            party = party.copy(update={"display_name": label, "updated_at": now})
        await self._storage.save_external_party(party)
        email_record = ExternalPartyEmail(
            id=self._storage.generate_id("epe"),
            tenant_id=tenant_id,
            external_party_id=party.id,
            email_normalized=normalized_email,
            email_original=email,
            is_primary=True,
            verified_at=None,
            last_seen_at=None,
            created_at=now,
        )
        await self._storage.save_external_party_email(email_record)
        return party, email_record

    async def provision_room_access(
        self,
        *,
        principal: TenantPrincipal,
        room_id: str,
        recipient_email: str,
        recipient_display_name: str | None = None,
        can_download: bool = False,
        can_print: bool = False,
        expires_in_seconds: int | None = None,
        invite_expires_in_seconds: int | None = None,
    ) -> ProvisionedRoomAccess:
        party, email_record = await self._upsert_external_party(
            tenant_id=principal.tenant_id,
            created_by=principal.user_id,
            email=recipient_email,
            display_name=recipient_display_name,
        )
        now = self._now()
        grant_expires_at = now + timedelta(seconds=expires_in_seconds) if expires_in_seconds else None
        existing_grants = list(
            await self._storage.list_external_access_grants(
                tenant_id=principal.tenant_id,
                external_party_id=party.id,
                resource_type=ExternalAccessResourceType.ROOM.value,
                resource_id=room_id,
            )
        )
        active_grant = next((grant for grant in existing_grants if grant.revoked_at is None), None)
        permissions = self._room_permissions(can_download=can_download)
        if active_grant is None:
            grant = ExternalAccessGrant(
                id=self._storage.generate_id("eag"),
                tenant_id=principal.tenant_id,
                external_party_id=party.id,
                resource_type=ExternalAccessResourceType.ROOM,
                resource_id=room_id,
                grant_type=ExternalAccessGrantType.PROVISIONED,
                permissions=permissions,
                can_download=can_download,
                can_print=can_print,
                expires_at=grant_expires_at,
                revoked_at=None,
                granted_by=principal.user_id,
                granted_at=now,
                updated_at=now,
            )
        else:
            grant = active_grant.copy(
                update={
                    "permissions": permissions,
                    "can_download": can_download,
                    "can_print": can_print,
                    "expires_at": grant_expires_at,
                    "updated_at": now,
                    "revoked_at": None,
                }
            )
        await self._storage.save_external_access_grant(grant)

        invite_expires_at = now + timedelta(seconds=invite_expires_in_seconds or self._invite_ttl_seconds)
        invite_token = self._encode_token(
            token_use="external_room_invite",
            payload={
                "tenant_id": principal.tenant_id,
                "grant_id": grant.id,
                "room_id": room_id,
                "external_party_id": party.id,
                "email": email_record.email_normalized,
            },
            expires_at=invite_expires_at,
        )
        return ProvisionedRoomAccess(
            party=party,
            grant=grant,
            invite_token=invite_token,
            invite_expires_at=invite_expires_at,
        )

    async def inspect_invite(self, *, invite_token: str) -> dict:
        payload = self._decode_token(invite_token, expected_use="external_room_invite")
        tenant_id = str(payload["tenant_id"])
        grant_id = str(payload["grant_id"])
        room_id = str(payload["room_id"])
        email = str(payload["email"])
        grant = await self._storage.get_external_access_grant(tenant_id=tenant_id, grant_id=grant_id)
        if grant is None or grant.resource_type != ExternalAccessResourceType.ROOM:
            raise ValueError("grant_not_found")
        if grant.revoked_at is not None:
            raise ValueError("grant_revoked")
        if grant.expires_at is not None and grant.expires_at <= self._now():
            raise ValueError("grant_expired")
        party = await self._storage.get_external_party(tenant_id=tenant_id, external_party_id=grant.external_party_id)
        if party is None:
            raise ValueError("party_not_found")
        group = await self._storage.get_document_group(tenant_id=tenant_id, group_id=room_id)
        if group is None:
            raise ValueError("group_not_found")
        return {
            "tenant_id": tenant_id,
            "grant": grant,
            "party": party,
            "group": group,
            "email": email,
            "expires_at": datetime.fromtimestamp(int(payload["exp"]), tz=UTC).replace(tzinfo=None),
        }

    async def create_session_from_invite(
        self,
        *,
        invite_token: str,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> ExternalRoomSessionTokens:
        inspection = await self.inspect_invite(invite_token=invite_token)
        normalized_email = self._normalize_email(email)
        expected_email = inspection["email"]
        if not normalized_email:
            raise ValueError("email_required")
        if normalized_email != expected_email:
            raise ValueError("email_not_allowed")
        tenant_id = inspection["tenant_id"]
        grant: ExternalAccessGrant = inspection["grant"]
        party: ExternalParty = inspection["party"]
        if party.status != ExternalPartyStatus.ACTIVE:
            raise ValueError("party_inactive")
        now = self._now()
        session = ExternalRoomSession(
            id=self._storage.generate_id("ers"),
            tenant_id=tenant_id,
            external_party_id=party.id,
            external_access_grant_id=grant.id,
            room_id=grant.resource_id,
            permissions=grant.permissions,
            presented_email=normalized_email,
            started_at=now,
            ended_at=None,
            ip_hash=self._hash(ip_address),
            ua_hash=self._hash(user_agent),
        )
        await self._storage.save_external_room_session(session)
        await self._storage.mark_external_party_email_seen(
            tenant_id=tenant_id,
            email_normalized=normalized_email,
            seen_at=now,
            verified_at=now,
        )
        await self._storage.save_external_room_event(
            ExternalRoomEvent(
                id=self._storage.generate_id("ere"),
                tenant_id=tenant_id,
                external_room_session_id=session.id,
                room_id=grant.resource_id,
                event_type=ExternalRoomEventType.ROOM_OPEN,
                document_id=None,
                timestamp=now,
            )
        )
        return self._issue_session_tokens(
            session=session,
            party=party,
            email=normalized_email,
        )

    async def revoke_room_access(self, *, tenant_id: str, grant_id: str, room_id: str) -> None:
        grant = await self._storage.get_external_access_grant(tenant_id=tenant_id, grant_id=grant_id)
        if grant is None or grant.resource_type != ExternalAccessResourceType.ROOM or grant.resource_id != room_id:
            raise ValueError("grant_not_found")
        await self._storage.revoke_external_access_grant(
            tenant_id=tenant_id,
            grant_id=grant_id,
            revoked_at=self._now(),
        )

    async def get_room_group(self, *, tenant_id: str, room_id: str):
        return await self._storage.get_document_group(tenant_id=tenant_id, group_id=room_id)

    async def list_room_access(self, *, tenant_id: str, room_id: str) -> list[dict]:
        grants = list(
            await self._storage.list_external_access_grants(
                tenant_id=tenant_id,
                resource_type=ExternalAccessResourceType.ROOM.value,
                resource_id=room_id,
            )
        )
        items: list[dict] = []
        for grant in grants:
            party = await self._storage.get_external_party(
                tenant_id=tenant_id,
                external_party_id=grant.external_party_id,
            )
            email = await self._storage.get_external_party_primary_email(
                tenant_id=tenant_id,
                external_party_id=grant.external_party_id,
            )
            if party is None or email is None:
                continue
            items.append(
                {
                    "grant_id": grant.id,
                    "external_party_id": grant.external_party_id,
                    "display_name": party.display_name,
                    "email": email.email_normalized,
                    "room_id": room_id,
                    "can_download": grant.can_download,
                    "can_print": grant.can_print,
                    "revoked_at": grant.revoked_at,
                    "expires_at": grant.expires_at,
                    "granted_at": grant.granted_at,
                }
            )
        return items

    def _issue_session_tokens(
        self,
        *,
        session: ExternalRoomSession,
        party: ExternalParty,
        email: str,
    ) -> ExternalRoomSessionTokens:
        access_expires_at = self._now() + timedelta(seconds=self._access_ttl_seconds)
        refresh_expires_at = self._now() + timedelta(seconds=self._refresh_ttl_seconds)
        access_token = self._encode_token(
            token_use="external_room_access",
            payload={
                "tenant_id": session.tenant_id,
                "session_id": session.id,
                "grant_id": session.external_access_grant_id,
                "room_id": session.room_id,
                "external_party_id": session.external_party_id,
                "permissions": session.permissions,
                "email": email,
                "display_name": party.display_name,
            },
            expires_at=access_expires_at,
        )
        refresh_token = self._encode_token(
            token_use="external_room_refresh",
            payload={
                "tenant_id": session.tenant_id,
                "session_id": session.id,
                "grant_id": session.external_access_grant_id,
                "room_id": session.room_id,
                "external_party_id": session.external_party_id,
                "email": email,
            },
            expires_at=refresh_expires_at,
        )
        return ExternalRoomSessionTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=self._access_ttl_seconds,
            refresh_expires_in=self._refresh_ttl_seconds,
        )

    async def authenticate_access_token(self, *, access_token: str) -> ExternalRoomPrincipal:
        payload = self._decode_token(access_token, expected_use="external_room_access")
        tenant_id = str(payload["tenant_id"])
        session_id = str(payload["session_id"])
        session = await self._storage.get_external_room_session(tenant_id=tenant_id, session_id=session_id)
        if session is None:
            raise ValueError("session_not_found")
        if session.ended_at is not None:
            raise ValueError("session_closed")
        grant = await self._storage.get_external_access_grant(
            tenant_id=tenant_id,
            grant_id=session.external_access_grant_id,
        )
        if grant is None or grant.revoked_at is not None:
            raise ValueError("grant_revoked")
        if grant.expires_at is not None and grant.expires_at <= self._now():
            raise ValueError("grant_expired")
        party = await self._storage.get_external_party(
            tenant_id=tenant_id,
            external_party_id=session.external_party_id,
        )
        if party is None:
            raise ValueError("party_not_found")
        if party.status != ExternalPartyStatus.ACTIVE:
            raise ValueError("party_inactive")
        return ExternalRoomPrincipal(
            tenant_id=tenant_id,
            external_party_id=session.external_party_id,
            session_id=session.id,
            grant_id=grant.id,
            room_id=session.room_id,
            permissions=grant.permissions,
            email=session.presented_email,
            display_name=party.display_name,
            can_download=grant.can_download,
            can_print=grant.can_print,
        )

    async def refresh_session(self, *, refresh_token: str) -> ExternalRoomSessionTokens:
        payload = self._decode_token(refresh_token, expected_use="external_room_refresh")
        tenant_id = str(payload["tenant_id"])
        session_id = str(payload["session_id"])
        session = await self._storage.get_external_room_session(tenant_id=tenant_id, session_id=session_id)
        if session is None or session.ended_at is not None:
            raise ValueError("session_closed")
        party = await self._storage.get_external_party(
            tenant_id=tenant_id,
            external_party_id=session.external_party_id,
        )
        if party is None:
            raise ValueError("party_not_found")
        grant = await self._storage.get_external_access_grant(
            tenant_id=tenant_id,
            grant_id=session.external_access_grant_id,
        )
        if grant is None or grant.revoked_at is not None:
            raise ValueError("grant_revoked")
        if grant.expires_at is not None and grant.expires_at <= self._now():
            raise ValueError("grant_expired")
        refreshed_session = session.copy(update={"permissions": grant.permissions})
        await self._storage.save_external_room_session(refreshed_session)
        return self._issue_session_tokens(
            session=refreshed_session,
            party=party,
            email=session.presented_email,
        )

    async def record_document_list(self, *, principal: ExternalRoomPrincipal) -> None:
        await self._storage.save_external_room_event(
            ExternalRoomEvent(
                id=self._storage.generate_id("ere"),
                tenant_id=principal.tenant_id,
                external_room_session_id=principal.session_id,
                room_id=principal.room_id,
                event_type=ExternalRoomEventType.DOCUMENT_LIST,
                document_id=None,
                timestamp=self._now(),
            )
        )

    async def record_nda_accepted(self, *, principal: ExternalRoomPrincipal, document_id: str | None = None) -> None:
        await self._storage.save_external_room_event(
            ExternalRoomEvent(
                id=self._storage.generate_id("ere"),
                tenant_id=principal.tenant_id,
                external_room_session_id=principal.session_id,
                room_id=principal.room_id,
                event_type=ExternalRoomEventType.NDA_ACCEPTED,
                document_id=document_id,
                timestamp=self._now(),
            )
        )

    async def record_document_download(self, *, principal: ExternalRoomPrincipal, document_id: str) -> None:
        await self._storage.save_external_room_event(
            ExternalRoomEvent(
                id=self._storage.generate_id("ere"),
                tenant_id=principal.tenant_id,
                external_room_session_id=principal.session_id,
                room_id=principal.room_id,
                event_type=ExternalRoomEventType.DOCUMENT_DOWNLOAD,
                document_id=document_id,
                timestamp=self._now(),
            )
        )

    async def close_session(self, *, principal: ExternalRoomPrincipal) -> None:
        now = self._now()
        await self._storage.end_external_room_session(
            tenant_id=principal.tenant_id,
            session_id=principal.session_id,
            ended_at=now,
        )
        await self._storage.save_external_room_event(
            ExternalRoomEvent(
                id=self._storage.generate_id("ere"),
                tenant_id=principal.tenant_id,
                external_room_session_id=principal.session_id,
                room_id=principal.room_id,
                event_type=ExternalRoomEventType.ROOM_CLOSE,
                document_id=None,
                timestamp=now,
            )
        )
