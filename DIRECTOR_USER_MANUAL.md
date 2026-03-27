# LeadLock — Director user manual

This guide is for users with the **Director** role. Directors have the widest access in LeadLock: they configure the business, manage users and products, and can move leads through every stage of the sales workflow.

Other roles: **Sales Manager** (early pipeline through qualification) and **Closer** (quotes and closing). Directors share some tasks with those roles where noted below.

---

## 1. Signing in and getting around

- Open the app URL provided by your administrator and sign in with your email and password.
- The **logo** (top left) usually takes you to the **Dashboard** (`/dashboard`) so you can see high-level stats at a glance.
- Main navigation (top bar) typically includes:
  - **Leads** — pipeline of leads (a badge may show the count of new leads).
  - **Customers** — customer records and communication hubs (a badge can indicate unread messages).
  - **Quotes** — quotes and opportunities.
  - **Orders** — orders created from quotes.
  - **Products** — **Director only** in the main bar: catalogue, pricing, and optional extras.
  - **Reminders** — follow-ups and stale-item alerts (badge when there are open reminders).
  - **Documents** — sales documents library.
  - **Discount requests** — requests from the team (badge when approvals are pending).

- Open the **profile menu** (your name / user icon) for:
  - **My Settings** — your profile and email-related preferences (available to everyone).
  - **Director-only items:** **Users**, **Company Settings**, **Email Templates**, **Quote Templates**, **SMS Templates**, **Reminder Triggers**, **Discounts & Giveaways**.

If you do not see **Products** or the director-only menu entries, your account is not a Director — contact another Director or your administrator.

---

## 2. Lead workflow — what Directors can do

Lead statuses (in order of a typical happy path): **NEW → CONTACT_ATTEMPTED → ENGAGED → QUALIFIED → QUOTED → WON** (or **LOST** at any point).

| Capability | Director |
|------------|----------|
| Move a lead to **any** next status | Yes — the system allows every transition that is not the current status. |
| Bypass normal role rules | Yes — when using an **override** with a **reason** (see API behaviour below), Directors can move leads in ways other roles cannot. |
| Move to **QUOTED** | Still subject to **quote rules** (customer profile and, if enabled, engagement proof) — see §3. |

**What this means in practice**

- Use **Leads** and **lead detail** pages to update lead fields, log activities (calls, SMS, email, notes), and move the lead forward or mark it lost.
- **Status history** on a lead shows who changed status and, when applicable, **override reasons** (audit trail).
- The on-screen buttons on a lead may focus on common actions (for example qualify or reject); the **backend** still allows Directors the full set of transitions. If you need a rare transition (for example straight to **WON**), your team may use workflows that call the API with `override_reason`, or you standardise moves through activities and customer updates first.

---

## 3. Quote lock (when a quote can be sent)

Before a lead can reach **QUOTED** (and before quotes align with “ready to send” checks), the **customer** attached to the lead must satisfy **quote prerequisites**:

1. **Postcode**, **email**, and **phone** on the customer record.
2. If **Company Settings** has **“Require engagement proof before quoting”** turned on, there must be at least one qualifying activity on that customer, such as inbound SMS/email/WhatsApp, a logged **Live Call**, or an **email sent** from the system (see the Quote Lock card on the customer for the exact list).

Directors **cannot** turn off postcode/email/phone requirements from the UI; they are enforced for everyone. The **engagement proof** requirement is optional and controlled under **Company Settings** (Director-only).

---

## 4. Company Settings (Director)

**Profile → Company Settings**

Use this to define how LeadLock represents your business and how quotes and installs are calculated.

Typical areas:

- **Identity** — company name, trading name, registration and VAT, address, phone, email, website.
- **Branding** — logos (header/footer), default terms, email disclaimer.
- **Bank details** — **visible only to Directors** in the API; other roles do not receive these fields when viewing company settings.
- **Installation & travel** — factory postcode, mileage rates, overnight allowances, average speed, margins used in delivery/install lines on quotes.
- **Policies** — e.g. **Require engagement proof before quoting** (see §3).
- **Customer import** — CSV import (and related export) for bulk customer work; follow the on-page format and validation messages.

Save changes after edits. If settings were never created, you may need to submit the form once to **create** the record (first-time setup).

---

