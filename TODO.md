# TODO

Open engineering, deployment and documentation items, in priority order. An item
is removed when it is done, not ticked — `git log -- TODO.md` is the record.
Findings about a GC's own vendors and invoices do not go here.

---

## 1. Credit card coding: wrong in production now

Numbers are the findings in `design/credit-card-coding.md`, which has the detail.
The fixes that block testing, with editor steps, are in the design record's
"Getting it running".

- [ ] **Intake's trigger condition misses replies** (finding 6) — it requires the subject
      to *start with* `[CC]` *(export 11-04)*, so "RE: [CC] …" never reaches the
      intake. Use *contains*. There is no folder rule yet, so APM's recipes still see
      every `[CC]` email.
- [ ] **Backstop in APM's `mailroom`** — a trigger condition skipping mail with
      `[CC]` in the subject: with no folder rule, APM sees every
      credit card email. An APM recipe change; confirm first that its trigger watches the inbox only.
- [ ] **Own mailbox for credit card coding** — decided for later; until then the
      `[CC]` trigger condition is what keeps APM's mail out of the intake.
- [ ] **Test the new email bodies** (1, 2) — the digest and FNC-001 now build their
      emails inline (`format_map` in the digest), done in the editor 2026-11-04. Check
      one of each arrives readable, and that replies with `[CC]` reach the folder.
- [ ] **Alert on `total_warning`** (16) — the parser and its three outputs are deployed
      *(export 11-04)*; the IF after step 9 that logs and emails a total mismatch is
      not. Design record, fix 8.
- [ ] **FNC-001 never matches: step 10 saves a null Record ID** — first live test
      *(export 11-04)*: step 6 found the charge and step 9 took the yes side, but step
      10 set `matched_record_id` to null, so step 11 sent "no matching card
      transaction". Every receipt arriving after its statement is told it has no
      match. The export's pill reads as the loop's `Record ID`; re-drag it from step
      8's current item. Then test one receipt for a charge already loaded.
- [ ] **Card Holders names must match the statement's spacing** — FNC-003 compares
      names lower-cased with runs of spaces collapsed, so a name entered without its
      space never resolves, and the digest and Item Complete fall back to finance.
      Either enter names as the statement prints them or compare with spaces removed.
- [ ] **The AI step mis-files coding** — "Code this to <job> <cost code>" came back with
      the job as `reason` and no `project_code`. FNC-001 step 4's field descriptions
      ask for a "project code"; say a project is a job name or number, and the reason
      is the purpose of the purchase.
- [ ] **Image receipts dropped** (5) — convert to PDF before FNC-001, and have the
      intake act on a `failed` result.

- [ ] **Build coding after the receipt** — replies, the coding sheet, history and
      5-minute batched email, decided 2026-11-04 and built in the repo; the Workato
      side is the design record's "Coding after the receipt", steps 1-8, in order.
- [ ] **Charge Form once Item Complete stops emailing it** — attach it to the finance
      package, or drop it. Decide before step 6 of that build.

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
