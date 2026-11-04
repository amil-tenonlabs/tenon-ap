# TODO

Open engineering, deployment and documentation items, in priority order. An item
is removed when it is done, not ticked — `git log -- TODO.md` is the record.
Findings about a GC's own vendors and invoices do not go here.

---

## 1. Credit card coding: wrong in production now

Numbers are the findings in `design/credit-card-coding.md`, which has the detail.
The fixes that block testing, with editor steps, are in the design record's
"Getting it running".

- [ ] **Separate credit card mail from APM's on the APM mailbox** (finding 6) — mail to
      `apm+cc@…`, an Outlook rule moving it (or a `[CC]` subject) to a `Credit
      Cards` folder, the intake watching only that.
      Testing steps 1-3 in the design record, before switching anything on.
- [ ] **Backstop in APM's `mailroom`** — a trigger condition skipping mail sent to
      `apm+cc` or with `[CC]` in the subject, in case the folder rule is off. An
      APM recipe change; confirm first that its trigger watches the inbox only.
- [ ] **Own mailbox for credit card coding** — decided for later; until then the
      folder rule above is what keeps APM's mail out.
- [ ] **Digest emails are a blank finance cover** (1) — RCP-002 steps 12/18.
- [ ] **FNC-001's matched / no-match emails are a blank Charge Form** (2) — steps 13/18.
- [ ] **FNC-002 does not copy coding to the charge** (3) — step 15; also decide
      how a later edit of a Receipt's coding reaches its Transaction.
- [ ] **Paste the cover template** (4) — `templates/finance_package_cover.html` now
      prints its tables with `{{{ }}}`.
- [ ] **Image receipts dropped** (5) — convert to PDF before FNC-001, and have the
      intake act on a `failed` result.

## 2. Credit card coding: wrong in some cases

- [ ] **No-match uses the calendar month and any card's statement** (7).
- [ ] **Duplicate charges from overlapping statements** (8) — the KNOWN GAP check in
      `tests/test_credit_card.py` turns around with the fix.
- [ ] **Recurring charges can match the wrong month** (9).
- [ ] **1,000-row reads** (10) — every daily and re-check read.
- [ ] **A receipt sent twice** (11).
- [ ] **Per-client values in steps** (13–15) — finance address, bank name on the
      Charge Form, statement format. Account properties before a second GC.

## 3. Decisions waiting on you

- [ ] **Fix the credit card project in place, or rebuild it** on the AP design
      (Claude, its own mailbox, ACC checks).
- [ ] **Exempt charges and finance** (12) — should they reach the package?
- [ ] **Scope of the wider AP bot** — sub pay applications, vendor invoices or
      both, and how far the first version goes. `design/ap-bot-overview.md`.
- [ ] **Where approved invoices and coded charges go** — the accounting system
      behind hh2, ACC Cost expenses, or a coded batch for AP staff to import.
      Name the accounting system.
- [ ] **AP mailbox** — its own address, or AP added to APM's classifier.
- [ ] **Approval rules** — who approves at which amount, per GC.

## 4. Before the wider AP build

- [ ] **Measure on real data** — a real extract and a sample of invoices, per
      the overview's last section. Output is read, not committed.
- [ ] **Ask the APM chat for an `AP` document set** in the Claude connector, and
      for the upload recipe to cover this repo — `handoffs/ap-document-set.md`.
      Only once the first AP document exists.
- [ ] **Accounting integration** — whether hh2 or the accounting system has an
      API Workato can reach, and whether that is a connector in tenon-apm or here.
