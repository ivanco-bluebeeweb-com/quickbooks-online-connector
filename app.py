"""Extension declaration, secrets, lifecycle hooks.

WHY BYOK (bring-your-own-key), same reasoning as HubSpot/Salesforce/Google
Drive Connector. The user's QuickBooks company data (invoices, bills,
customers) lives inside THEIR OWN Intuit company -- Imperal cannot and
should not broker access to someone else's books centrally.

WHY OAUTH2 AUTHORIZATION CODE, NOT API KEY (see CONNECTOR_DISCOVERY.md
and PREPARATION.md §2, confirmed against developer.intuit.com 2026-08-29).

QuickBooks Online only supports OAuth2 ("Sign in with Intuit" /
authorization code grant) -- there is no static API key option.

WHY THE USER BRINGS THEIR OWN INTUIT DEVELOPER APP (client_id/client_secret),
SAME PATTERN AS CLIO CONNECTOR, NOT A SINGLE IMPERAL-OWNED OAUTH APP.

Registering one shared Imperal-owned Intuit app usable by every Imperal
user would require Intuit's own app-review/certification process and a
single fixed redirect_uri Imperal would have to host and maintain
centrally. Following Clio Connector's exact precedent instead: each user
registers their own free Intuit Developer app (developer.intuit.com),
gets their own client_id/client_secret, and points its redirect URI at
Imperal's OAuth callback for this connector. `connect_quickbooks` collects
client_id/client_secret once, builds the authorize URL, and stores a
PENDING record (state-keyed); the callback webhook does the code-for-token
exchange server-side and writes the finished connection (access_token/
refresh_token/realm_id) into `quickbooks_connections`.

WHY ONE SECRET HOLDING A JSON ARRAY, NOT A FLAT SECRET FOR "the" COMPANY.

QuickBooks supports exactly one company per OAuth authorization, but a
single Imperal user may run several companies (agency bookkeeping several
clients, or personal + business). Same multi-connection pattern as
HubSpot/Google Drive/Salesforce/Clio Connector.
"""
from __future__ import annotations

from imperal_sdk import ChatExtension, Extension

ext = Extension(
    "quickbooks-online-connector",
    version="0.1.0",
    display_name="QuickBooks Online",
    icon="icon.svg",
    capabilities=["quickbooks:read", "quickbooks:write"],
    description=(
        "Connect your own QuickBooks Online company (Intuit OAuth2) to "
        "manage invoices, bills, customers, vendors, items, payments, "
        "estimates, sales receipts, credit memos, journal entries, and "
        "run reports (P&L, Balance Sheet, Cash Flow, AR/AP aging) -- full "
        "read/write plus value-add reports like cash position and "
        "overdue-invoice tracking."
    ),
)

chat = ChatExtension(
    ext,
    tool_name="quickbooks",
    description=(
        "QuickBooks Online Connector -- connect your QuickBooks company "
        "via OAuth2, then manage customers/vendors/employees/items, "
        "invoices/estimates/sales receipts/payments/credit memos, bills/"
        "bill payments/purchase orders/vendor credits, journal entries, "
        "accounts, deposits, transfers, run financial reports (P&L, "
        "Balance Sheet, Cash Flow, AR/AP aging, Trial Balance), attach "
        "files, and check company info/preferences."
    ),
)

# Credentials never flow through the LLM beyond this one setup call.
# `connect_quickbooks` collects the Intuit Developer app's client_id/
# client_secret (created by the user themselves at developer.intuit.com --
# same reasoning as Clio Connector) plus a friendly label; the callback
# webhook does the code-for-token exchange server-side and stores
# access_token/refresh_token/realm_id in the Vault-encrypted secret below.
ext.secret(
    "quickbooks_connections",
    (
        "JSON array of connected QuickBooks companies: client_id/"
        "client_secret (your own Intuit Developer app), access_token, "
        "refresh_token, expiry timestamps, realm_id, company_name, label. "
        "Managed through connect_quickbooks / disconnect_quickbooks -- "
        "you should not need to edit this directly."
    ),
    required=True,
    write_mode="both",
    max_bytes=65536,
    rotation_hint_days=90,
)(lambda: None)

ext.secret(
    "quickbooks_pending",
    (
        "JSON array of in-flight QuickBooks OAuth connection attempts "
        "(client_id/client_secret captured at connect_quickbooks time, "
        "keyed by a pending id used as the OAuth `state`), consumed and "
        "removed by the callback webhook once the code-for-token exchange "
        "completes. write_mode='extension': only connector code writes "
        "this, never the Panel UI directly."
    ),
    required=False,
    write_mode="extension",
    max_bytes=16384,
)(lambda: None)


@ext.health_check
async def health_check(ctx) -> dict:
    """Fast configuration health; no third-party call -- just confirms at
    least one company connection is stored, same shape as HubSpot/Clio
    Connector's health_check."""
    import json as _json
    raw = await ctx.secrets.get("quickbooks_connections")
    try:
        count = len(_json.loads(raw)) if raw else 0
    except Exception:
        count = 0
    return {
        "healthy": True,
        "detail": (
            f"{count} QuickBooks compan{'y' if count == 1 else 'ies'} connected."
            if count else "Not connected yet -- run connect_quickbooks."
        ),
    }
