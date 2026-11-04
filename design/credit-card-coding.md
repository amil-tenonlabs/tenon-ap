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
| `credit-card-coding/parse_statement.py` | Email Intake, step 7 (Python) |
| `credit-card-coding/classify_attachment.json` | Email Intake, step 16 (OpenAI utility, categorise text) |
| `credit-card-coding/extract_receipt_fields.json` | FNC-001, step 4 (OpenAI utility, parse text) |
| `credit-card-coding/open_items.py` | RCP-002, step 4 (Python) |
| `credit-card-coding/group_finance_package.py` | RCP-003, step 6 (Python) |
| `credit-card-coding/split_finance_package.py` | RCP-003, step 28 (Python) |
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

1. **The daily digest's email is the finance package cover, empty.** RCP-002 steps 13
   and 19 render "Finance Package Cover" with no inputs, and steps 14 and 20 send that
   as the body. A cardholder asked for receipts gets a blank reconciliation-package
   page, not their list.
2. **"Receipt matched" and "No matching card transaction found" from FNC-001 are a blank
   Charge Form.** Steps 14 and 19 render "Charge Form" with no inputs. FNC-002 sends the
   same two emails as inline HTML that does name the receipt.
3. **A receipt matched after its statement keeps blank coding on the charge.** FNC-001
   copies project, cost code and reason to the Transaction at match time; FNC-002 step
   16 sets `matched` and `matched_receipt_id` only. A receipt sent before the statement
   — the normal order — leaves its charge uncoded, and RCP-002 asks for coding the
   cardholder already gave. Nothing copies a later edit of a Receipt's coding either.
4. **The cover page probably prints its tables as raw HTML.** It inserts four pre-built
   HTML tables with `{{...}}`, which Mustache escapes; tenon-apm's templates use
   `{{{...}}}` for HTML. Check one rendered package.
5. **Image receipts are lost.** The intake sends any receipt to FNC-001, whose first step
   reads text from a PDF. A phone photo fails there; FNC-001 returns `failed`, the
   intake does not read the result, and nothing is logged or sent. RCP-003 already knows
   how to turn an image into a PDF.

16. **A page packed into one cell was dropped — fixed in the repo, 2026-11-04.** A bank
    PDF converted to Excel can put a page's header in one cell and its rows in another,
    one per line, out of column alignment. The parser found no charge in the Charge
    column and skipped them: on the first real statement tested, 3 of 14 charges and $752
    of $1,023 (a DocuSign charge among them). `_unpack` now reads each line - date, date,
    description, reference, MCC, amount - into the header's columns; a line with one
    amount is a charge, since position cannot show a credit. Every statement is now also
    held to its own "Total Activity": `total_warning` names any difference, and says so
    when no total is printed.

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
   card + date + amount + reference number, which the statement carries - read as text:
   Excel stores a column-laid reference as a number, losing digits, so on the first real
   statement two different MTA charges showed the same reference.
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

13. Finance's address is typed into RCP-003 step 35 and RCP-002 step 20, although step
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
editor shows them in the 2026-11-04 export, the trigger being step 1. Deleting a step
renumbers every step below it, so work through each recipe from its last change up.

**Before switching anything on**

1. **Keep the two products out of each other's mail** (finding 6). Every credit card
   email carries `[CC]` in its subject (owner, 2026-11-04; a plus-tagged address was
   considered and dropped). In Outlook on the APM mailbox, add a rule: subject contains
   `[CC]` → move to a new folder `Credit Cards`, stop processing more rules. In Email
   Intake, set the New email trigger's folder to `Credit Cards`. A rule runs on delivery,
   so APM's recipes, watching the inbox, never see these emails and this recipe never
   sees APM's. A reply keeps the tag ("RE: [CC] …"), so every email the recipes send
   starts its subject with `[CC] ` — FNC-001 steps 15 and 20, FNC-002 steps 18 and 24,
   RCP-002 steps 14 and 20, RCP-003 step 35, Item Complete step 16. A sender who forgets
   the tag reaches APM's inbox instead. If the trigger offers no folder, add a trigger
   condition on the subject instead and accept that APM still sees the test emails.
2. **Send finance mail to yourself.** RCP-003 step 35 and RCP-002 step 20 have a client's
   finance address typed in. Put your own in for testing; an account property
   `CC_FINANCE_EMAIL` replaces it before a client.
3. **Fill Card Holders** with each test cardholder's name exactly as the statement file
   name starts, and their email.

**Fix**

