# LeadLock automations — staff meeting agenda (one page)

**Purpose:** Walk through what the system does automatically today, where staff control it, and what to change next.

**Suggested time:** 45–60 minutes · **Audience:** Sales, closers, directors

---

## 1. Inbound leads (10 min)

| Topic | What happens automatically | Where to see it | Quick demo |
|-------|---------------------------|-----------------|------------|
| Make.com / forms / Facebook | Lead created as **NEW**; may link to existing customer | Leads list, lead detail | Show a recent Facebook/form lead + source |
| Welcome SMS/email | **Only if** Reminder Trigger has **on lead create** + template | Settings → Reminder Triggers; outreach log on rule | Create test lead or show webhook lead + send log |
| Duplicate enquiries | Flag + optional **auto-close** + duplicate SMS | Company Settings; duplicate lead record | Show closed duplicate vs primary lead |

**Discuss:** Assignee (`WEBHOOK_DEFAULT_USER_ID`), welcome message wording, auto-close duplicates on/off.

---

## 2. Lead pipeline — status moves (10 min)

| Trigger | Auto status change |
|---------|-------------------|
| Staff logs **any activity** on **NEW** lead | → **ENGAGED** |
| Inbound SMS/email/call (engagement proof) | → **ENGAGED** (from CONTACT_ATTEMPTED) |
| Customer has postcode, email, phone (+ engagement if enabled) | → **QUALIFIED** |
| Quote created or **sent** | **QUALIFIED** → **QUOTED** |
| Quote **won** / **lost** | Lead → **WON** / **LOST** |

| Also automatic | Notes |
|----------------|-------|
| **Opportunity** created when qualified (if none exists) | Draft quote in Opportunities |
| Closer-created lead (valid source + type) | Starts **QUALIFIED**; all qualifies need source (not Manual/Other) + type (Stables/Sheds/Cabins) |
| Customer → **New lead and quote** | Modal for source + type; lead starts **NEW**, then qualify before quote |
| SLA badges | Red (NEW >15 min), amber (no engagement >48h) — **visual only** |

**Demo path:** Open **NEW** lead → log a note → refresh status → fill customer fields → show **QUALIFIED** + new opportunity.

**Discuss:** Are auto-moves helping or confusing? Stricter quote lock (engagement proof)?

---

## 3. Customer messages — what runs in the background (10 min)

| Automation | Runs when | Staff control |
|------------|-----------|---------------|
| **Reminder Trigger outreach** | Stale lead/quote matches rule (every ~5 min) | Reminder Triggers: threshold, SMS/email template, cooldown |
| **Scheduled SMS** | Due time reached (~45 sec worker) | Customer SMS — schedule send |
| **SMS bot (out of hours)** | Customer texts known number | Company Settings: bot mode, hours, instructions |
| **Inbound email** | Known customer email (~5 min poll) | Customer must exist with that email |
| **STOP / opt-out** | Keyword or Twilio block | Stops bot + automated reminder messages |

**Rules:** No sends **23:00–06:00** (company timezone). Opt-out respected.

**Demo path:** Settings → one active outreach rule → Reminder Triggers outreach history → optional: inbound SMS after hours (bot reply).

**Discuss:** Which stale rules should send SMS vs email vs staff-only reminder?

---

## 4. Staff reminders & weekly plan (8 min)

| Feature | Automatic? | How staff use it |
|---------|------------|------------------|
| **Reminders** (tasks on Reminders page) | **No** — someone clicks **Generate** | Daily/weekly habit; act or dismiss |
| **Reminder rules** | Define *when* stale | Director edits thresholds |
| **Weekly plan** | List can be generated; **auto-send email/SMS only if enabled on server** | Weekly Plan page — review before send |
| Quote accepted | Open quote reminders **auto-dismissed** | — |
| Installation completed | After configurable delay: **REQUEST_REVIEW** staff reminder; optional customer SMS/email with Google/Facebook/Trustpilot links | Company Settings → Post-install review requests |

**Demo path:** Reminders → Generate → show stale lead + suggested action → dismiss or complete.

**Discuss:** Should reminders auto-generate on a schedule? Enable weekly plan auto-send?

---

## 5. Quotes, tracking & integrations (7 min)

| Item | Behaviour |
|------|-----------|
| Quote email **open tracking** | Drives “sent not opened” / “opened no reply” rules |
| Website **visit pixel** (`ltk=`) | Shows under customer **Websites Visited** |
| **Send to production** | **Manual** button on order |
| **Xero (Make)** | **Manual** push from order when configured |
| Product sync from production | Webhook updates catalogue |

**Demo path:** Sent quote → tracking / reminder rule → customer Websites Visited (if used).

---

## 6. What is *not* automated (2 min — set expectations)

- Quotes are **not** auto-sent to customers
- Orders are **not** auto-sent to production
- Unknown phone numbers **do not** create leads
- Unknown inbound emails are **ignored**
- Most status changes still need **staff action** unless a trigger above fires

---

## 7. Future changes — capture on the day

| Priority | Idea | Owner | Notes |
|----------|------|-------|-------|
| 1 | | | |
| 2 | | | |
| 3 | | | |

**Common asks to vote on:** Auto-generate reminders daily · More/fewer outreach rules · Bot on/off or hours · Stricter qualify/quote rules · Weekly plan auto-send · New Make.com sources

---

## Demo cheat sheet (15 min total hands-on)

1. **Webhook lead** → Leads → check status, assignee, outreach log
2. **Activity on NEW** → status → ENGAGED
3. **Customer complete** → QUALIFIED + opportunity
4. **Reminder Triggers** → one rule + outreach history
5. **Reminders** → Generate → one action
6. *(Optional)* Inbound SMS → activity + bot if after hours

---

## Key settings map (for directors)

| Setting | Location |
|---------|----------|
| Outreach rules & templates | Settings → Reminder Triggers |
| SMS bot & quiet-hours timezone | Company Settings |
| Engagement proof before quote | Company Settings |
| Auto-close duplicates | Company Settings |
| Email/SMS templates | Profile → templates menus |
| Weekly plan message templates | Settings → Weekly Plan Templates |
| Post-install review URLs, delay & templates | Settings → Company → Post-install review requests |

---

## Viewing this file in a browser

- **Cursor / VS Code:** Open this file → **Ctrl+Shift+V** (Markdown preview) → print to PDF if needed.
- **GitHub:** Open the file in the repo; GitHub renders Markdown in the browser.

---

*Cheshire Stables LeadLock — automations overview. For technical detail see `MAINTENANCE_MANUAL.md`, `MAKECOM_INTEGRATION_GUIDE.md`, `DIRECTOR_USER_MANUAL.md`.*
