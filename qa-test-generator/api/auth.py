"""
JWT authentication dependency for FastAPI.

The frontend (Supabase Auth) sends the user's access token in the
Authorization header. We validate it via supabase.auth.get_user()
and return the verified user_id for use in request handlers.
"""

from typing import Optional
from fastapi import Depends, HTTPException, Header
from db.client import get_supabase_client


async def get_current_user(authorization: Optional[str] = Header(None)) -> str:
    """
    FastAPI dependency — extracts and verifies the Supabase JWT.

    Returns the authenticated user's UUID string.
    Raises HTTP 401 if the token is missing or invalid.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header with Bearer token required")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Bearer token is empty")

    try:
        client = get_supabase_client()
        response = client.auth.get_user(token)
        if not response or not response.user:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return str(response.user.id)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Token verification failed")
