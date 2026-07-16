"""Seed a self-contained HexShare demo workspace.

Idempotent: safe to run on every `docker compose ... up`. The first run
creates a demo user, sample documents, a due-diligence room, and external
access; later runs detect the existing data and only refresh the printed
share/invite links.

Intended for `HEXSHARE_DEMO_MODE=true` deployments only. Everything is
created under the local tenant so the credential-free demo login lands in a
populated workspace.

Run:  PYTHONPATH=/app python scripts/seed_demo.py
"""
from __future__ import annotations

import asyncio
import io
import os
import textwrap

import asyncpg

from app.adapters import JWTTokenAdapter, NoopEventBus
from app.auth.tenant_auth import TenantPrincipal
from app.core.authz import ResourceAction
from app.domain import DocumentGroup, NdaContentType, NdaScopeType
from app.infra.factories import ObjectStorageFactory, StorageFactory
from app.ports.object_storage_port import ObjectWriteRequest
from app.services import DocumentService, ExternalRoomAccessService, LinkService, NdaService

TENANT = os.getenv("HEXSHARE_LOCAL_TENANT_ID", "local")
DEMO_USER = "demo-user"
GROUP_ID = "dcgrp_demo"
GUEST_EMAIL = "guest@example.com"
GUEST_NAME = "Guest Investor"
FRONTEND = os.getenv("HEXSHARE_FRONTEND_URL", "http://localhost:3000").rstrip("/")
SHARE_LINK_TTL_SECONDS = 365 * 24 * 60 * 60
OUTPUT_PATH = os.getenv("HEXSHARE_DEMO_LINKS_PATH", "/seed-output/demo-links.txt")

SHARE_DOC_ID = "doc_demo_share"

DEMO_NDA_TITLE = "Project Atlas — Mutual Non-Disclosure Agreement"
DEMO_NDA_TEXT = (
    "MUTUAL NON-DISCLOSURE AGREEMENT\n\n"
    "This is a sample NDA presented by HexShare's NDA gate. In a real data room, "
    "a recipient must read this agreement to the end, type their name as a signature, "
    "and confirm acceptance before any document in the room can be opened.\n\n"
    "1. Confidential Information. All materials made available in this room are "
    "confidential and provided solely to evaluate a potential transaction.\n\n"
    "2. Non-Disclosure. The recipient agrees not to disclose or reproduce any "
    "confidential information without prior written consent.\n\n"
    "3. Attribution. The recipient understands that every page viewed is watermarked "
    "with their identity and that all access is audited.\n\n"
    "4. Acceptance. Typing your name below and confirming constitutes acceptance of "
    "this agreement, recorded with your identity, timestamp, and NDA version.\n\n"
    "(Replace this placeholder with your own NDA text once you self-host.)"
)

_FULL_BITMASK = int(
    ResourceAction.READ
    | ResourceAction.WRITE
    | ResourceAction.DELETE
    | ResourceAction.MANAGE
    | ResourceAction.EXPORT
)


# Sample PDF generation (Pillow -> image-backed PDF; no binary assets shipped)
def _load_font(size: int):
    from PIL import ImageFont

    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _make_pdf(*, title: str, body: str, pages: int = 1) -> bytes:
    """Render a simple multi-page PDF with a title and wrapped body text."""
    from PIL import Image, ImageDraw

    width, height = 1240, 1754  # ~A4 at 150 DPI
    margin = 110
    title_font = _load_font(48)
    body_font = _load_font(28)
    wrapped = textwrap.wrap(body, width=78) or [""]

    images = []
    for page_index in range(max(1, pages)):
        img = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(img)
        y = margin
        if page_index == 0:
            draw.text((margin, y), title, fill=(17, 24, 39), font=title_font)
            y += 90
        else:
            draw.text((margin, y), f"{title} (cont.)", fill=(107, 114, 128), font=body_font)
            y += 60
        draw.line([(margin, y), (width - margin, y)], fill=(229, 231, 235), width=2)
        y += 40
        for line in wrapped:
            draw.text((margin, y), line, fill=(31, 41, 55), font=body_font)
            y += 44
        draw.text(
            (margin, height - margin),
            f"HexShare demo document — page {page_index + 1}",
            fill=(156, 163, 175),
            font=body_font,
        )
        images.append(img)

    buf = io.BytesIO()
    images[0].save(buf, format="PDF", save_all=True, append_images=images[1:], resolution=150.0)
    return buf.getvalue()


