"""Build non-PII recipient labels for visible document watermarks."""
from __future__ import annotations

import hashlib


def pseudonymous_watermark(
    *identity_parts: str | None,
    brand_name: str = "HexShare",
) -> str:
    material = "|".join(
        str(part).strip().lower()
        for part in identity_parts
        if part is not None and str(part).strip()
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest().upper()
    recipient_code = f"{digest[:4]}-{digest[4:8]}-{digest[8:12]}"
    resolved_brand = brand_name.strip() or "HexShare"
    return f"{resolved_brand} - Recipient {recipient_code}"