4. **Digest emails** (finding 1). In RCP-002 delete steps 13 and 19 (the template
   renders). Step 14's Content, in formula mode, with the loop's `items` pill:
   `'<p>These card charges need a receipt or coding:</p><table border="1" cellpadding="4" style="border-collapse:collapse"><tr><th>Date</th><th>Merchant</th><th>Amount</th><th>Missing</th></tr>' + items.format_map('<tr><td>%{transaction_date}</td><td>%{merchant}</td><td>%{amount}</td><td>%{missing_summary}</td></tr>').join + '</table><p>Reply with the receipt attached and the project, cost code and reason in the email.</p>'`.
   Step 20 the same over the `finance_fallback_items` list pill, with a first column for
   `%{cardholder_name}`. Start step 14's subject with `[CC] ` so a reply reaches the
   `Credit Cards` folder.
5. **FNC-001's two emails** (finding 2). Delete steps 14 and 19. Give steps 15 and 20
   the inline HTML FNC-002 steps 18 and 24 already use, mapping the pills to step 4's
   parsed `receipt_number`, `merchant`, `receipt_date`, `amount`, `currency`, and for
   the no-match month step 5's `receipt_month`.
6. **FNC-002 copies coding to the charge** (finding 3). Step 16 (update Transactions):
   add `project_code`, `cost_code` and `reason`, each from the receipt loop's (step 7)
   field of the same name — as FNC-001 step 13 does.
7. **Cover page** (finding 4). Paste `templates/finance_package_cover.html` into the
   Finance Package Cover template: its four tables now print with `{{{ }}}`.

8. **Statement parser** (finding 16). Paste `credit-card-coding/parse_statement.py` into
   Email Intake step 7's code, whole. Append three string fields to that step's output
   schema - `statement_total`, `parsed_total`, `total_warning` - never regenerate it.
   Then, after step 9 (the ignored-rules warning), add an IF: `total_warning` is
   present → Log message (WARN) with the file name and `total_warning`, and Send email
   to the tester, subject `[CC] Statement total check: ` + file name. Re-sending a
   statement already loaded adds only the rows that were missing: rows read before keep
   their ids.

**How to test**

- Email receipts as **PDFs** with `[CC]` in the subject and the coding in the body —
  `Project: …  Cost code: …  Reason: …`. Phone photos are dropped until finding 5 is
  fixed, and there is no way yet to add coding by reply.
- Name the statement `<CARDHOLDER NAME>_<masked card>_<number>_<YYYYMMDD>.xlsx`, e.g.
  `PAT SAMPLE_4111xxxxxxxx1234_1_20261105.xlsx`, and send it the same way.
- Send a receipt before its statement and one after: the first is matched by FNC-002,
  the second by FNC-001, and each charge should end up coded.
- Run RCP-002 and RCP-003 by hand from the editor rather than waiting for 08:00 UTC.

## Coding after the receipt: replies, spreadsheets, history and batched email

Decided by the owner (2026-11-04): a charge reaches finance only once it is coded; coding
can arrive by reply or by spreadsheet as well as with the receipt; a cardholder's own
consistent history codes a charge without asking; and people get one email per burst of
activity, never one per receipt. **Built in the repo, not yet in Workato.** Checks pass
(`tests/test_coding.py`, `tests/test_credit_card.py`); needs testing in Workato.

### The rules

- **Coding lives on the charge.** Transactions' `project_code`, `cost_code` and `reason`
  are the record; the package groups by the charge's project, the receipt's only as a
  fallback. A field is filled, never blanked: every update keeps what is there when it
  brings nothing for a field.
- **Every item has a reference**, printed on every email and spreadsheet row: a charge
  is its `transaction_id` (`8678-20261029-606.00-14`), a receipt with no charge yet is
  `R-` + its Record ID.
- **A reply codes what it names.** Only the reply's own text counts, never the quoted
  email below it. One line per item, `Ref: project, cost code, reason`, codes many at
  once; the reason keeps any commas of its own. A reply in a thread about one item can
  say it in words ("Project: Perry", or "code this to Perry 01-750", read by the AI). Two
  references and no coded line is asked about, never guessed.
- **The spreadsheet** is the digest's attachment: one row per open item, the coding
  columns pre-filled with any suggestion and shaded to fill in. Sent back, every row with
  coding is applied - returning it unchanged confirms its suggestions - and a row whose
  reference is not one is reported by its row number.
