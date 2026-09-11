# family_economy

A household expense tracker. It ingests credit-card and bank exports, separates
recurring fixed expenses from variable ones, and reports monthly totals and a
monthly average. Generic: any family enters their own files and categories.

Read `docs/design.md` before making design decisions — it is the agreed
architecture, and section 16 documents both real file formats.

## Tech stack

- **Backend**: Python 3.12, FastAPI (async), Pydantic v2, SQLAlchemy 2.0 +
  aiosqlite, Alembic, pandas + openpyxl, pdfplumber. Package manager: uv.
- **Frontend**: React 19 + TypeScript + Vite, Tailwind CSS, shadcn/ui,
  TanStack Query, TanStack Table, Recharts, i18next.
- **Storage**: SQLite at `data/household.db`, path from `HOUSEHOLD_DB_URL`.
- FastAPI serves the built frontend — one process, one container.

## Commands

```bash
uv sync                                  # backend deps
uv run uvicorn app.main:app --reload     # API on :8000
uv run pytest                            # tests
uv run ruff check . && uv run ruff format .
cd frontend && npm install && npm run dev   # UI on :5173, proxies /api
```

## Structure

```
backend/app/{api,models,db,importers,services,agents}
frontend/src/{pages,components,charts,api,lib,i18n}
tests/            docs/            data/   (gitignored)
```

## Domain rules — these are easy to get wrong and were learned the hard way

1. **Money is `Decimal`. Never `float`.** Anywhere, including tests.
2. **Reports key on `billing_month`, not transaction date.** A purchase on the
   28th is charged the following month.
3. **Never sum the card export's `סכום עסקה מקורי` for installments** — it holds
   the whole deal amount, not this month's payment. Use `סכום חיוב`.
4. **Dedupe keys include an occurrence counter within the source file.** Two
   genuinely identical transactions (same merchant, day, card, amount) do occur;
   content-only keys silently delete one. Re-importing a file must still dedupe.
5. **Bank credit-card settlement lines are transfers, not expenses** — the card
   file carries the detail. If a settlement has no matching card file, keep it as
   an expense under "credit — no detail" and warn. Never let money vanish.
6. **Utility bills (electricity, water, municipal tax) arrive through the credit
   card as standing orders, not through the bank.** Do not assume otherwise.
7. **Bimonthly bills are normalized before averaging.** The monthly average uses
   the last 12 *complete* months; the current partial month is excluded.
8. **Recurring series cluster by description AND amount.** One mortgage can post
   as two lines with the same description and different amounts.
9. **The `הוראת קבע` note in the card export is a definitive recurring flag.**
   Statistical cadence detection is only for what is not flagged.
10. **The card issuer already supplies a category per transaction.** That is the
    seed. Rules next. The LLM is last, receives merchant names only — never
    amounts, dates, or account numbers — and its answer is stored as a rule.

## Bank PDF parsing (Leumi)

The bank exports PDF, not Excel. Text extraction returns Hebrew reversed, both
character order within a word and word order within a line. Parse by position:
`extract_words`, sort right-to-left, reverse Hebrew tokens. Group words into
lines by a ~3px tolerance, never by rounding `top` into buckets. Resolve
debit vs credit from the running balance (`previous − amount == current`), and
**let the balance chain continue across page boundaries** — resetting it per
page breaks exactly the large rows that sit on the seam.

## Privacy — non-negotiable

- `data/` is gitignored. Bank files, card exports and the DB never enter git.
- **Never put real amounts, merchant names, account numbers or card digits into
  commits, PR bodies, docs, or code comments.** Test fixtures are anonymized.
- Card numbers are stored as last 4 digits only. API keys live in `.env`.

## Conventions

- Type hints everywhere; async for all API endpoints.
- Pydantic models for every request and response; TS types generated from the
  OpenAPI schema so the frontend cannot drift from the backend.
- RTL first: logical CSS properties only (`ms-*`/`me-*`), never `left`/`right`.
  Format numbers and dates with `Intl.NumberFormat('he-IL', …)`.
- Tests make no network or LLM calls.
