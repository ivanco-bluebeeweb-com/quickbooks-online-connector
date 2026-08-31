"""Connection management for QuickBooks Online Connector: connect/
disconnect/list, OAuth callback webhook, proactive token refresh -- same
shape as Clio Connector's handlers_connection.py (JSON array under one
secret, plus a pending-connections secret keyed by OAuth `state`).

WHY THE FLOW IS SPLIT connect_quickbooks (tool) + handle_oauth_callback
(webhook), SAME REASONING AS CLIO CONNECTOR.

Intuit only offers Authorization Code Grant -- there is no way to
validate credentials without a real user browser redirect and consent.
`connect_quickbooks` registers the client_id/client_secret as a PENDING
connection (keyed by a pending id used as OAuth `state`) and hands back
the authorize URL; `handle_oauth_callback` finishes the exchange once
Intuit redirects back with `code`+`realmId`+`state`.
"""
from __future__ import annotations

import json
import time as _time
import uuid

from imperal_sdk import ActionResult

import quickbooks_client as qc
from app import ext, chat
from schemas import (
    NoParams,
    ConnectQuickbooksParams, ConsentUrlResult,
    ProviderConnection, ProviderConnectionList,
    DisconnectQuickbooksParams, DeleteResult,
)

_SECRET_NAME = "quickbooks_connections"
_PENDING_SECRET = "quickbooks_pending"


async def _load_connections(ctx) -> list[dict]:
    raw = await ctx.secrets.get(_SECRET_NAME)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


async def _save_connections(ctx, connections: list[dict]) -> None:
    await ctx.secrets.set(_SECRET_NAME, json.dumps(connections))


async def _load_pending(ctx) -> list[dict]:
    raw = await ctx.secrets.get(_PENDING_SECRET)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


async def _save_pending(ctx, pending: list[dict]) -> None:
    await ctx.secrets.set(_PENDING_SECRET, json.dumps(pending))


async def resolve_connection(ctx, connection_id: str = "") -> dict | None:
    connections = await _load_connections(ctx)
    if not connections:
        return None
    if connection_id:
        for c in connections:
            if c.get("id") == connection_id:
                return c
        return None
    return connections[0]


async def ensure_fresh_token(ctx, conn: dict) -> dict:
    """Proactively refresh the access_token if it's within 60s of expiry
    (QBO access tokens live only 1 hour -- reactive refresh-on-401 alone
    would mean far too many failed-then-retried calls)."""
    expires_at = int(conn.get("expires_at", 0) or 0)
    if expires_at and expires_at - int(_time.time()) > 60:
        return conn

    refresh_token = conn.get("refresh_token", "")
    if not refresh_token:
        return conn

    result = await qc.refresh_access_token(ctx, conn["client_id"], conn["client_secret"], refresh_token)
    if not result.get("ok"):
        return conn  # let the ensuing 401 drive the "reconnect" message

    conn["access_token"] = result["access_token"]
    conn["refresh_token"] = result.get("refresh_token", refresh_token)
    conn["expires_at"] = int(_time.time()) + int(result.get("expires_in", 3600))
    conn["refresh_expires_at"] = int(_time.time()) + int(result.get("x_refresh_token_expires_in", 8640000))

    connections = await _load_connections(ctx)
    for i, c in enumerate(connections):
        if c.get("id") == conn.get("id"):
            connections[i] = conn
            break
    await _save_connections(ctx, connections)
    return conn


def _connection_to_entity(c: dict) -> ProviderConnection:
    return ProviderConnection(
        id=c.get("id", ""),
        title=c.get("label") or c.get("company_name") or "QuickBooks company",
        connected=True,
        detail=f"realm {c.get('realm_id', '') or '—'}",
        realm_id=c.get("realm_id", ""),
        company_name=c.get("company_name", ""),
    )


async def resolve_or_error(ctx, connection_id: str = ""):
    conn = await resolve_connection(ctx, connection_id)
    if not conn:
        return None, ActionResult.error(
            "No QuickBooks connection found. Connect one with connect_quickbooks first "
            "and open the returned authorize_url to finish the one-time login.",
            code="QUICKBOOKS_NOT_CONNECTED",
        )
    conn = await ensure_fresh_token(ctx, conn)
    return conn, None


