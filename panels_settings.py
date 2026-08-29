"""The single 'App settings' screen (center slot) -- connection management
(disconnect per QuickBooks company) for QuickBooks Online Connector. Split
out of panels.py per the same convention as Clio Connector's /
MuleSoft Connector's panels_settings.py.

Per ~/UI_INTERFACE_STANDARD.md: the left sidebar never wraps the connect
form in a Card, and disconnect (never exposed in the sidebar itself) lives
here, one row per connected company. The one secondary "App settings"
button sits LAST at the bottom of the sidebar.
"""
from __future__ import annotations

from imperal_sdk import ui

from app import ext
import handlers_connection as h


def _connection_row(c: dict) -> ui.UINode:
    label = c.get("label") or c.get("company_name") or "QuickBooks company"
    return ui.Stack(direction="v", gap=1, align="start", children=[
        ui.Text(label, variant="body"),
        ui.Text(f"Realm {c.get('realm_id', '') or '—'}", variant="caption"),
        ui.Button(
            "Disconnect", variant="danger", size="sm",
            on_click=ui.Call("disconnect_quickbooks", {"connection_id": c.get("id")}),
        ),
    ])


def _connections_section(connections: list[dict]) -> ui.UINode:
    if not connections:
        return ui.Stack(direction="v", gap=1, children=[
            ui.Text("Connections", variant="heading"),
            ui.Text("No QuickBooks companies connected yet.", variant="caption"),
        ])
    children: list[ui.UINode] = [ui.Text("Connections", variant="heading")]
    for i, c in enumerate(connections):
        if i > 0:
            children.append(ui.Divider())
        children.append(_connection_row(c))
    return ui.Stack(direction="v", gap=2, align="start", children=children)


@ext.panel("quickbooks_settings", slot="center", title="QuickBooks Online -- App settings")
async def quickbooks_settings_panel(ctx, **kwargs) -> object:
    connections = await h._load_connections(ctx)
    return ui.Stack(direction="v", gap=4, align="stretch", children=[
        ui.Header(text="QuickBooks Online -- App settings", level=2),
        _connections_section(connections),
    ])
