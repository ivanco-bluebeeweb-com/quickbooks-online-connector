"""Generic entity CRUD + SQL-like query for QuickBooks Online Connector --
one layer covering Customer/Vendor/Employee/Item/Invoice/Bill/Payment/
Estimate/SalesReceipt/CreditMemo/JournalEntry/Purchase/PurchaseOrder/
VendorCredit/Deposit/Transfer/Account/Class/Department/TaxCode/Term/
Attachable and any other QBO entity, same "one generic layer + named
convenience wrappers" shape as HubSpot Connector's CRM Objects handling.

WHY GENERIC ENTITY NAME (free text), NOT AN ENUM PER TOOL.

QuickBooks Online's Accounting API is genuinely uniform: every entity
type shares the same /v3/company/{realmId}/{entity}, .../{entity}/{id},
sparse-update-via-POST-with-sync_token, and /query shapes (confirmed
developer.intuit.com/app/developer/qbo/docs/learn/rest-api-features,
2026-08-29). A fixed enum would silently break coverage the moment Intuit
adds a new entity type or a user needs one this connector's author didn't
anticipate.
"""
from __future__ import annotations

from imperal_sdk import ActionResult

import quickbooks_client as qc
from app import chat
from handlers_connection import resolve_or_error
from schemas import (
    ListEntitiesParams, EntityList,
    GetEntityParams, EntityDetail,
    CreateEntityParams,
    UpdateEntityParams,
    DeleteEntityParams, DeleteResult,
    SendEntityParams,
    VoidEntityParams,
)


_LIST_DESC = (
    "List QuickBooks records of any entity type (Customer, Vendor, Employee, Item, Invoice, Bill, "
    "Payment, Estimate, SalesReceipt, CreditMemo, JournalEntry, Purchase, PurchaseOrder, VendorCredit, "
    "Deposit, Transfer, Account, Class, Department, TaxCode, Term, Attachable), with an optional WHERE "
    "filter fragment."
)


@chat.function(
    "list_entities",
    _LIST_DESC,
    action_type="read", chain_callable=True, data_model=EntityList,
)
async def list_entities(ctx, params: ListEntitiesParams) -> ActionResult:
    """List records of one QuickBooks entity type via a generated SELECT query, with optional WHERE/pagination."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if not conn:
        return err
    entity = params.entity.strip()
    query = f"SELECT * FROM {entity}"
    if params.where.strip():
        query += f" WHERE {params.where.strip()}"
    query += f" STARTPOSITION {max(1, params.start_position)} MAXRESULTS {max(1, min(1000, params.max_results))}"
    result = await qc.request(ctx, conn, "GET", "/query", params={"query": query}, action=f"list {entity}")
    qr = result.get("QueryResponse", {}) if isinstance(result, dict) else {}
    rows = qr.get(entity, []) if isinstance(qr, dict) else []
    if not isinstance(rows, list):
        rows = []
    return ActionResult.success(EntityList(entity=entity, rows=rows, total_shown=len(rows)), summary="Entities listed.")


@chat.function(
    "get_entity",
    "Read one QuickBooks record of any entity type in full by its Id (e.g. get one Invoice, Customer, Bill).",
    action_type="read", chain_callable=True, data_model=EntityDetail,
)
async def get_entity(ctx, params: GetEntityParams) -> ActionResult:
    """Read one QuickBooks record of any entity type in full by its Id."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if not conn:
        return err
    entity = params.entity.strip()
    result = await qc.request(ctx, conn, "GET", f"/{entity.lower()}/{params.entity_id}", action=f"get {entity}")
    data = result.get(entity, {}) if isinstance(result, dict) else {}
    return ActionResult.success(EntityDetail(entity=entity, data=data), summary="Entity retrieved.")


