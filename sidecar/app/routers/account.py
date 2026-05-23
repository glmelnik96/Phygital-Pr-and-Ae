"""GET /account/balance — current Phygital+ credit balance for the active session."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/account/balance")
async def balance(request: Request) -> dict:
    """Return current credit balance.

    Response: {ok, balance, currency, is_infinity, expires_at, user_name}
    On Phygital+ errors returns 502 so the UI can show a clear hint.
    """
    get_client = getattr(request.app.state, "get_client", None)
    if get_client is None:
        raise HTTPException(status_code=503, detail="session_not_ready")

    try:
        client = await get_client()
    except Exception as e:  # no_session / refresh failed
        raise HTTPException(status_code=503, detail=f"session_error: {e}") from e

    try:
        data = await client.get_credits_info()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"phygital_error: {e}") from e
    finally:
        try:
            await client.__aexit__(None, None, None)
        except Exception:
            pass

    members = data.get("members") or []
    if not members:
        return {"ok": True, "balance": 0.0, "currency": "credits", "is_infinity": False,
                "expires_at": None, "user_name": None}

    # Active session typically maps to first member; sum across members so multi-pool
    # accounts still show a coherent total (matches what the web UI displays in header).
    balance_total = 0.0
    any_infinity = False
    expires_at = None
    user_name = None
    for m in members:
        try:
            balance_total += float(m.get("credits_balance") or 0.0)
        except (TypeError, ValueError):
            pass
        if m.get("is_infinity"):
            any_infinity = True
        if expires_at is None and m.get("expiration_date"):
            expires_at = m.get("expiration_date")
        if user_name is None and m.get("user_name"):
            user_name = m.get("user_name")

    return {
        "ok": True,
        "balance": balance_total,
        "currency": "credits",
        "is_infinity": any_infinity,
        "expires_at": expires_at,
        "user_name": user_name,
    }