## 5. Users (Director)

**Profile → Users**

- **List** all app users.
- **Create** users and assign roles: **Director**, **Sales Manager**, or **Closer**.
- **Edit** names, emails, roles, and **active** status (deactivating a user stops them logging in without deleting history).

Treat Director accounts as high privilege: only people who should manage users, bank details, and catalogue data should hold this role.

---

## 6. Products (Director)

**Products** in the main navigation (Director only).

- Maintain your **product catalogue**: names, descriptions, prices, categories, installation hours, spec sheet data, etc.
- Manage **optional extras** linked to products.
- **Images** — upload product images where the app supports it (Director-only uploads).

Sales staff use these products when building quotes; keeping them accurate avoids pricing and specification errors.

---

## 7. Templates (Director)

| Menu item | Purpose |
|-----------|---------|
| **Email Templates** | Reusable email content for outbound communication. |
| **Quote Templates** | Structure/content patterns for quotes where the app uses them. |
| **SMS Templates** | Reusable SMS text for consistency and speed. |

Edit these when branding, legal wording, or sales messaging changes.

---

## 8. Discounts and discount requests

- **Profile → Discounts & Giveaways** — define **discount templates** (percentage/fixed, scope, giveaways). **Directors** create, edit, and deactivate templates.
- **Discount requests** (main nav) — staff submit requests; **Directors** and **Sales Managers** can **approve** or decline pending requests (watch the badge for pending items).

---

## 9. Reminders and reminder rules

- **Reminders** — everyone sees reminders relevant to their role; **Directors** (and **Closers**) see **all** reminders in the system so nothing is hidden by team silos.
- **Profile → Reminder Triggers** — configure **rules** that generate reminders (thresholds, entity types, priorities). **Creating and editing rules is Director-only**; viewing the page may be available more broadly, but rule management is restricted to Directors in the product.

Use this to tune how aggressively the system flags stale leads and quotes.

---

## 10. Sales documents

**Documents** in the main navigation.

**Directors** and **Sales Managers** can **upload and manage** files in the sales document library (e.g. brochures, terms PDFs). Other roles may have read-only access depending on implementation — use this area as the single source for files the team should send or reference.

---

## 11. Quotes, orders, customers, and reporting

These areas are **not** Director-exclusive:

- **Customers** — full CRM view: contact details, leads, quotes, activities, email/SMS/Messenger where integrated, and the **Quote Lock** status card.
- **Quotes** — build, send, track opens, and manage opportunity fields.
- **Orders** — progression from accepted quotes, deposits, and installation milestones where configured.
- **Dashboard** — stats and shortcuts (via logo or `/dashboard`).

Directors use the same screens with the added confidence that they can fix data, users, and company-wide settings when something blocks the team.

---

## 12. Good habits for Directors

1. **Keep Company Settings current** — especially VAT, bank details, terms, and install/mileage assumptions used on PDFs.
2. **Review Users** when people join or leave — deactivate leavers promptly.
3. **Align Products and Discounts** with real pricing authority — avoid “stray” discount templates that confuse the team.
4. **Use engagement proof policy deliberately** — stricter proof improves data quality but adds friction; match it to how you actually sell.
5. **Watch Reminders and Discount request badges** — they surface work that may need a Director decision.
6. **Respect audit fields** — status history and override reasons exist for accountability; use overrides when the exception is justified and documented.

---

## 13. If something is blocked

| Issue | What to check |
|-------|----------------|
| Cannot move lead to **QUOTED** | Customer postcode, email, phone; engagement proof if required (§3). |
| Team member cannot see bank details | Only **Directors** receive bank fields from the API. |
| Missing menu (Products, Users, …) | Role must be **Director**; not a browser cache issue. |
| Quote email missing “view online” link | This is configured in **deployment** (frontend URL on the server). Ask whoever maintains hosting (`FRONTEND_BASE_URL` / similar). |

For **password resets** and **new Director onboarding**, another Director can create or reactivate an account under **Users**. If you are the only Director and locked out, your technical administrator must use the database or seed/bootstrap flows documented for operators (`README.md`, `MAINTENANCE_MANUAL.md`).

---

*Proprietary — Cheshire Stables. This manual describes the LeadLock application behaviour as implemented in the product; minor UI labels may vary by version.*
