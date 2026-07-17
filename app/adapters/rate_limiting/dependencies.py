"""Rate limiting FastAPI dependencies."""
from __future__ import annotations

import logging
from typing import Callable, Awaitable

from fastapi import Depends, HTTPException, Request

from app.adapters.rate_limiting.limiter import RateLimiter
from app.api.dependencies.services import (
    get_policy_loader,
    get_rate_limit_backend,
)

logger = logging.getLogger(__name__)


def _subject_from_request(request: Request) -> str:
    """Extract unique subject from request.
    
    Uses tenant_id and user_id for multi-tenant deployments,
    falls back to IP address for unauthenticated requests.
    """
    tenant_id = request.headers.get("X-Tenant-Id")
    
    # Try to get user from auth
    user_id = None
    if hasattr(request.state, "user") and request.state.user:
        user_id = request.state.user.id

    if tenant_id and user_id:
        return f"{tenant_id}:{user_id}"
    elif user_id:
        return f"user:{user_id}"
    else:
        ip = request.client.host if request.client else "unknown"
        return f"ip:{ip}"


def _get_user_tier(request: Request) -> str:
    """Get subscription tier from request.
    
    Default to free tier for unauthenticated or tier not set.
    """
    if hasattr(request.state, "user") and request.state.user:
        # Assuming user has a tier attribute (set by auth or tier service)
        return getattr(request.state.user, "tier", "free")
    return "free"


def rate_limit(policy_name: str) -> Callable[[Request], Awaitable[None]]:
    """Create rate limit dependency for a policy.
    
    Usage in route:
        @app.get("/api/documents")
        async def list_documents(
            _rate_limit = Depends(rate_limit("api_general"))
        ):
            ...
    
    Parameters
    ----------
    policy_name:
        Name of the policy to check against.
    """

    async def dependency(
        request: Request,
        policy_loader = Depends(get_policy_loader),
        backend = Depends(get_rate_limit_backend),
    ) -> None:
        if not getattr(request.app.state, "rate_limit_enabled", False) or backend is None:
            return

        tier = _get_user_tier(request)
        subject = _subject_from_request(request)

        # Load policies for user's tier
        policies = await policy_loader.get_policies(tier)

        # Check policy exists
        if policy_name not in policies:
            logger.warning(
                f"Rate limit policy not found: {policy_name}. "
                f"Available policies for tier {tier}: {list(policies.keys())}"
            )
            return  # Policy not configured, allow

        # Check rate limit
        limiter = RateLimiter(backend, policies)
        result = await limiter.check(policy_name, subject)

        if not result.allowed:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={
                    "X-RateLimit-Limit": str(result.limit),
                    "X-RateLimit-Remaining": str(result.remaining),
                    "X-RateLimit-Reset": str(result.reset_at),
                    "Retry-After": str(result.retry_after),
                },
            )

    return dependency
