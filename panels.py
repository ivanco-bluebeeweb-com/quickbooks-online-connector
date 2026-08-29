"""Panel UI -- connections list/connect form + the one required "App
settings" entry point, same shape as Clio Connector's panels.py.

SIDEBAR CONTENT -- NO CARDS ANYWHERE, per ~/UI_INTERFACE_STANDARD.md's
"left sidebar, no decorated cards" rule. Every section is a plain
ui.Stack, content stacked vertically and left-aligned, sections separated
by ui.Divider() -- no Card border/background/shadow anywhere in this
slot. Disconnect lives only in the "App settings" screen
(panels_settings.py). The one secondary "App settings" button is always
the LAST element at the bottom of the sidebar.

PER ~/UI_INTERFACE_STANDARD.md (2026-08-21 addendum): every Input carries
its own visible label (never placeholder-only), the placeholder text is
always contextually specific to what's being entered (never a generic
"Enter value"), the form's own container is stretched to the full width
of the left sidebar, and the form's inner content is stretched to fill
that container. The "How do I set this up?" instructions live ONLY in
the help modal below -- never duplicated as static sidebar text.
"""
from __future__ import annotations

from imperal_sdk import ui

from app import ext
import handlers_connection as h


def _settings_button() -> ui.UINode:
    return ui.Button(
        "App settings", variant="secondary", size="sm", full_width=True,
        icon="settings", on_click=ui.Call("__panel__quickbooks_settings"),
    )


def _connection_row(c: dict) -> ui.UINode:
    label = c.get("label") or c.get("company_name") or "QuickBooks company"
    return ui.Stack(direction="v", gap=1, children=[
        ui.Text(label, variant="body"),
        ui.Text(f"Realm {c.get('realm_id', '') or '—'}", variant="caption"),
    ])


def _connections_section(connections: list[dict]) -> ui.UINode:
    if not connections:
        return ui.Text("No QuickBooks companies connected yet.", variant="caption")
    children: list[ui.UINode] = []
    for i, c in enumerate(connections):
        if i > 0:
            children.append(ui.Divider())
        children.append(_connection_row(c))
    return ui.Stack(direction="v", gap=2, children=children)


def _connect_section() -> ui.UINode:
    return ui.Stack(direction="v", gap=3, align="stretch", children=[
        ui.Button("How do I set this up?", variant="ghost", size="sm",
                  icon="HelpCircle",
                  on_click=ui.Call("__panel__quickbooks_connect_help")),
        ui.Form(
            action="connect_quickbooks",
            submit_label="Get authorize link",
            children=[
                ui.Stack(direction="v", gap=1, align="stretch", children=[
                    ui.Text("Intuit app Client ID", variant="caption"),
                    ui.Input(param_name="client_id",
                             placeholder="Paste your Intuit Developer app's Client ID"),
                ]),
                ui.Stack(direction="v", gap=1, align="stretch", children=[
                    ui.Text("Intuit app Client Secret", variant="caption"),
                    ui.Password(param_name="client_secret",
                                placeholder="Paste your Intuit Developer app's Client Secret"),
                ]),
                ui.Stack(direction="v", gap=1, align="stretch", children=[
                    ui.Text("Label (optional)", variant="caption"),
                    ui.Input(param_name="label", placeholder="e.g. Acme Corp books"),
                ]),
            ],
        ),
    ])


@ext.panel("quickbooks_connect", slot="left", title="QuickBooks Online", icon="🧾",
           default_width=320, min_width=260, max_width=420)
async def quickbooks_connect_panel(ctx, **kwargs) -> object:
    connections = await h._load_connections(ctx)

    header = ui.Header(text="QuickBooks Online", level=2,
                        subtitle="Manage invoices, bills, customers and see your real cash position from Imperal")

    return ui.Stack(direction="v", gap=4, align="stretch", children=[
        header,
        _connections_section(connections),
        ui.Divider(),
        _connect_section(),
        ui.Divider(),
        ui.Button("View cash position", variant="primary", size="sm", full_width=True,
                  icon="Landmark", on_click=ui.Call("__panel__quickbooks_center")),
        ui.Divider(),
        _settings_button(),
    ])


@ext.panel("quickbooks_connect_help", slot="center",
           title="How to connect QuickBooks Online", center_overlay=True)
async def quickbooks_connect_help(ctx, **kwargs) -> object:
    content = ui.Stack(direction="v", gap=3, children=[
        ui.Text("1. Go to developer.intuit.com, sign in, and open \"My Apps\"."),
        ui.Text("2. Click \"Create an app\" > choose \"QuickBooks Online and Payments\", give it a name."),
        ui.Text("3. Under Keys & OAuth, copy the app's Client ID and Client Secret (use the Production keys, not Development, once you're ready for real company data)."),
        ui.Text("4. Add a Redirect URI -- you'll get the exact callback URL to paste there after clicking \"Get authorize link\" below."),
        ui.Text("5. Paste the Client ID and Client Secret into the form here and click \"Get authorize link\"."),
        ui.Text("6. Open the link, sign in with Intuit, pick a company, and approve access -- the connection finishes itself automatically."),
        ui.Divider(),
        ui.Alert(
            title="Full QuickBooks Online coverage",
            message=(
                "Customers, Vendors, Employees, Items, Invoices, Bills, "
                "Payments, Estimates, Sales Receipts, Credit Memos, Journal "
                "Entries, Purchases, Purchase Orders, Vendor Credits, "
                "Deposits, Transfers, Accounts, Classes, Departments, plus "
                "full SQL-like queries, every standard report (P&L, Balance "
                "Sheet, Cash Flow, AR/AP aging, Trial Balance), attachments, "
                "and value-add reports like cash position and overdue "
                "invoices."
            ),
            type="info",
        ),
        ui.Divider(),
        ui.Link("developer.intuit.com", url="https://developer.intuit.com/app/developer/homepage"),
    ])
    return ui.Stack(direction="v", gap=3, children=[content])
