"""QuickBooks Online Accounting API HTTP client -- OAuth2 Bearer token
auth, thin wrapper over the /v3/company/{realmId}/... REST-ish API, plus
the Intuit OAuth2 token endpoints (authorize/exchange/refresh). Follows
the exact same shape as Clio Connector's clio_client.py (fail()-dict error
taxonomy, ClientFail, generic request()).

WHY 401 vs 403 vs 429/5xx ARE HANDLED DIFFERENTLY, same principle as
HubSpot/Salesforce/Clio Connector's clients.

A 401 means the access token itself is rejected (expired -- QBO access
tokens live only 1 hour, so this should be rare if proactive refresh runs
correctly; if it still happens, the refresh_token itself may be revoked/
expired at 100 days of inactivity). A 403 means the token is valid but
this Intuit app/user lacks entitlement for the endpoint. QBO wraps errors
in its own {"Fault": {"Error": [{"Message":..., "Detail":..., "code":...}]}}
envelope (not a flat "message" field) -- parsed explicitly in _check_status.
"""
from __future__ import annotations

import base64
from typing import Any
from urllib.parse import urlencode

AUTHORIZE_URL = "https://appcenter.intuit.com/connect/oauth2"
TOKEN_URL = "https://oauth2.platform.intuit.com/oauth2/v1/tokens/bearer"
REVOKE_URL = "https://developer.api.intuit.com/v2/oauth2/tokens/revoke"
API_BASE = "https://quickbooks.api.intuit.com"
MINOR_VERSION = "75"
SCOPE = "com.intuit.quickbooks.accounting"

NO_CONNECTION = "QUICKBOOKS_NOT_CONNECTED"
UNAUTHORIZED = "QUICKBOOKS_UNAUTHORIZED"
FORBIDDEN = "QUICKBOOKS_FORBIDDEN"
NOT_FOUND = "QUICKBOOKS_NOT_FOUND"
RATE_LIMITED = "QUICKBOOKS_RATE_LIMITED"
BACKEND_5XX = "QUICKBOOKS_BACKEND_ERROR"
VALIDATION_FAILED = "QUICKBOOKS_VALIDATION_FAILED"
RESPONSE_UNEXPECTED = "QUICKBOOKS_RESPONSE_UNEXPECTED"
UPLOAD_FAILED = "QUICKBOOKS_UPLOAD_FAILED"

_MESSAGES = {
    NO_CONNECTION: "No QuickBooks company is connected yet.",
    UNAUTHORIZED: "QuickBooks rejected this connection. Reconnect the company and try again.",
    FORBIDDEN: "This QuickBooks connection is not entitled for that action.",
    NOT_FOUND: "QuickBooks has no such record, or this connection cannot access it.",
    RATE_LIMITED: "QuickBooks rate-limited this request. Try again shortly.",
    BACKEND_5XX: "QuickBooks had a server-side problem. Try again shortly.",
    VALIDATION_FAILED: "QuickBooks rejected the request as invalid.",
    RESPONSE_UNEXPECTED: "QuickBooks returned a response the connector could not safely interpret.",
    UPLOAD_FAILED: "Could not upload the attachment to QuickBooks.",
}


class ClientFail(Exception):
    def __init__(self, payload: dict):
        self.payload = payload
        super().__init__(payload.get("detail", ""))


def fail(code: str, detail: str = "") -> dict:
    return {
        "ok": False,
        "error_code": code,
        "error": _MESSAGES.get(code, "QuickBooks request failed."),
        "detail": detail,
    }


def parse_json_object(raw: str) -> tuple[bool, Any]:
    """Parse a caller-supplied JSON object string. Returns (True, dict) on
    success, or (False, error_message_str) on failure -- used by
    handlers_entities.py's create_entity/update_entity so a malformed
    fields_json produces a clear VALIDATION_FAILED instead of a raw
    JSONDecodeError traceback."""
    import json as _json
    if not raw or not raw.strip():
        return False, "empty fields_json"
    try:
        data = _json.loads(raw)
    except (TypeError, ValueError) as exc:
        return False, str(exc)
    if not isinstance(data, dict):
        return False, "fields_json must be a JSON object, not a list/scalar"
    return True, data