@chat.function(
    "create_entity",
    "Create a new QuickBooks record of any entity type (e.g. a new Invoice, Customer, Bill, Item, Payment) "
    "from a JSON object of its fields exactly as QuickBooks expects.",
    action_type="write", chain_callable=True, data_model=EntityDetail,
    event="quickbooks-connector.create_entity",
    effects=["quickbooks.entity.created"],
)
async def create_entity(ctx, params: CreateEntityParams) -> ActionResult:
    """Create a new QuickBooks record of any entity type from a raw JSON fields object."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if not conn:
        return err
    entity = params.entity.strip()
    ok, body = qc.parse_json_object(params.fields_json)
    if not ok:
        return ActionResult.fail(qc.fail(qc.VALIDATION_FAILED, f"fields_json is not valid JSON: {body}"))
    result = await qc.request(ctx, conn, "POST", f"/{entity.lower()}", json_body=body, action=f"create {entity}")
    data = result.get(entity, {}) if isinstance(result, dict) else {}
    return ActionResult.success(EntityDetail(entity=entity, data=data), summary="Entity created.")


@chat.function(
    "update_entity",
    "Update selected fields of an existing QuickBooks record (sparse update, merged onto the existing entity). "
    "Requires the entity's current SyncToken from get_entity -- QuickBooks enforces optimistic concurrency.",
    action_type="write", chain_callable=True, data_model=EntityDetail,
    event="quickbooks-connector.update_entity",
    effects=["quickbooks.entity.updated"],
)
async def update_entity(ctx, params: UpdateEntityParams) -> ActionResult:
    """Sparse-update selected fields of an existing QuickBooks record (requires current SyncToken)."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if not conn:
        return err
    entity = params.entity.strip()
    ok, patch = qc.parse_json_object(params.fields_json)
    if not ok:
        return ActionResult.fail(qc.fail(qc.VALIDATION_FAILED, f"fields_json is not valid JSON: {patch}"))
    patch["Id"] = params.entity_id
    patch["SyncToken"] = params.sync_token
    patch.setdefault("sparse", True)
    result = await qc.request(ctx, conn, "POST", f"/{entity.lower()}", json_body=patch, action=f"update {entity}")
    data = result.get(entity, {}) if isinstance(result, dict) else {}
    return ActionResult.success(EntityDetail(entity=entity, data=data), summary="Entity updated.")


@chat.function(
    "delete_entity",
    "Delete/void a QuickBooks record. Most QBO transaction entities (Invoice, Bill, Payment, ...) support "
    "delete=true instead of true deletion; a handful of master-data entities (Customer, Vendor, Item, Account) "
    "cannot be deleted at all by QuickBooks and are instead deactivated via update_entity (set Active=false).",
    action_type="destructive", chain_callable=True, data_model=DeleteResult,
    event="quickbooks-connector.delete_entity",
    effects=["quickbooks.entity.deleted"],
)
async def delete_entity(ctx, params: DeleteEntityParams) -> ActionResult:
    """Delete/void a QuickBooks record of any entity type."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if not conn:
        return err
    entity = params.entity.strip()
    body = {"Id": params.entity_id, "SyncToken": params.sync_token}
    await qc.request(
        ctx, conn, "POST", f"/{entity.lower()}", params={"operation": "delete"},
        json_body=body, action=f"delete {entity}",
    )
    return ActionResult.success(DeleteResult(deleted=True, entity=entity, entity_id=params.entity_id), summary="Entity deleted.")


@chat.function(
    "send_entity",
    "Email a QuickBooks transaction (Invoice, Estimate, SalesReceipt, CreditMemo) to its customer, or to an "
    "override address.",
    action_type="write", chain_callable=True, data_model=EntityDetail,
    event="quickbooks-connector.send_entity",
    effects=["quickbooks.entity.sent"],
)
async def send_entity(ctx, params: SendEntityParams) -> ActionResult:
    """Email a QuickBooks transaction (Invoice/Estimate/SalesReceipt/CreditMemo) to its customer."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if not conn:
        return err
    entity = params.entity.strip()
    result = await qc.request(
        ctx, conn, "POST", f"/{entity.lower()}/{params.entity_id}/send",
        params={"sendTo": params.send_to.strip()} if params.send_to.strip() else None,
        action=f"send {entity}",
    )
    data = result.get(entity, {}) if isinstance(result, dict) else {}
    return ActionResult.success(EntityDetail(entity=entity, data=data), summary="Entity send requested.")


@chat.function(
    "void_entity",
    "Void a QuickBooks transaction (e.g. 'Invoice', 'SalesReceipt', 'Payment') -- keeps the record but zeroes "
    "its amount, for audit-trail-preserving corrections. Requires the entity's current SyncToken from "
    "get_entity.",
    action_type="destructive", chain_callable=True, data_model=EntityDetail,
    event="quickbooks-connector.void_entity",
    effects=["quickbooks.entity.voided"],
)
async def void_entity(ctx, params: VoidEntityParams) -> ActionResult:
    """Void a QuickBooks transaction, preserving the audit-trail record with a zeroed amount."""
    conn, err = await resolve_or_error(ctx, params.connection_id)
    if not conn:
        return err
    entity = params.entity.strip()
    body = {"Id": params.entity_id, "SyncToken": params.sync_token}
    result = await qc.request(
        ctx, conn, "POST", f"/{entity.lower()}", params={"operation": "void"},
        json_body=body, action=f"void {entity}",
    )
    data = result.get(entity, {}) if isinstance(result, dict) else {}
    return ActionResult.success(EntityDetail(entity=entity, data=data), summary="Void entity done.")
