"""Pydantic params/result models for QuickBooks Online Connector.

All params models are module-scope (V17 federal invariant, same rule as
HubSpot/Salesforce/Clio Connector's schemas.py).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class NoParams(BaseModel):
    """Explicit empty params model -- V17 disallows untyped handlers."""
    pass


class ConnectionScoped(BaseModel):
    connection_id: str = Field(
        "",
        description="Which connected QuickBooks company to use (see list_connections). Omit if only one company is connected.",
    )


# ──────────────────────────────────────────────────────────────────────────
# Connection
# ──────────────────────────────────────────────────────────────────────────


class ConnectQuickbooksParams(BaseModel):
    client_id: str = Field("", description="Your Intuit Developer app's Client ID (developer.intuit.com > My Apps > your app > Keys & OAuth).")
    client_secret: str = Field("", description="Your Intuit Developer app's Client Secret.")
    label: str = Field("", description="Optional friendly label for this company connection, e.g. 'Acme Corp books'.")


class ConsentUrlResult(BaseModel):
    authorize_url: str = Field(description="Open this URL in a browser to sign in with Intuit, pick a company, and approve access. QuickBooks redirects back here automatically once you approve.")
    redirect_uri: str = Field(description="The callback URL registered for this attempt (must match a Redirect URI configured on your Intuit app).")


class ProviderConnection(BaseModel):
    id: str
    title: str = ""
    connected: bool = True
    detail: str = ""
    realm_id: str = ""
    company_name: str = ""


class ProviderConnectionList(BaseModel):
    connections: list[ProviderConnection] = Field(default_factory=list)


class DisconnectQuickbooksParams(BaseModel):
    connection_id: str = Field(..., description="The connection id to disconnect (see list_connections).")


class DeleteResult(BaseModel):
    deleted: bool = True
    detail: str = ""


# ──────────────────────────────────────────────────────────────────────────
# Generic entity CRUD (Customer, Vendor, Employee, Item, Invoice, Bill, ...)
# ──────────────────────────────────────────────────────────────────────────


class ListEntitiesParams(ConnectionScoped):
    entity: str = Field(..., description="QuickBooks entity name, e.g. 'Customer', 'Vendor', 'Employee', 'Item', 'Invoice', 'Bill', 'Payment', 'Estimate', 'SalesReceipt', 'CreditMemo', 'JournalEntry', 'Purchase', 'PurchaseOrder', 'VendorCredit', 'Deposit', 'Transfer', 'Account', 'Class', 'Department', 'TaxCode', 'Term', 'Attachable'.")
    where: str = Field("", description="Optional SQL-like WHERE clause fragment, e.g. \"Active = true\" or \"Balance > '100'\".")
    max_results: int = Field(100, description="Max rows to return (QuickBooks caps at 1000 per page).")
    start_position: int = Field(1, description="1-based pagination offset.")


class EntityRow(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)


class EntityList(BaseModel):
    entity: str = ""
    rows: list[dict[str, Any]] = Field(default_factory=list)
    total_shown: int = 0


class GetEntityParams(ConnectionScoped):
    entity: str = Field(..., description="QuickBooks entity name, e.g. 'Invoice'.")
    entity_id: str = Field(..., description="The entity's Id.")


class EntityDetail(BaseModel):
    entity: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class CreateEntityParams(ConnectionScoped):
    entity: str = Field(..., description="QuickBooks entity name to create, e.g. 'Invoice', 'Customer', 'Bill'.")
    fields_json: str = Field(..., description="JSON object of the entity's fields exactly as QuickBooks expects (e.g. '{\"DisplayName\":\"Acme Co\"}' for a Customer, or a full Invoice body with Line items).")


class UpdateEntityParams(ConnectionScoped):
    entity: str = Field(..., description="QuickBooks entity name to update.")
    entity_id: str = Field(..., description="The entity's Id.")
    sync_token: str = Field(..., description="The entity's current SyncToken (from get_entity) -- QuickBooks requires this for optimistic concurrency on every update.")
    fields_json: str = Field(..., description="JSON object of the fields to change, merged onto the existing entity (sparse update).")


class DeleteEntityParams(ConnectionScoped):
    entity: str = Field(..., description="QuickBooks entity name to void/delete, e.g. 'Invoice', 'Bill', 'Payment' (most QBO transaction entities support delete=true instead of true deletion).")
    entity_id: str = Field(..., description="The entity's Id.")
    sync_token: str = Field(..., description="The entity's current SyncToken (from get_entity).")


class SendEntityParams(ConnectionScoped):
    entity: str = Field(..., description="Entity type to email, e.g. 'Invoice' or 'Estimate'.")
    entity_id: str = Field(..., description="The entity's Id.")
    send_to: str = Field("", description="Override recipient email address. Omit to use the entity's own BillEmail.")


class VoidEntityParams(ConnectionScoped):
    entity: str = Field(..., description="Entity type to void, e.g. 'Invoice', 'SalesReceipt', 'Payment'.")
    entity_id: str = Field(..., description="The entity's Id.")
    sync_token: str = Field(..., description="The entity's current SyncToken.")


# ──────────────────────────────────────────────────────────────────────────
# Query
# ──────────────────────────────────────────────────────────────────────────


class RunQueryParams(ConnectionScoped):
    query: str = Field(..., description="A full QuickBooks SQL-like query string, e.g. \"SELECT * FROM Invoice WHERE Balance > '0' ORDERBY TxnDate DESC MAXRESULTS 50\".")


class QueryResult(BaseModel):
    rows: list[dict[str, Any]] = Field(default_factory=list)
    total_shown: int = 0


# ──────────────────────────────────────────────────────────────────────────
# Reports
# ──────────────────────────────────────────────────────────────────────────


class RunReportParams(ConnectionScoped):
    report_name: str = Field(..., description="QuickBooks report name: 'ProfitAndLoss', 'BalanceSheet', 'CashFlow', 'AgedReceivables', 'AgedPayables', 'GeneralLedger', 'TrialBalance', 'CustomerBalance', 'VendorBalance', 'TransactionList'.")
    start_date: str = Field("", description="Report start date YYYY-MM-DD. Omit for report defaults.")
    end_date: str = Field("", description="Report end date YYYY-MM-DD. Omit for report defaults.")
    summarize_by: str = Field("", description="Optional column grouping, e.g. 'Month', 'Quarter', 'Customer', 'Vendor'.")


class ReportResult(BaseModel):
    report_name: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────────
# Value-add
# ──────────────────────────────────────────────────────────────────────────


class CashPositionReport(BaseModel):
    connection_id: str = ""
    bank_balances: list[dict[str, Any]] = Field(default_factory=list)
    total_cash: float = 0.0
    unpaid_invoices_total: float = 0.0
    unpaid_invoices_count: int = 0
    overdue_invoices_total: float = 0.0
    overdue_invoices_count: int = 0
    unpaid_bills_total: float = 0.0
    unpaid_bills_count: int = 0
    overdue_bills_total: float = 0.0
    overdue_bills_count: int = 0


class OverdueReportParams(ConnectionScoped):
    min_days_overdue: int = Field(1, description="Only flag invoices/bills overdue by at least this many days.")


class OverdueInvoicesReport(BaseModel):
    connection_id: str = ""
    count: int = 0
    total_amount: float = 0.0
    invoices: list[dict[str, Any]] = Field(default_factory=list)


class GetCompanyInfoParams(ConnectionScoped):
    pass


class CompanyInfo(BaseModel):
    company_name: str = ""
    legal_name: str = ""
    country: str = ""
    fiscal_year_start_month: str = ""
    email: str = ""
    address: str = ""
    realm_id: str = ""


class AttachmentUploadParams(ConnectionScoped):
    entity: str = Field(..., description="Entity type to attach the file to, e.g. 'Invoice', 'Bill'.")
    entity_id: str = Field(..., description="The entity's Id to attach the file to.")
    file_url: str = Field(..., description="A publicly reachable https:// URL of the file to attach (fetched and uploaded server-side).")
    file_name: str = Field(..., description="Filename to store, including extension, e.g. 'receipt.pdf'.")
