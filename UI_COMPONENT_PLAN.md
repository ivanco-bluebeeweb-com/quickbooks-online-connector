# QuickBooks Online Connector — UI Component Plan

Built strictly from `imperal_sdk.ui` per `ONBOARDING_FIRST_LAUNCH_STANDARD.md` §2 and §6 catalog. All inputs carry visible labels via `Stack(caption)+field` (L1), forms/containers stretch full width, no sidebar/modal instruction duplication.

## 0. Pre-connect & connect flow

**Sidebar (`slot="left"`, no params):**
```
Stack(v, gap=3, align="stretch"):
  Badge(connected ? "Connected" green,dot : "Not connected" gray,dot)
  Text(caption, "Connect QuickBooks Online to manage invoices, bills, customers and see cash position right here.")
  Divider()
  if not connected: Button("Connect QuickBooks", variant=primary, full_width, on_click=Call("__panel__connect_qb"))
  if connected: List of connected companies (name + Button("Switch", size=sm))
  Divider()
  Button("App settings", variant=secondary, on_click=Call("__panel__qb_settings"))
```

**Center pre-connect (`Empty`):**
```
Empty(message="Connect QuickBooks Online to see your real cash position, unpaid invoices and AR/AP aging.",
      icon="Landmark", action=Button("Connect QuickBooks", on_click=Call("__panel__connect_qb")))
```

**Connect panel (`__panel__connect_qb`, center overlay):**
```
Stack(v, gap=3, align="stretch", className="full-width"):
  Text(heading, "Connect QuickBooks Online")
  Text(caption, "You'll be redirected to Intuit to sign in and authorize read/write access to invoices, bills, customers, vendors and reports.")
  Button("Continue to QuickBooks", variant=primary, full_width, on_click=Open(oauth_url))
  Divider()
  Text(caption, "Already authorized? Come back here and check below.")
  Button("Check connection", variant=secondary, full_width, on_click=Call("check_qb_connection"))
```

**Success:** `Alert(success, "QuickBooks connected — loading your company data…")`, `refresh_panels=["sidebar","editor"]`.

**Error inline:** `Alert(error, <taxonomy per ONBOARDING §4>)` inside same panel.

**App settings (`__panel__qb_settings`):** one row per connected company — `Text(company_name)`, `Text(caption, realm_id)`, `Button("Disconnect", variant=danger, on_click=Call("disconnect_quickbooks", {"connection_id": ...}))` behind `Dialog` confirm.

## 1. Post-connect summary (center default)

```
Stack(v, gap=4):
  Stats([Stat("Cash on hand", value, trend), Stat("Unpaid invoices", count), Stat("Overdue bills", count)])
  Chart(type=line, "Revenue last 90 days")
  DataTable(recent invoices, columns=[customer, amount, due_date, status])
```

All per §6 catalog items 1-9 reused verbatim (provider name substituted: "QuickBooks").
