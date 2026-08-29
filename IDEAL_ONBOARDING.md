# QuickBooks Online Connector — Ideal Onboarding

**Provider auth type:** OAuth2 Authorization Code (Intuit), app-level client_id/secret + per-user multi-company connections. Matches §5 row "OAuth user-delegated" of `ONBOARDING_FIRST_LAUNCH_STANDARD.md`.

## 0. Pre-connect & connect flow (ideal, unconstrained)

- **Sidebar (state 0):** Badge "Not connected" (gray, dot). Caption: "Connect QuickBooks Online to manage invoices, bills, customers and see your real P&L right here." Primary button "Connect QuickBooks" — ideally opens the OAuth popup INSIDE the panel with a live progress indicator that auto-detects completion (no manual "check connection" click needed) and auto-refreshes the sidebar/center the instant Intuit redirects back — today's SDK cannot push that event into the panel (L9), so realistically this becomes a manual "I've connected — check now" button.
- **Center (state 0):** `Empty` state mirroring the same CTA, ideally showing a live preview of what the summary dashboard will look like (skeleton with real card shapes) rather than a static message — not available in current SDK skeleton system for pre-connect, so falls back to plain `Empty`.
- **Connect form (OAuth):** ideally a single click straight to Intuit's consent screen with scope names translated into plain language ("Read invoices and customers, create/update bills and payments") shown BEFORE the click, not after.
- **Multi-company:** QuickBooks supports exactly one company per authorization; ideally, if the user already connected company A and wants company B, the flow should recognize "add another company" as a first-class action right in the sidebar, not buried in App settings.
- **Post-connect:** immediate value-add summary — cash position, unpaid invoices count, AR/AP aging headline — computed live from the freshly connected company, no extra click.

## 1. Gap vs current SDK (§2.4 limits)

- L9: no push notification when OAuth completes — user must click "Check connection" manually.
- L4: no native wizard/stepper — emulated via `Progress` + step text.
- L2/L3: sidebar renders without params at session init, so "which step are we on" state must live in the center panel only.

These gaps are accepted; `UI_COMPONENT_PLAN.md` builds the realistic version.
