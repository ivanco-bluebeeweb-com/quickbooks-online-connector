"""Query, Reports, company info, attachments, and value-add reports for
QuickBooks Online Connector -- same "value-add on top of raw API" shape as
HubSpot Connector's handlers_value_add.py / MuleSoft Connector's
audit_cloudhub_environment.
"""
from __future__ import annotations

from imperal_sdk import ActionResult

import quickbooks_client as qc
from app import chat
from handlers_connection import resolve_or_error
from schemas import (
    RunQueryParams, QueryResult,
    RunReportParams, ReportResult,
    GetCompanyInfoParams, CompanyInfo,
    CashPositionReport,
    OverdueReportParams, OverdueInvoicesReport,
    AttachmentUploadParams, EntityDetail,
)


@chat.function(
    "run_query",
    "Run a full QuickBooks SQL-like query against any entity, e.g. \"SELECT * FROM Invoice WHERE Balance > '0' "
    "ORDERBY TxnDate DESC MAXRESULTS 50\". The most flexible way to filter/sort/limit any QuickBooks data.",
    action_type="read", chain_callable=True, data_model=QueryResult,
)
async def run_query(ctx, params: RunQueryParams) -> ActionResult:
    """Run a full QuickBooks SQL-like query string and flatten every returned row list."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if not conn:
        return err
    result = await qc.request(ctx, conn, "GET", "/query", params={"query": params.query}, action="run query")
    qr = result.get("QueryResponse", {}) if isinstance(result, dict) else {}
    rows: list[dict] = []
    for key, val in qr.items():
        if key in ("startPosition", "maxResults", "totalCount"):
            continue
        if isinstance(val, list):
            rows.extend(val)
    return ActionResult.success(QueryResult(rows=rows, total_shown=len(rows))), summary="Query run requested."


@chat.function(
    "run_report",
    "Run a QuickBooks report by name -- ProfitAndLoss, BalanceSheet, CashFlow, AgedReceivables, AgedPayables, "
    "GeneralLedger, TrialBalance, CustomerBalance, VendorBalance, TransactionList -- optionally scoped to a date "
    "range and/or grouped by Month/Quarter/Customer/Vendor.",
    action_type="read", chain_callable=True, data_model=ReportResult,
)
async def run_report(ctx, params: RunReportParams) -> ActionResult:
    """Run a named QuickBooks report (P&L, Balance Sheet, aging, etc), optionally date-scoped/grouped."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if not conn:
        return err
    query_params: dict = {}
    if params.start_date.strip():
        query_params["start_date"] = params.start_date.strip()
    if params.end_date.strip():
        query_params["end_date"] = params.end_date.strip()
    if params.summarize_by.strip():
        query_params["summarize_column_by"] = params.summarize_by.strip()
    result = await qc.request(
        ctx, conn, "GET", f"/reports/{params.report_name}",
        params=query_params or None, action=f"run report {params.report_name}",
    )
    return ActionResult.success(ReportResult(report_name=params.report_name, data=result if isinstance(result, dict) else {})), summary="Report run requested."


@chat.function(
    "get_company_info",
    "Read the connected QuickBooks company's own profile: legal name, country, fiscal year start, address.",
    action_type="read", chain_callable=True, data_model=CompanyInfo,
)
async def get_company_info(ctx, params: GetCompanyInfoParams) -> ActionResult:
    """Read the connected QuickBooks company's own profile."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if not conn:
        return err
    result = await qc.request(
        ctx, conn, "GET", f"/companyinfo/{conn.get('realm_id', '')}", action="get company info",
    )
    ci = result.get("CompanyInfo", result) if isinstance(result, dict) else {}
    addr = ci.get("CompanyAddr", {}) or {}
    address = ", ".join(filter(None, [
        addr.get("Line1", ""), addr.get("City", ""), addr.get("CountrySubDivisionCode", ""), addr.get("PostalCode", ""),
    ]))
    return ActionResult.success(CompanyInfo(
        company_name=ci.get("CompanyName", ""),
        legal_name=ci.get("LegalName", ""),
        country=ci.get("Country", ""),
        fiscal_year_start_month=ci.get("FiscalYearStartMonth", ""),
        email=(ci.get("Email", {}) or {}).get("Address", ""),
        address=address,
        realm_id=conn.get("realm_id", ""),
    )), summary="Company info retrieved."


@chat.function(
    "upload_attachment",
    "Attach a file to an existing QuickBooks transaction (e.g. a receipt PDF to a Bill, a signed contract to an "
    "Invoice) by fetching it from a publicly reachable URL and uploading it server-side.",
    action_type="write", chain_callable=True, data_model=EntityDetail,
    event="quickbooks-connector.upload_attachment",
    effects=["quickbooks.attachment.uploaded"],
)
async def upload_attachment(ctx, params: AttachmentUploadParams) -> ActionResult:
    """Attach a file (fetched from a public URL) to an existing QuickBooks transaction."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if not conn:
        return err
    result = await qc.upload_attachment(
        ctx, conn, entity=params.entity, entity_id=params.entity_id,
        file_url=params.file_url, file_name=params.file_name,
    )
    return ActionResult.success(EntityDetail(entity="Attachable", data=result)), summary="Upload attachment done."