- **History.** When a charge has blank coding and the cardholder's two most recent
  explicitly coded charges at the same merchant agree, that coding fills the blanks,
  marked `coding_source` `history` with `history_coded_on`. Coding applied from history
  never counts as evidence for more, so a guess cannot confirm itself. Anything less
  certain is a suggestion only. Merchants compare on their first two words, filler and
  state codes dropped ("DOCUSIGN INC. 800-3799973 DE" is "DocuSign Inc").
- **Finance gets coded charges only.** A new charge with any of the three blank is held
  (`held_uncoded_count`, and a line in the log). History coding waits a day, so the
  cardholder has seen it in one email before it goes.
- **Email in bursts.** Recipes queue a row in Notifications instead of emailing. Every 5
  minutes one recipe sends each person one email holding everything queued for them,
  once nothing new has been queued for 5 minutes - a 10-receipt email gets one answer.
  The daily digest stays its own email.

### Repo parts

| repo file | Workato step |
| --- | --- |
| `credit-card-coding/read_coding_reply.py` | Email Intake, reply branch (new) |
| `credit-card-coding/read_coding_sheet.py` | Email Intake, spreadsheet branch (new) |
| `credit-card-coding/suggest_coding.py` | RCP-002, after its Search (new) |
| `credit-card-coding/build_coding_sheet.py` | RCP-002, inside the cardholder loop (new) |
| `credit-card-coding/batch_notifications.py` | Send Queued Notifications (new recipe) |
| `credit-card-coding/split_shares.py` | FNC-004 Apply Coding, split path (new) |
| `credit-card-coding/open_items.py` | RCP-002 step 4 (changed: carries suggestions) |
| `credit-card-coding/group_finance_package.py` | RCP-003 step 6 (changed: holds uncoded) |
| `credit-card-coding/extract_receipt_fields.json` | FNC-001 step 4 (changed: field descriptions, file name) |

### Build steps

Steps are numbered as the editor showed them in the 2026-11-04 (second) export. Build in
this order: each part works before the next is switched on.

**1. Data tables**

- Transactions: add `coding_source` (short text) and `history_coded_on` (date).
- New table **Notifications**: `recipient`, `kind`, `ref`, `merchant`, `date`,
  `currency`, `project_code`, `cost_code`, `reason` (short text), `amount` (number),
  `note` (long text), `sent` (boolean), `sent_at` (date-time). `kind` is one of
  `received`, `matched`, `no_match`, `coded`, `history`, `complete`, `problem`.

**2. Send Queued Notifications** (new recipe; nothing is queued yet, so it sends nothing)

1. Trigger: Scheduler, every 5 minutes.
2. Search records, Notifications, `sent` is false, limit 1000, field name to value.
3. Execute Python code, `batch_notifications.py`; inputs `notifications_json` =
   step 2's Records `.to_json`, `now` = `now.iso8601`, `quiet_minutes` = `5`; outputs
   `batches` (list: `recipient`, `subject`, `html`, `summary`, `record_ids` list of
   strings, `count`), `batch_count`, `waiting_count`.
4. Repeat for each `batches`: Outlook Send email, To `recipient`, Subject `subject`,
   Content `html` (HTML); then Update records batch, Notifications, source
   `record_ids`, Record ID = the current id, `sent` true, `sent_at` now.

Rows are marked sent only after their email goes, so a failed send is retried on the next
run.

**3. FNC-004 Apply Coding** (new callable recipe)

Input: `updates` (list: `ref`, `ref_type`, `project_code`, `cost_code`, `reason`),
`source` (`email`, `reply`, `sheet` or `history`), `notify_email`. For each update:

- `ref_type` `transaction`: Search Transactions, `transaction_id` = `ref`, limit 1. None →
  queue a `problem` ("Ref … was not found") to `notify_email`; next. Else Update the
  Transactions record: each field `= [update field].presence || [record field]`;
  `coding_source` = `source`; `history_coded_on` = `source == 'history' ? today :
  [record history_coded_on]`. If the record's `matched_receipt_id` is present, Update
  that Receipts record with the same three merged values.
- `ref_type` `receipt`: Get the Receipts record by Record ID = `ref`. None → `problem`.
  Else update it the same way; if its `matched_transaction_id` is present, Search
  Transactions by it and update that charge with the merged values and `coding_source`.
- Queue a Notifications row: `kind` = `source == 'history' ? 'history' : 'coded'`,
  `recipient` = `notify_email`, `ref`, and merchant, date, amount and the merged coding
  from the record.

Return `applied` and `not_found` counts.