def build_authorize_url(client_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "client_id": client_id,
        "response_type": "code",
        "scope": SCOPE,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def _basic_auth(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()


async def exchange_code_for_token(ctx, client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    resp = await ctx.http.post(
        TOKEN_URL,
        headers={
            "Authorization": _basic_auth(client_id, client_secret),
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
    )
    if resp.status_code != 200:
        body = resp.body if isinstance(resp.body, dict) else {}
        return fail(UNAUTHORIZED, body.get("error_description", f"HTTP {resp.status_code}"))
    body = resp.body if isinstance(resp.body, dict) else {}
    return {
        "ok": True,
        "access_token": body.get("access_token", ""),
        "refresh_token": body.get("refresh_token", ""),
        "expires_in": body.get("expires_in", 3600),
        "x_refresh_token_expires_in": body.get("x_refresh_token_expires_in", 8640000),
    }


async def refresh_access_token(ctx, client_id: str, client_secret: str, refresh_token: str) -> dict:
    resp = await ctx.http.post(
        TOKEN_URL,
        headers={
            "Authorization": _basic_auth(client_id, client_secret),
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
    )
    if resp.status_code != 200:
        body = resp.body if isinstance(resp.body, dict) else {}
        return fail(UNAUTHORIZED, body.get("error_description", f"HTTP {resp.status_code}"))
    body = resp.body if isinstance(resp.body, dict) else {}
    return {
        "ok": True,
        "access_token": body.get("access_token", ""),
        "refresh_token": body.get("refresh_token", refresh_token),
        "expires_in": body.get("expires_in", 3600),
        "x_refresh_token_expires_in": body.get("x_refresh_token_expires_in", 8640000),
    }


async def revoke_token(ctx, client_id: str, client_secret: str, token: str) -> dict:
    resp = await ctx.http.post(
        REVOKE_URL,
        headers={
            "Authorization": _basic_auth(client_id, client_secret),
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        json={"token": token},
    )
    if resp.status_code not in (200, 400):
        return fail(RESPONSE_UNEXPECTED, f"revoke HTTP {resp.status_code}")
    return {"ok": True}


def _headers(access_token: str, extra: dict | None = None) -> dict:
    h = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    if extra:
        h.update(extra)
    return h


def _check_status(resp, action: str) -> Any:
    if resp.status_code in (200, 201, 202):
        return resp.body if isinstance(resp.body, (dict, list)) else {}
    if resp.status_code == 204:
        return {}
    body = resp.body if isinstance(resp.body, dict) else {}
    detail = ""
    fault = body.get("Fault") if isinstance(body, dict) else None
    if isinstance(fault, dict):
        errors = fault.get("Error") or []
        if errors:
            first = errors[0] if isinstance(errors[0], dict) else {}
            detail = f"{first.get('Message', '')} {first.get('Detail', '')}".strip()
    if resp.status_code == 401:
        raise ClientFail(fail(UNAUTHORIZED, f"{action}: {detail}" if detail else action))
    if resp.status_code == 403:
        raise ClientFail(fail(FORBIDDEN, f"{action}: {detail}" if detail else action))
    if resp.status_code == 404:
        raise ClientFail(fail(NOT_FOUND, f"{action}: {detail}" if detail else action))
    if resp.status_code == 429:
        raise ClientFail(fail(RATE_LIMITED, action))
    if resp.status_code >= 500:
        raise ClientFail(fail(BACKEND_5XX, action))
    if resp.status_code in (400, 422):
        raise ClientFail(fail(VALIDATION_FAILED, f"{action}: {detail}" if detail else action))
    raise ClientFail(fail(RESPONSE_UNEXPECTED, f"{action}: HTTP {resp.status_code} {detail}"))


async def request(
    ctx, conn: dict, method: str, path: str, *,
    json_body: dict | None = None, params: dict | None = None, action: str = "",
) -> Any:
    """Generic authenticated REST call against QuickBooks Online Accounting
    API v3, scoped to conn['realm_id']. Access token must already be fresh
    -- callers use handlers_connection.ensure_fresh_token() first."""
    access_token = conn.get("access_token", "")
    realm_id = conn.get("realm_id", "")
    if not access_token or not realm_id:
        raise ClientFail(fail(NO_CONNECTION))
    url = f"{API_BASE}/v3/company/{realm_id}{path}"
    all_params = {"minorversion": MINOR_VERSION}
    if params:
        all_params.update(params)
    headers = _headers(access_token, {"Content-Type": "application/json"} if json_body is not None else None)
    if method == "GET":
        resp = await ctx.http.get(url, headers=headers, params=all_params)
    elif method == "POST":
        resp = await ctx.http.post(url, headers=headers, params=all_params, json=json_body or {})
    else:
        raise ClientFail(fail(RESPONSE_UNEXPECTED, f"unsupported method {method}"))
    return _check_status(resp, action or f"{method} {path}")


async def query(ctx, conn: dict, sql: str) -> dict:
    access_token = conn.get("access_token", "")
    realm_id = conn.get("realm_id", "")
    if not access_token or not realm_id:
        raise ClientFail(fail(NO_CONNECTION))
    url = f"{API_BASE}/v3/company/{realm_id}/query"
    headers = _headers(access_token, {"Content-Type": "application/text"})
    resp = await ctx.http.post(url, headers=headers, params={"minorversion": MINOR_VERSION}, data=sql)
    return _check_status(resp, f"query: {sql[:80]}")


async def get_company_info(ctx, conn: dict) -> dict:
    realm_id = conn.get("realm_id", "")
    return await request(ctx, conn, "GET", f"/companyinfo/{realm_id}", action="get_company_info")
