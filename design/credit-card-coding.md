# Credit card coding

Status: **built in Workato, reviewed here; not changed.** Written 2026-11-04 from a
Workato export of the "Credit Card Coding" project (uploaded 2026-11-04, not committed —
it carries a client's address). The repo's copies of its parts are byte for byte what the
export held, so the first fix to any of them shows as a clean diff.

Cardholders on a GC's company cards email receipts; the bank's monthly statement arrives
as an .xlsx. The project logs both, matches each receipt to its card charge, chases what
is missing, and sends finance a PDF package per month and project with the receipts
behind it.

## What it is made of

Workato project **Credit Card Coding**. Every Outlook step uses the **APM Outlook account**
connection, from the Tenon APM project.

| recipe | trigger | does |
| --- | --- | --- |
| Credit Card Transaction and Receipt Reconciliation (Email Intake) | New email, APM Outlook account, no folder filter | Each attachment: a statement by file name → parse, insert new rows, then FNC-002; else AI-classify, and a receipt → FNC-001 |
| Process Receipt and Match Transaction (FNC-001) | Function | Extract the PDF's text, AI-parse its fields, log a Receipt, match, email the sender |
| Check All Logged Receipts Against Transactions (FNC-002) | Function | After a statement loads, try every unmatched receipt again |
| Resolve Cardholder Email (FNC-003) | Function | Card Holders lookup by name, case- and space-insensitive |
| Item Complete Confirmation Email | Receipts row updated | One email to the cardholder once matched, coded and with a file |
| Daily Open Items Follow-up Digest (RCP-002) | 08:00 UTC daily | Per cardholder: charges missing a receipt or coding |
| Daily Finance Package by Month and Project Code (RCP-003) | 08:00 UTC daily | Per receipt month × project: cover page + receipts as one PDF, emailed to finance, versioned |

| repo file | Workato step |
| --- | --- |
| `credit-card-coding/parse_statement.py` | Email Intake, step 6 (Python) |
| `credit-card-coding/classify_attachment.json` | Email Intake, step 15 (OpenAI utility, categorise text) |
| `credit-card-coding/extract_receipt_fields.json` | FNC-001, step 3 (OpenAI utility, parse text) |
| `credit-card-coding/open_items.py` | RCP-002, step 3 (Python) |
| `credit-card-coding/group_finance_package.py` | RCP-003, step 5 (Python) |
| `credit-card-coding/split_finance_package.py` | RCP-003, step 27 (Python) |
| `templates/finance_package_cover.html` + `.schema.json` | Message template "Finance Package Cover" |
| `templates/charge_form.html` + `.schema.json` | Message template "Charge Form" |

The two `.json` files are the steps' `input` as exported, datapills in `#{_dp(...)}`
form; add changes in the editor, not by pasting.

### Data tables

- **Transactions** — one per statement row: `transaction_id`, `transaction_date`,
  `merchant`, `amount` (credits negative), `card_last4`, `cardholder_name`,
  `cardholder_email` (never filled), `statement_month`, coding (`project_code`,
  `cost_code`, `reason`), `matched`, `matched_receipt_id`, `exempt`, `sent_in_package`,
  `package_version_sent`, `sent_date`.
- **Receipts** — one per receipt attachment: AI-read fields, `receipt_month`,
  `sender_email`, `message_id`, coding from the email body, `matched`,
  `matched_transaction_id`, `no_match_notified`, `receipt_file`, `email_body`,
  `confirmation_sent`.
- **Card Holders** — `cardholder_name`, `email`.
- **Exemption Rules** — `rule_type` (`vendor`: merchant contains the value;
  `max_amount`: a charge strictly below it), `value`, `active` (blank is active), `notes`.
  An exempt charge needs coding but no receipt.

### The rules as built

- **A statement** is recognised by its file name alone:
  `<CARDHOLDER NAME>_<masked card>_<number>_<YYYYMMDD>.xlsx`. The cardholder is the text
  before the first underscore; the statement month is the date's year and month. The
  parser takes the first sheet with a header holding Description, Charge, and Credit or
  Reference Number, plus two dates; the transaction date is the second. A month later
  than the statement's is the year before.
- **A match** is a receipt and an unmatched charge of exactly the same amount, plus any
  one of: same date, one merchant name containing the other, or same card last four. The
  first such charge wins.
- **No match** emails the sender once, and only if some statement for the receipt's
  calendar month is on file; otherwise the receipt waits for FNC-002.
- **Coding** (project, cost code, reason) is read from the email body only, never
  inferred from the receipt.
- **The finance package** holds matched charges, grouped by the receipt's month and
  project (blank → Unassigned). Each day's package for a group is the next version and
  carries everything sent before, with what is new listed first. A receipt with no file,
  an image that will not convert, or another file type holds its charge back.

## Findings

From reading the export and running the Python steps (`tests/test_credit_card.py`).
None is fixed. Most live in recipe steps rather than in the repo's files.

**Wrong output today**

1. **The daily digest's email is the finance package cover, empty.** RCP-002 steps 12
   and 18 render "Finance Package Cover" with no inputs, and steps 13 and 19 send that
   as the body. A cardholder asked for receipts gets a blank reconciliation-package
   page, not their list.
2. **"Receipt matched" and "No matching card transaction found" from FNC-001 are a blank
   Charge Form.** Steps 13 and 18 render "Charge Form" with no inputs. FNC-002 sends the
   same two emails as inline HTML that does name the receipt.
3. **A receipt matched after its statement keeps blank coding on the charge.** FNC-001
   copies project, cost code and reason to the Transaction at match time; FNC-002 step
   15 sets `matched` and `matched_receipt_id` only. A receipt sent before the statement
   — the normal order — leaves its charge uncoded, and RCP-002 asks for coding the
   cardholder already gave. Nothing copies a later edit of a Receipt's coding either.
4. **The cover page probably prints its tables as raw HTML.** It inserts four pre-built
   HTML tables with `{{...}}`, which Mustache escapes; tenon-apm's templates use
   `{{{...}}}` for HTML. Check one rendered package.
5. **Image receipts are lost.** The intake sends any receipt to FNC-001, whose first step
   reads text from a PDF. A phone photo fails there; FNC-001 returns `failed`, the
   intake does not read the result, and nothing is logged or sent. RCP-003 already knows
   how to turn an image into a PDF.

**Wrong in some cases**

6. **The intake listens to the APM mailbox, unfiltered.** Every email APM receives —
   drawings, submittals — has its attachments AI-classified, and a PDF read as a receipt
   is logged and its sender may be told no card charge matched. Give it its own mailbox
   or folder, or filter before classifying.
7. **No-match fires on the calendar month, and on any cardholder's statement.** A
   receipt dated Oct 28 belongs on a statement closing in November, but an October
   statement on file — anyone's — triggers "no matching card transaction" at once.
   Check the statement for that card (`card_last4`, else the cardholder) whose period
   covers the receipt date.
8. **A re-sent or overlapping statement duplicates charges.** `transaction_id` ends in
   the row's position in the file, so the same charge in another export gets a new id
   and passes the duplicate check (a KNOWN GAP check in the test proves it). Use
   card + date + amount + reference number, which the statement carries.
9. **A recurring charge can match the wrong month.** Same amount and same card is enough,
   whatever the dates, and the first unmatched charge wins — a monthly $49.99
   subscription receipt can take any month's charge. Prefer the nearest date; require the
   date within a window when only the card agrees.
10. **Everything stops at 1,000 rows.** RCP-002 reads the oldest 1,000 Transactions;
    RCP-003 the oldest 1,000 matched and any 1,000 matched Receipts; FNC-002 the first
    1,000 unmatched receipts. A few months in, the newest charges stop reaching the
    digest and the package, silently. Filter to what is open or unsent, and page.
11. **A receipt sent twice** is logged twice; the second finds its charge taken and the
    sender is told no charge matched.
12. **An exempt charge never reaches finance.** It needs no receipt, but the package takes
    matched charges only. Intended or not is a decision.

**Per-client values in recipe steps** (CLAUDE.md: they belong in account properties)

13. Finance's address is typed into RCP-003 step 34 and RCP-002 step 19, although step
    comments say it comes from a `finance_email` property.
14. The Charge Form names one bank's card ("VISA (BANK OF AMERICA)").
15. The statement file-name pattern and its columns are one bank's export.

**Other**

- The AI steps use Workato's OpenAI utility, not the Claude connector APM uses. Whether
  AP moves to Claude is open.
- Both daily recipes run at 08:00 UTC — 3 or 4 AM in New York.
- `cardholder_email` on Transactions is never written; the digest resolves the address
  each run through FNC-003.

## Getting it running: testing on the APM mailbox

Decided by the owner (2026-11-04): testing runs on the APM mailbox; the project gets its own
mailbox later. Nothing in it calls ACC, so it needs no SSA until it does. These are the
fixes that block a useful test, in order; findings 7-15 wait. Steps are numbered as the
editor shows them in the 2026-11-04 export.

**Before switching anything on**

1. **Keep the two products out of each other's mail** (finding 6). Credit card mail goes
   to the APM address with a plus tag, `apm+cc@…` (owner, 2026-11-04). Exchange Online
   delivers it to the APM mailbox and keeps the tagged address on the message. In
   Outlook on the APM mailbox, add a rule: recipient address includes `apm+cc` **or**
   subject contains `[CC]` → move to a new folder `Credit Cards`, stop processing more
   rules. In Email Intake, set the New email trigger's folder to `Credit Cards`. A rule
   runs on delivery, so APM's recipes, watching the inbox, never see these emails and
   this recipe never sees APM's. The subject half is for replies: the recipes send from
   the plain APM address, so a cardholder's reply comes back without the tag. If the
   trigger offers no folder, add a trigger condition on the same two tests instead and
   accept that APM still sees the test emails.
   - Plus addressing must be on for the tenant. It is by default; an admin can confirm
     with `Get-OrganizationConfig | fl DisablePlusAddressInRecipients` (False is on).
   - A sender who Bccs the address leaves no tagged recipient on the message; ask
     testers to put it in To.
2. **Send finance mail to yourself.** RCP-003 step 34 and RCP-002 step 19 have a client's
   finance address typed in. Put your own in for testing; an account property
   `CC_FINANCE_EMAIL` replaces it before a client.
3. **Fill Card Holders** with each test cardholder's name exactly as the statement file
   name starts, and their email.

**Fix**

4. **Digest emails** (finding 1). In RCP-002 delete steps 12 and 18 (the template
   renders). Step 13's Content, in formula mode, with the loop's `items` pill:
   `'<p>These card charges need a receipt or coding:</p><table border="1" cellpadding="4" style="border-collapse:collapse"><tr><th>Date</th><th>Merchant</th><th>Amount</th><th>Missing</th></tr>' + items.format_map('<tr><td>%{transaction_date}</td><td>%{merchant}</td><td>%{amount}</td><td>%{missing_summary}</td></tr>').join + '</table><p>Reply with the receipt attached and the project, cost code and reason in the email.</p>'`.
   Step 19 the same over the `finance_fallback_items` list pill, with a first column for
   `%{cardholder_name}`. Start step 13's subject with `[CC] ` so a reply reaches the
   `Credit Cards` folder.
5. **FNC-001's two emails** (finding 2). Delete steps 13 and 18. Give steps 14 and 19
   the inline HTML FNC-002 steps 17 and 23 already use, mapping the pills to step 3's
   parsed `receipt_number`, `merchant`, `receipt_date`, `amount`, `currency`, and for
   the no-match month step 4's `receipt_month`.
6. **FNC-002 copies coding to the charge** (finding 3). Step 15 (update Transactions):
   add `project_code`, `cost_code` and `reason`, each from the receipt loop's (step 6)
   field of the same name — as FNC-001 step 12 does.
7. **Cover page** (finding 4). Paste `templates/finance_package_cover.html` into the
   Finance Package Cover template: its four tables now print with `{{{ }}}`.

**How to test**

- Email receipts as **PDFs** to `apm+cc@…`, with the coding in the body —
  `Project: …  Cost code: …  Reason: …`. Phone photos are dropped until finding 5 is
  fixed, and there is no way yet to add coding by reply.
- Name the statement `<CARDHOLDER NAME>_<masked card>_<number>_<YYYYMMDD>.xlsx`, e.g.
  `PAT SAMPLE_4111xxxxxxxx1234_1_20261105.xlsx`, and send it the same way.
- Send a receipt before its statement and one after: the first is matched by FNC-002,
  the second by FNC-001, and each charge should end up coded.
- Run RCP-002 and RCP-003 by hand from the editor rather than waiting for 08:00 UTC.

## Open decisions

- Fix in place, in the order above, or rebuild on the AP design (Claude, ACC, own mailbox).
- Where coded charges finally go — today a PDF to finance, re-keyed by hand.
- Whether project codes should be checked against ACC's projects, and cost codes against
  the project's budget codes, before a charge counts as coded.