@chat.function(
    "get_cash_position",
    "Value-add report: one-glance cash position for the connected company -- bank account balances, total cash, "
    "and unpaid/overdue invoice and bill totals, so you see the real financial picture in one call.",
    action_type="read", chain_callable=True, data_model=CashPositionReport,
)
async def get_cash_position(ctx, params: GetCompanyInfoParams) -> ActionResult:
    """Value-add: aggregate bank balances plus unpaid/overdue AR and AP into one snapshot."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if not conn:
        return err

    accounts_result = await qc.request(
        ctx, conn, "GET", "/query",
        params={"query": "SELECT * FROM Account WHERE AccountType = 'Bank' MAXRESULTS 100"},
        action="list bank accounts",
    )
    bank_rows = (accounts_result.get("QueryResponse", {}) or {}).get("Account", []) if isinstance(accounts_result, dict) else []
    bank_balances = [{"name": a.get("Name", ""), "balance": a.get("CurrentBalance", 0)} for a in bank_rows]
    total_cash = sum(float(a.get("balance", 0) or 0) for a in bank_balances)

    inv_result = await qc.request(
        ctx, conn, "GET", "/query",
        params={"query": "SELECT * FROM Invoice WHERE Balance > '0' MAXRESULTS 200"},
        action="list unpaid invoices",
    )
    invoices = (inv_result.get("QueryResponse", {}) or {}).get("Invoice", []) if isinstance(inv_result, dict) else []
    unpaid_invoices_total = sum(float(i.get("Balance", 0) or 0) for i in invoices)

    import datetime as _dt
    today = _dt.date.today().isoformat()
    overdue_invoices = [i for i in invoices if i.get("DueDate", "9999-99-99") < today]
    overdue_invoices_total = sum(float(i.get("Balance", 0) or 0) for i in overdue_invoices)

    bill_result = await qc.request(
        ctx, conn, "GET", "/query",
        params={"query": "SELECT * FROM Bill WHERE Balance > '0' MAXRESULTS 200"},
        action="list unpaid bills",
    )
    bills = (bill_result.get("QueryResponse", {}) or {}).get("Bill", []) if isinstance(bill_result, dict) else []
    unpaid_bills_total = sum(float(b.get("Balance", 0) or 0) for b in bills)
    overdue_bills = [b for b in bills if b.get("DueDate", "9999-99-99") < today]
    overdue_bills_total = sum(float(b.get("Balance", 0) or 0) for b in overdue_bills)

    return ActionResult.success(CashPositionReport(
        connection_id=conn.get("id", ""),
        bank_balances=bank_balances,
        total_cash=round(total_cash, 2),
        unpaid_invoices_total=round(unpaid_invoices_total, 2),
        unpaid_invoices_count=len(invoices),
        overdue_invoices_total=round(overdue_invoices_total, 2),
        overdue_invoices_count=len(overdue_invoices),
        unpaid_bills_total=round(unpaid_bills_total, 2),
        unpaid_bills_count=len(bills),
        overdue_bills_total=round(overdue_bills_total, 2),
        overdue_bills_count=len(overdue_bills),
    )), summary="Cash position retrieved."


@chat.function(
    "get_overdue_invoices",
    "Value-add report: flag every unpaid invoice overdue by at least a given number of days, sorted worst-first "
    "-- the AR collections list.",
    action_type="read", chain_callable=True, data_model=OverdueInvoicesReport,
)
async def get_overdue_invoices(ctx, params: OverdueReportParams) -> ActionResult:
    """Value-add: flag every unpaid invoice overdue by at least N days, worst-first."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if not conn:
        return err
    result = await qc.request(
        ctx, conn, "GET", "/query",
        params={"query": "SELECT * FROM Invoice WHERE Balance > '0' MAXRESULTS 1000"},
        action="list unpaid invoices",
    )
    invoices = (result.get("QueryResponse", {}) or {}).get("Invoice", []) if isinstance(result, dict) else []

    import datetime as _dt
    today = _dt.date.today()
    flagged = []
    for inv in invoices:
        due = inv.get("DueDate", "")
        if not due:
            continue
        try:
            due_date = _dt.date.fromisoformat(due)
        except ValueError:
            continue
        days_over = (today - due_date).days
        if days_over >= params.min_days_overdue:
            flagged.append({
                "id": inv.get("Id", ""),
                "doc_number": inv.get("DocNumber", ""),
                "customer": (inv.get("CustomerRef", {}) or {}).get("name", ""),
                "balance": inv.get("Balance", 0),
                "due_date": due,
                "days_overdue": days_over,
            })
    flagged.sort(key=lambda r: r["days_overdue"], reverse=True)
    return ActionResult.success(OverdueInvoicesReport(
        connection_id=conn.get("id", ""),
        count=len(flagged),
        total_amount=round(sum(float(r["balance"] or 0) for r in flagged), 2),
        invoices=flagged,
    )), summary="Overdue invoices retrieved."