# Seed helpers
async def _upsert_local_user(pool) -> None:
    sql = """
    INSERT INTO local_users (
        tenant_id, user_id, email, name, auth_provider, provider_subject,
        created_at, last_login_at
    )
    VALUES ($1, $2, $3, $4, 'demo', $2, NOW(), NOW())
    ON CONFLICT (tenant_id, user_id) DO UPDATE
        SET email = EXCLUDED.email,
            name = EXCLUDED.name
    """
    async with pool.acquire() as con:
        await con.execute(sql, TENANT, DEMO_USER, "demo@hexshare.local", "Demo User")


async def _upsert_group_membership(pool) -> None:
    sql = """
    INSERT INTO document_group_memberships (
        group_id, tenant_id, user_id, permissions, granted_by, granted_at
    )
    VALUES ($1, $2, $3, $4, $3, NOW())
    ON CONFLICT (group_id, user_id) DO UPDATE
        SET permissions = EXCLUDED.permissions
    """
    async with pool.acquire() as con:
        await con.execute(sql, GROUP_ID, TENANT, DEMO_USER, _FULL_BITMASK)


async def _create_document(
    *,
    storage,
    object_storage,
    document_service: DocumentService,
    document_id: str,
    name: str,
    pdf_bytes: bytes,
    room_id: str | None,
) -> None:
    existing = await storage.get_document(tenant_id=TENANT, document_id=document_id)
    if existing is not None:
        return
    object_key = object_storage.build_object_key(
        tenant_id=TENANT,
        document_id=document_id,
        filename=name,
    )
    await object_storage.write_object(
        ObjectWriteRequest(
            object_key=object_key,
            content=pdf_bytes,
            content_type="application/pdf",
        )
    )
    await document_service.create_document(
        document_id=document_id,
        tenant_id=TENANT,
        name=name,
        mime_type="application/pdf",
        size=len(pdf_bytes),
        storage_key=object_key,
        created_by=DEMO_USER,
        room_id=room_id,
    )


async def _seed_documents_and_room(*, storage, object_storage, document_service) -> None:
    # Ungrouped doc backing the public, no-login share link.
    await _create_document(
        storage=storage,
        object_storage=object_storage,
        document_service=document_service,
        document_id=SHARE_DOC_ID,
        name="HexShare — Company Overview.pdf",
        pdf_bytes=_make_pdf(
            title="Acme Corp — Company Overview",
            body=(
                "This is a sample document served through HexShare's secure viewer. "
                "Every page you see is rendered server-side as an image with a "
                "watermark baked into the pixels — the original file never reaches "
                "your browser. Open this same link in a private window to see the "
                "watermark carry the viewer's identity. Replace these samples with "
                "your own documents once you self-host."
            ),
            pages=2,
        ),
        room_id=None,
    )

    # A few more ungrouped documents so the dashboard is populated.
    extra_docs = [
        ("doc_demo_deck", "Pitch Deck.pdf", "Acme Corp — Pitch Deck",
         "Company vision, market size, product, traction, and the ask. A sample "
         "deck so the dashboard shows a realistic document set."),
        ("doc_demo_cap", "Cap Table.pdf", "Acme Corp — Capitalization Table",
         "Founders, option pool, and investor ownership across rounds. Sample figures only."),
        ("doc_demo_metrics", "Key Metrics.pdf", "Acme Corp — Key Metrics",
         "ARR, growth rate, gross margin, CAC and payback. Placeholder numbers for the demo."),
        ("doc_demo_legal", "Incorporation Docs.pdf", "Acme Corp — Incorporation",
         "Certificate of incorporation and bylaws (sample). Replace with your own once you self-host."),
        ("doc_demo_notes", "Board Notes.pdf", "Acme Corp — Board Meeting Notes",
         "Summary of the last board meeting: hiring plan, runway, and next milestones."),
    ]
    for doc_id, name, title, body in extra_docs:
        await _create_document(
            storage=storage,
            object_storage=object_storage,
            document_service=document_service,
            document_id=doc_id,
            name=name,
            pdf_bytes=_make_pdf(title=title, body=body, pages=1),
            room_id=None,
        )

    # The due-diligence room (document group).
    if await storage.get_document_group(tenant_id=TENANT, group_id=GROUP_ID) is None:
        from datetime import datetime

        await storage.save_document_group(
            DocumentGroup(
                id=GROUP_ID,
                tenant_id=TENANT,
                name="Project Atlas — Due Diligence Room",
                description="Sample data room shared with an external recipient.",
                created_by=DEMO_USER,
                created_at=datetime.utcnow(),
            )
        )

    # Grouped documents inside the room.
    await _create_document(
        storage=storage,
        object_storage=object_storage,
        document_service=document_service,
        document_id="doc_demo_room_1",
        name="Financial Model.pdf",
        pdf_bytes=_make_pdf(
            title="Project Atlas — Financial Model",
            body=(
                "Three-year projection summary. Revenue, gross margin, burn and "
                "runway figures would live here. In the room viewer, time spent on "
                "each page is recorded per recipient, and download attempts are "
                "logged even when blocked by policy."
            ),
            pages=3,
        ),
        room_id=GROUP_ID,
    )
    await _create_document(
        storage=storage,
        object_storage=object_storage,
        document_service=document_service,
        document_id="doc_demo_room_2",
        name="Term Sheet.pdf",
        pdf_bytes=_make_pdf(
            title="Project Atlas — Term Sheet",
            body=(
                "Non-binding summary of proposed terms. Access to this document is "
                "granted through an external access grant that can be revoked at any "
                "time — revocation takes effect on the recipient's next request."
            ),
            pages=1,
        ),
        room_id=GROUP_ID,
    )