@chat.function(
    "connect_quickbooks",
    "Start connecting your QuickBooks Online company: register your Intuit Developer app's Client ID/"
    "Client Secret, then get back a one-time browser authorize_url. Open it, sign in with Intuit, pick "
    "a company, and approve access -- QuickBooks redirects back here automatically and the connection "
    "finishes itself, no further action needed.",
    action_type="write",
    chain_callable=True,
    data_model=ConsentUrlResult,
    event="quickbooks-connector.connect",
    effects=["quickbooks.connection.pending"],
)
async def connect_quickbooks(ctx, params: ConnectQuickbooksParams) -> ActionResult:
    """Register the user's own Intuit Developer app credentials and hand
    back a one-time browser authorize_url. The actual connection is
    finished by handle_oauth_callback once Intuit redirects back."""
    if not params.client_id.strip() or not params.client_secret.strip():
        return ActionResult.error(
            "Both the Intuit Developer app's Client ID and Client Secret are required.",
            code="QUICKBOOKS_MISSING_FIELDS",
        )
    pending_id = str(uuid.uuid4())
    redirect_uri = ctx.webhook_url("callback")
    pending = {
        "id": pending_id,
        "label": params.label.strip(),
        "client_id": params.client_id.strip(),
        "client_secret": params.client_secret.strip(),
        "redirect_uri": redirect_uri,
        "owner_user_id": getattr(ctx.user, "imperal_id", ""),
        "owner_tenant_id": getattr(ctx.user, "tenant_id", ""),
    }
    all_pending = await _load_pending(ctx)
    all_pending.append(pending)
    await _save_pending(ctx, all_pending)

    authorize_url = qc.build_authorize_url(params.client_id.strip(), redirect_uri, pending_id)
    return ActionResult.success(ConsentUrlResult(authorize_url=authorize_url, redirect_uri=redirect_uri)), summary="Quickbooks connected."


@ext.webhook("callback")
async def handle_oauth_callback(ctx, headers, body, query_params):
    """Intuit's OAuth redirect target: exchanges `code` for tokens and
    finishes the pending connection started by connect_quickbooks. Runs as
    user_id="__webhook__" (nobody is logged in when Intuit redirects the
    browser here), so the pending connection is looked up system-wide by
    the `state` value (the pending id connect_quickbooks generated)."""
    error = query_params.get("error")
    state = query_params.get("state", "")
    code = query_params.get("code", "")
    realm_id = query_params.get("realmId", "")

    if error:
        return {"status_code": 200, "body": f"QuickBooks authorization failed: {error}. Close this tab and try connect_quickbooks again."}
    if not state or not code or not realm_id:
        return {"status_code": 400, "body": "Missing code/state/realmId."}

    all_pending = await _load_pending(ctx)
    pending = next((p for p in all_pending if p.get("id") == state), None)
    if not pending:
        return {"status_code": 400, "body": "Unknown or expired connection request. Run connect_quickbooks again."}

    result = await qc.exchange_code_for_token(
        ctx, pending["client_id"], pending["client_secret"], code, pending["redirect_uri"],
    )
    if not result.get("ok"):
        return {"status_code": 200, "body": f"Could not finish connecting QuickBooks: {result.get('error', 'unknown error')}. Close this tab and try connect_quickbooks again."}

    conn = {
        "id": str(uuid.uuid4()),
        "label": pending.get("label", ""),
        "client_id": pending["client_id"],
        "client_secret": pending["client_secret"],
        "realm_id": realm_id,
        "access_token": result["access_token"],
        "refresh_token": result["refresh_token"],
        "expires_at": int(_time.time()) + int(result.get("expires_in", 3600)),
        "refresh_expires_at": int(_time.time()) + int(result.get("x_refresh_token_expires_in", 8640000)),
        "company_name": "",
    }

    # Best-effort: fetch the company name right away so the sidebar shows
    # something more useful than a bare realm id.
    try:
        info = await qc.get_company_info(ctx, conn)
        company = (info or {}).get("CompanyInfo", {})
        conn["company_name"] = company.get("CompanyName", "")
    except Exception:
        pass

    all_pending = [p for p in all_pending if p.get("id") != state]
    await _save_pending(ctx, all_pending)

    connections = await _load_connections(ctx)
    connections.append(conn)
    await _save_connections(ctx, connections)

    return {"status_code": 200, "body": "QuickBooks connected! You can close this tab and go back to Imperal."}


@chat.function(
    "list_connections",
    "List the connected QuickBooks Online companies and whether each saved connection still works.",
    action_type="read",
    chain_callable=True,
    data_model=ProviderConnectionList,
)
async def list_connections(ctx, params: NoParams) -> ActionResult:
    """List every connected QuickBooks company for this account."""
    connections = await _load_connections(ctx)
    return ActionResult.success(ProviderConnectionList(connections=[_connection_to_entity(c) for c in connections])), summary="Connections listed."


@chat.function(
    "disconnect_quickbooks",
    "Disconnect a QuickBooks Online company: deletes the saved connection. Nothing in QuickBooks itself is changed.",
    action_type="destructive",
    chain_callable=True,
    data_model=DeleteResult,
    event="quickbooks-connector.disconnect",
    effects=["quickbooks.connection.removed"],
)
async def disconnect_quickbooks(ctx, params: DisconnectQuickbooksParams) -> ActionResult:
    """Delete one saved QuickBooks connection by id. Idempotent-ish: fails
    clearly if the connection_id no longer exists."""
    connections = await _load_connections(ctx)
    remaining = [c for c in connections if c.get("id") != params.connection_id]
    if len(remaining) == len(connections):
        return ActionResult.error("No such QuickBooks connection.", code="QUICKBOOKS_NOT_CONNECTED")
    await _save_connections(ctx, remaining)
    return ActionResult.success(DeleteResult(deleted=True, detail="QuickBooks connection removed.")), summary="Quickbooks disconnected."
