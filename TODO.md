# TODO

Open engineering, deployment and documentation items, in priority order. An item
is removed when it is done, not ticked — `git log -- TODO.md` is the record.
Findings about a GC's own vendors and invoices do not go here.

---

## 1. Decisions waiting on you

- [ ] **Scope of the first build** — sub pay applications, vendor invoices or
      both, and how far the first version goes (intake and coding, approval,
      posting). `design/ap-bot-overview.md`.
- [ ] **Where approved invoices go** — the accounting system behind hh2, ACC
      Cost expenses, or a coded batch for AP staff to import. Name the
      accounting system.
- [ ] **AP mailbox** — its own address, or AP added to APM's classifier.
- [ ] **Approval rules** — who approves at which amount, per GC.

## 2. Before the first build

- [ ] **Measure on real data** — a real extract and a sample of invoices, per
      the overview's last section. Output is read, not committed.
- [ ] **Ask the APM chat for an `AP` document set** in the Claude connector, and
      for the upload recipe to cover this repo — `handoffs/ap-document-set.md`.
      Only once the first AP document exists.
- [ ] **Accounting integration** — whether hh2 or the accounting system has an
      API Workato can reach, and whether that is a connector in tenon-apm or here.

## 3. Repo

- [ ] **CI** — add a Python 3.9 test workflow, as tenon-apm's
      `.github/workflows/tests.yml`, when the first Python step and its tests land.
