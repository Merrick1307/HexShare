import os
from datetime import datetime, timedelta, timezone
import jwt

from app.ports.flow_state import FlowStatePort


class SignedJWTFlowState(FlowStatePort):
    def __init__(self, *, secret: str | None = None) -> None:
        self.secret = secret or os.getenv("HEXSHARE_SESSION_SECRET")
        if not self.secret:
            raise RuntimeError("Missing HEXSHARE_SESSION_SECRET")

    def seal(self, payload: dict, *, ttl_seconds: int) -> str:
        exp = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        body = {**payload, "exp": int(exp.timestamp())}
        return jwt.encode(body, self.secret, algorithm="HS256")

    def unseal(self, token: str) -> dict:
        return jwt.decode(token, self.secret, algorithms=["HS256"])