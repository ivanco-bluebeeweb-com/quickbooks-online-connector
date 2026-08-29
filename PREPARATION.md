# QuickBooks Online Connector — Preparation

**Статус:** Фаза 1 (Discovery) завершена — см. `CONNECTOR_DISCOVERY.md`. Release scope: максимальный (Ярус 1+2+3), подтверждено стандартным правилом волны Finance & Business Operations.
**Владелец продукта:** vlad@bluebeeweb.com
**Дата подготовки:** 2026-08-29, v0.1
**Vikunja task:** #2674 (BBW Imperal Apps), [App Development].

**Почему сейчас:** QuickBooks Online — самая распространённая облачная бухгалтерская система для малого/среднего бизнеса в США, первое приложение категории Accounting & Bookkeeping в новом направлении Industries → Finance & Business Operations.

---

## 1. Паспорт приложения

**Название в Marketplace (display_name): «QuickBooks Online»**. app_id: `quickbooks-online-connector`.

Коннектор к Accounting API QuickBooks Online через OAuth2. BYOK: пользователь подключает свою(и) компанию(и) QuickBooks через стандартный OAuth2 authorization code flow (Intuit App с client_id/client_secret, настроенным разработчиком Imperal — то есть APP-level credentials, а connections per-user хранятся в user-scoped секрете, аналогично Google Drive/HubSpot паттерну).

## 2. Авторизация — OAuth2 Authorization Code (Intuit)

- App-level: `client_id`/`client_secret` (declared as app-scope secrets, созданы Imperal-разработчиком в Intuit Developer Dashboard).
- Per-user: authorization code → access_token (1h) + refresh_token (100 days, rotates on each refresh) + `realmId` (company id).
- Redirect URI зарегистрирован на стороне Intuit App.
- Sandbox vs Production — разные наборы client_id/secret (объявляем production; sandbox — для собственного тестирования разработчиком, не для конечного пользователя).
- Proactive refresh: access_token живёт всего 1 час — обязательно `fresh_token`/`with_fresh_token` из `imperal_sdk`, refresh перед каждым вызовом, а не reactive-on-401 (иначе слишком частые ре-аутентификации).
- Отзыв: если refresh_token невалиден (истёк 100-дневный период неактивности) — понятная ошибка "reconnect your QuickBooks company".

## 3. Такие же принципы, как у HubSpot/Google Drive Connector

- Один секрет с JSON-массивом подключённых компаний (`quickbooks_connections`), каждая запись: `{connection_id, realm_id, company_name, access_token, refresh_token, expires_at, refresh_expires_at}`.
- `list_connections` — обзор всех подключённых компаний.
- Ошибки — единый словарь кодов в `quickbooks_client.py` (по образцу `drive_client.py`/`hubspot_client.py`).

## 4. Денежная точность (APP_SAFETY_CHECKLIST)

Суммы — Decimal-safe строки, никогда float-округление на стороне коннектора; передаём то, что вернул QuickBooks, без пересчёта. Void-операции (`void_invoice`, `void_payment`) — explicit confirmation gate, `action_type="write"`, не автоматизируются без явного подтверждения пользователя в вызове.

## 5. Чеклист публикации

Discovery ✅ → Preparation ✅ → IDEAL_ONBOARDING.md/UI_COMPONENT_PLAN.md (до panels.py) → код → validate 0/0 → публичный Git без секретов → deploy → pricing (per_action, suspended) → submit_for_review.
