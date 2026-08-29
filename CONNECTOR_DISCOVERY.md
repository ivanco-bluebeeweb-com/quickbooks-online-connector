# QuickBooks Online Connector — Connector Discovery

**Дата discovery:** 2026-08-29
**Vikunja task:** #2674 (BBW Imperal Apps), [App Development] QuickBooks Online Connector.
**Статус:** Ярусы 1-3 пройдены (свежее чтение developer.intuit.com, 2026-08-29). Пользователь дал явное указание («делай приложения для направления Finance & Business Operations... максимальный функционал» — общее правило волны) — это фиксируется как выбранный release scope (Ярус 1+2+3), повторный вопрос не требуется.

---

## 1. Целевой сервис и источники

QuickBooks Online (Intuit) — крупнейшая облачная бухгалтерская платформа для малого/среднего бизнеса в США. Единый REST-подобный Accounting API поверх модели "Company" (realmId), с OAuth2 авторизацией.

Источники (прочитаны 2026-08-29):
- `developer.intuit.com/app/developer/qbo/docs/develop/authentication-and-authorization/oauth-2.0` — OAuth2 authorization code flow
- `developer.intuit.com/app/developer/qbo/docs/learn/rest-api-features` — базовая схема данных, форматы
- `developer.intuit.com/app/developer/qbo/docs/learn/explore-the-quickbooks-online-api` — карта возможностей API
- `developer.intuit.com/app/developer/qbo/docs/get-started/start-developing-your-app` — Sandbox/Production окружения
- `developer.intuit.com/app/developer/qbo/docs/develop/sandboxes/postman` — тестовые company

## 2. Карта возможностей

| Домен API | Возможность | Ingress/Egress/Both | Комментарий |
|---|---|---|---|
| Customers | CRUD + query | Both | Ядро — клиенты |
| Vendors | CRUD + query | Both | Поставщики |
| Employees | CRUD + query | Both | Для payroll-adjacent данных (не сам payroll) |
| Items (Products/Services) | CRUD + query | Both | Каталог товаров/услуг |
| Invoices | CRUD + send + query | Both | Ядро — счета клиентам |
| Estimates | CRUD + query | Both | Коммерческие предложения |
| SalesReceipts | CRUD + query | Both | Продажи с немедленной оплатой |
| Payments | CRUD + query | Both | Платежи от клиентов |
| Bills | CRUD + query | Both | Счета от поставщиков (AP) |
| BillPayments | CRUD + query | Both | Оплата счетов поставщикам |
| Purchases | CRUD + query | Both | Расходы (карта/чек/наличные) |
| JournalEntries | CRUD + query | Both | Ручные проводки в ГК |
| Accounts (Chart of Accounts) | CRUD + query | Both | План счетов |
| Classes/Departments | CRUD + query | Both | Аналитика по сегментам бизнеса |
| TaxCodes/TaxRates | query | Ingress | Налоговые ставки |
| Reports | P&L, Balance Sheet, Cash Flow, AR/AP Aging | Ingress | Ключевая ценность для CFO |
| Attachments | upload/link to any entity | Egress | Вложения к счетам/чекам |
| CompanyInfo | get | Ingress | Диагностика подключения |
| Query language | generic SQL-like `query` endpoint on any entity | Ingress | Универсальный поиск |

## 3. Классификация по типу функционала

- **Ingress**: списки/чтение любых сущностей, query, отчёты, company info.
- **Egress**: создание/обновление (sparse update через `SyncToken`) всех сущностей, отправка invoice по email, загрузка attachments.
- **Both**: send-and-record операции (создание Payment одновременно применяется к Invoice).

## 4. Ярус 1 — ключевые функции (P0)

1. `connect_quickbooks` / `disconnect_quickbooks` / `list_connections` — OAuth2, realmId per company
2. `list_customers` / `get_customer` / `create_customer` / `update_customer`
3. `list_vendors` / `get_vendor` / `create_vendor` / `update_vendor`
4. `list_invoices` / `get_invoice` / `create_invoice` / `update_invoice` / `send_invoice`
5. `list_bills` / `get_bill` / `create_bill` / `update_bill`
6. `create_payment` / `list_payments` / `get_payment`
7. `list_accounts` (chart of accounts)
8. `run_query` — generic QBO query language passthrough
9. `get_company_info`

## 5. Ярус 2 — расширение (P1)

10. `list_items` / `get_item` / `create_item` / `update_item`
11. `list_employees` / `get_employee` / `create_employee` / `update_employee`
12. `list_estimates` / `get_estimate` / `create_estimate` / `update_estimate`
13. `list_sales_receipts` / `get_sales_receipt` / `create_sales_receipt`
14. `create_bill_payment` / `list_bill_payments`
15. `create_purchase` / `list_purchases`
16. `create_journal_entry` / `list_journal_entries`
17. `list_classes` / `list_departments`
18. `list_tax_codes` / `list_tax_rates`
19. `upload_attachment` / `list_attachments`

## 6. Ярус 3 — ценность/отчётность (P2)

20. `get_profit_and_loss_report` / `get_balance_sheet_report` / `get_cash_flow_report`
21. `get_ar_aging_report` / `get_ap_aging_report`
22. `get_cash_position_summary` (value-add: балансы всех банковских счетов + просрочки в одном отчёте)
23. `void_invoice` / `void_payment` (explicit confirmation gate — деструктивно для бухгалтерии)
24. `delete_attachment`

## 7. Решение по объёму

Release scope: **максимальный (Ярус 1+2+3)** — подтверждено стандартным правилом волны Finance & Business Operations. Write-операции на финансовых документах (invoices/bills/payments/journal entries) — `action_type="write"`, void-операции получают explicit confirmation gate (аналог WooCommerce `update_order_status_risky` в WordPress Hub).