async def _ensure_share_link(*, storage, link_service: LinkService) -> str:
    links = list(await storage.list_share_links(tenant_id=TENANT, document_id=SHARE_DOC_ID))
    active = [link for link in links if link.revoked_at is None]
    if active:
        link = active[0]
    else:
        link = await link_service.create_share_link(
            tenant_id=TENANT,
            document_id=SHARE_DOC_ID,
            created_by=DEMO_USER,
            expires_in_seconds=SHARE_LINK_TTL_SECONDS,
            can_download=False,
            can_print=False,
            require_email=False,
        )
    token = await link_service.generate_share_token(link)
    return f"{FRONTEND}/view/{token}"


def _write_links(share_url: str, invite_url: str) -> None:
    short_share = f"{FRONTEND}/api/auth/demo/share"
    short_room = f"{FRONTEND}/api/auth/demo/room"
    lines = [
        "HexShare demo links",
        "===================",
        "",
        f"Open the app:   {FRONTEND}   then click 'Try the demo'.",
        "",
        "Short links (recommended — copy-safe, they redirect to live tokens):",
        f"  Public share (no login):   {short_share}",
        f"  External room invite:      {short_room}",
        f"    (on the invite page, enter the email: {GUEST_EMAIL})",
        "",
        "Full tokenized links (only work if copied whole — they are very long):",
        f"  Share:    {share_url}",
        f"  Invite:   {invite_url}",
        "",
    ]
    body = "\n".join(lines)
    print("\n" + body)
    try:
        os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
        with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
            fh.write(body)
        print(f"Links written to {OUTPUT_PATH}")
    except OSError as exc:
        print(f"(could not write {OUTPUT_PATH}: {exc})")


async def main() -> None:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit("DATABASE_URL is required to seed the demo")

    pool = await asyncpg.create_pool(dsn=dsn)
    try:
        import app.infra.bootstrap  # noqa: F401  (registers adapter factories)

        storage = StorageFactory.create(os.getenv("HEXSHARE_STORAGE", "postgres"), pool=pool)
        object_storage = ObjectStorageFactory.create(os.getenv("HEXSHARE_OBJECT_STORAGE", "s3"))
        token_adapter = JWTTokenAdapter()
        event_bus = NoopEventBus()
        document_service = DocumentService(storage, event_bus)
        link_service = LinkService(storage, token_adapter, event_bus)
        external = ExternalRoomAccessService(storage=storage)
        nda_service = NdaService(storage=storage, object_storage=object_storage)

        await _upsert_local_user(pool)
        await _seed_documents_and_room(
            storage=storage,
            object_storage=object_storage,
            document_service=document_service,
        )
        await _upsert_group_membership(pool)

        # Gate the demo room with a sample NDA so the acceptance flow is visible.
        await nda_service.set_policy(
            tenant_id=TENANT,
            scope_type=NdaScopeType.ROOM,
            scope_id=GROUP_ID,
            created_by=DEMO_USER,
            content_type=NdaContentType.TEXT,
            text_body=DEMO_NDA_TEXT,
            title=DEMO_NDA_TITLE,
            require_scroll=True,
            require_typed_signature=True,
        )

        share_url = await _ensure_share_link(storage=storage, link_service=link_service)

        provisioned = await external.provision_room_access(
            principal=TenantPrincipal(tenant_id=TENANT, user_id=DEMO_USER),
            room_id=GROUP_ID,
            recipient_email=GUEST_EMAIL,
            recipient_display_name=GUEST_NAME,
            can_download=False,
            can_print=False,
        )
        invite_url = f"{FRONTEND}/external-room/invitations/{provisioned.invite_token}"

        _write_links(share_url, invite_url)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