**4. Email Intake**

1. Trigger condition: subject **contains** `[CC]` (not starts with), and remove "has
   attachments" - a reply with only text must come in.
2. First step inside the Try: Execute Python code, `read_coding_reply.py`, `body` = the
   body with tags stripped (as step 18's `email_body` formula); outputs `ref_count`,
   `updates` (list as FNC-004's), `update_count`, `needs_ai`, `single_ref`,
   `single_ref_type`, `new_text`, `problems`.
3. IF `ref_count` > 0:
   - IF `needs_ai`: OpenAI parse text on `new_text` with three fields - `project_code`,
     `cost_code`, `reason`, described as in `extract_receipt_fields.json` - then call
     FNC-004 with one update: `single_ref`, `single_ref_type` and the three parsed
     fields.
   - IF `update_count` > 0: call FNC-004 with `updates`.
   - Each FNC-004 call: `source` `reply`, `notify_email` = the sender.
   - IF `problems` present: queue a `problem` row to the sender with `note` = `problems`.
4. The attachments loop only when the email has attachments (an IF around it).
5. Inside it, before the AI classifier, IF the name ends `.xlsx` (and is not a
   statement): Execute Python code, `read_coding_sheet.py` (`file_content_base64` as the
   statement step takes it); IF `is_coding_sheet`: FNC-004 with `updates`, `source`
   `sheet`; queue a `problem` if `problems`; skip the classifier for this file.
6. The receipt branch: add AND the name ends `.pdf`, so an image or logo is skipped
   rather than failing (finding 5 stays open for photos).

**5. FNC-001 Process Receipt**

- Step 4 (AI parse): replace the three coding field descriptions with
  `extract_receipt_fields.json`'s, and in the text formula insert the
  `=== THIS RECEIPT'S FILE NAME ===` section before the email body, with the trigger's
  `attachment_name` - so one email can code several receipts differently.
- Step 14 (matched email) → Create record, Notifications, `kind` `matched`, recipient the
  sender, `ref` = the transaction id (step 15's formula), merchant, date, amount,
  currency and coding from step 5.
- Step 18 (no-match email) → the same with `kind` `no_match`, `ref` = `'R-' + ` step 5's
  Record ID, `note` = "Not on the " + receipt_month + " statement".
- Before step 21 (no statement yet): queue `kind` `received`, `ref` `R-` + Record ID.

**6. FNC-002 and Item Complete**

- FNC-002 steps 18 and 24 → Notifications rows as FNC-001's, from the receipt loop.
- Item Complete step 16 → a `complete` row. The Charge Form stops being emailed; whether
  it belongs in the finance package instead is open.

**7. RCP-002 Daily digest**

1. After step 3 (Search Transactions): Execute Python code, `suggest_coding.py`,
   `records_json` = step 3's Records `.to_json`; outputs `apply` (list as FNC-004's
   updates, plus `cardholder_name`), `apply_count`, `suggested_count`, `records_json`.
2. IF `apply_count` > 0: Repeat for each `apply` → FNC-003 for the cardholder's email →
   FNC-004 with that one update, `source` `history`, `notify_email` the email (finance
   when unresolved).
3. Step 4 (open items): its `records_json` becomes step 1's `records_json`. Paste
   `open_items.py`; append to `groups` → `items`: `suggestion`, `suggested_project_code`,
   `suggested_cost_code`, `suggested_reason`.
4. Inside the cardholder loop, before the email: Execute Python code,
   `build_coding_sheet.py`, `items_json` = the loop's `items` `.to_json`, `label` = its
   `cardholder_name`, `today` = `today.strftime('%Y-%m-%d')`; outputs `file_name`,
   `file_base64`, `row_count`. Attach it to the email (file name, contents
   `file_base64.decode_base64`).
5. The email's table gains a Ref column (`%{transaction_id}`) and a Suggested column
   (`%{suggestion}`), and its closing line reads: "Reply with `Ref: project, cost code,
   reason` per line, or fill in the attached sheet and send it back, with [CC] in the
   subject."

**8. RCP-003 Finance package**

- Step 6: paste `group_finance_package.py`; add an input `today` =
  `today.strftime('%Y-%m-%d')`; append the output `held_uncoded_count` and add it to
  step 7's log line.

### Splits: one charge across projects

Decided by the owner (2026-11-04): a charge can be split across projects and cost codes, and
its receipt goes into each project's package. Built in the repo with the rest of this
section; checks pass, needs testing in Workato.

- **Entered** as one line or one sheet row per share, the same reference on each, each with a
  share: `$400` or `60%` in a reply (a bare number never counts there, since it could be a
  cost code), or the sheet's **Split share** column, where a plain number is dollars. On a
  receipt email the AI step fills `split_text`, one share per line as
  `project | cost code | share | reason`. Lines for one charge without a share on each are
  not a split: the first is used and the sender is told.
- **Checked** by `split_shares.py` against the charge: percentages become dollars, the last
  percentage share takes any rounding cent, a credit splits as a credit, and shares that do
  not add up apply nothing and say by how much. A field blank on a share is filled from the
  charge's own coding, then from the one value the other shares agree on; a share still
  missing one is refused. One share of the whole charge is ordinary coding.
- **Stored** in a **Splits** table, one row per share. The charge's own fields hold a summary
  (`Split: Perry / Oak St`, the cost codes, the reasons) so the digest counts it coded, and
  `coding_source` is `split`, so it never feeds the history rule.
- **Packaged** one entry per share, in its own project's group, at its share, with the line
  "Split: 400.00 of 606.00 (also Oak St 02-100 206.00)"; the receipt goes in each package.
  Each share is sent and versioned on its own Splits row, so one project's package cannot
  mark another's share sent. Shares that do not total the charge hold it.

**Build, on top of steps 1-8 above**

1. Data table **Splits**: `transaction_id`, `project_code`, `cost_code`, `reason` (short
   text), `amount` (number), `sent_in_package` (boolean), `package_version_sent` (short
   text), `sent_date` (date-time).
2. Email Intake: `read_coding_reply.py` and `read_coding_sheet.py` (the sheet's Split share
   column) each gain `shares` on every update - append to `updates` a list `shares` of
   `project_code`, `cost_code`, `reason`, `share`. The AI step on a reply adds `split_text`
   as FNC-001 step 4 has it.
3. FNC-004 Apply Coding: its update input gains `shares` (as above) and `split_text`. For a
   charge whose update has either, Execute Python code `split_shares.py`: `charge_amount` =
   the charge's amount, `shares_json` = `shares.to_json`, `split_text`, and the charge's
   current `project_code`, `cost_code`, `reason`; outputs `ok`, `is_split`, `shares` (list:
   `project_code`, `cost_code`, `reason`, `amount`, `amount_text`), `problems`,
   `project_code`, `cost_code`, `reason`, `split_note`.
   - Not `ok`: queue a `problem` with `problems`; change nothing.
   - `ok` and `is_split`: delete the charge's Splits rows (Search by `transaction_id`, then
     Delete records), Create one per share, and update the charge with the summary
     `project_code`, `cost_code`, `reason` and `coding_source` `split`. Queue a `coded` row
     whose `note` is `split_note`.
   - `ok`, not `is_split`: the ordinary path with the returned three fields.
   A split given for a receipt with no charge yet waits: store `split_text` on the Receipts
   row (a new long-text field) and apply it when FNC-001 or FNC-002 matches the receipt.
4. FNC-001 step 4: append the `split_text` field from `extract_receipt_fields.json`. After
   step 13 (charge matched), IF `split_text` is present → FNC-004 with one update: `ref` =
   the transaction id, `ref_type` `transaction`, `split_text`, `source` `email`.
5. RCP-003: after step 4, Search Splits (all rows, limit 1000, field name to value). Step 6
   gains the input `splits_json` = those Records `.to_json`. Step 28's output gains
   `mark_sent_splits` (list: `record_id`, `transaction_id`); after step 36's batch update of
   Transactions, Update records batch on **Splits** from `mark_sent_splits`, with the same
   `sent_in_package`, `package_version_sent` and `sent_date` values. Step 28's inputs are
   unchanged; the items it receives now carry `table`, `cost_code` and `split_note`.

## Reading receipts with Claude: photos, scans and PDFs

Proposed 2026-11-04 to fix finding 5; built in the repo, not in Workato. Checks pass
(`tests/test_read_receipt.py`), needs testing in Workato.

**Why this way.** The Claude connector in tenon-apm sends a file only as a `document`
block, which takes a PDF and not a JPG or PNG; Claude reads a PDF's pages as images, so a
photo converted to a one-page PDF is read as well as the photo itself. PDF tools already
converts images in RCP-003. Nothing in the shared connector changes. Claude reads every
receipt, text PDF or photo, so there is one path, and it reads the email's coding and splits
in the same call. Workato's OpenAI step stays only as the intake's classifier for non-image
files.

**The rules**

- An attachment that is an image (jpg, jpeg, png, gif, webp, heic, heif, tif, tiff) and not
  inline is a receipt candidate: converted to PDF and sent straight to FNC-001, never through
  the classifier, which sees only a file name. Inline images are signatures and logos and are
  skipped.
- Claude returns one JSON object (`read_receipt_prompt.txt`); `read_receipt.py` checks it. A
  reply that is not that object logs nothing. `is_receipt` false (a logo, a photo of
  something else) logs nothing and tells the sender what it saw. A total that cannot be read
  is blank, never zero, and the sender is asked for a clearer copy; the receipt is still
  logged with its file.
- The amount is the final total charged - tax, tip and fees in, discounts out; a handwritten
  tip and total on a restaurant slip win over the printed subtotal.
- A year that is not printed is left blank, not guessed.
- The email body is data, not instructions: the prompt says so, as APM's classifier does.

**Build**

1. **Claude connection** in the Credit Card Coding project, or use APM's: the Claude Platform
   on AWS connector from tenon-apm. Per tenon-apm's CLAUDE.md, a client's connections use the
   Anthropic workspace prod-tenon uploads to; this call uploads nothing, so any workspace
   works.
2. **Email Intake.** Add an **Else if** to step 5 (the statement-file IF), above its Else:
   - Condition: `['jpg','jpeg','png','gif','webp','heic','heif','tif','tiff'].include?(Name.to_s.downcase.split('.').last)`
     is true, AND `IsInline` is not true.
   - PDF tools **Convert to PDF**: file format `image`; source file =
     `ContentBytes.to_s.gsub(/\s/, '').match?(/\A[A-Za-z0-9+\/]+={0,2}\z/) ? ContentBytes.to_s.gsub(/\s/, '').decode_base64 : ContentBytes`;
     output file name = `Name.to_s.sub(/\.[^.]+\z/, '')`.
   - Call FNC-001 as step 18 does, but `attachment_content` = the converted file's contents
     `.encode_base64` and `attachment_name` = `Name.to_s.sub(/\.[^.]+\z/, '') + '.pdf'`.
   - Wrap the conversion in a Try; on error, email the sender "[CC] Could not read " + Name
     + " - please send it as a PDF or a JPG".
   - Step 17's receipt condition gains AND the name ends `.pdf`, so a file the classifier
     calls a receipt but no reader can open is skipped.
3. **FNC-001.** Insert, as the first steps inside the Try:
   - Claude **Send message**: System prompt = `read_receipt_prompt.txt` pasted whole (it has
     no datapills); User message = `FILE NAME: ` + `attachment_name`, a blank line,
     `EMAIL BODY:`, then `email_body` (or `(none)` when blank); Document (base64) = the
     trigger's `attachment_content`; media type `application/pdf`; title = `attachment_name`;
     Max tokens 1024. Model override optional - a larger model reads faded photos better.
   - Execute Python code, `read_receipt.py`: input `response_text` = the Claude step's
     Response text; outputs `ok`, `is_receipt` (boolean), `merchant`, `receipt_date`,
     `receipt_month`, `amount` (number), `currency`, `card_last_4`, `receipt_number`,
     `project_code`, `cost_code`, `reason`, `split_text`, `notes`, `problems`.
   - IF `ok` is not true OR `is_receipt` is not true: email the sender "[CC] Not read as a
     receipt: " + `attachment_name`, body `notes` or `problems`; Return result `status`
     `not_receipt`, `matched` false. (Once Notifications exists, queue a `problem` instead.)
   - Re-point every pill that read the OpenAI step to the Python step: step 5's nine fields
     (receipt_number, receipt_date in its formula, merchant, amount, currency, card_last4 in
     its formula, project_code, cost_code, reason) and step 6's amount filter. Then delete
     the old extract-text and OpenAI steps; Workato refuses if anything still reads them.
   - IF `problems` is present after logging: email the sender "[CC] Receipt received -
     please check " + `attachment_name` with `problems`. It is still matched as usual.
4. Test with one phone photo of a receipt, one scanned PDF and one email signature image:
   two logged and one skipped.

## Open decisions

- Fix in place, in the order above, or rebuild on the AP design (Claude, ACC, own mailbox).
- Where coded charges finally go — today a PDF to finance, re-keyed by hand.
- Whether project codes should be checked against ACC's projects, and cost codes against
  the project's budget codes, before a charge counts as coded.
