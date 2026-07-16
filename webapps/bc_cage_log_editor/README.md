# BC Cage Log Editor — Dataiku Standard Webapp

An editable data grid over a single dataset, **`Bc_Cage_SP`**: shows the cage
log as a spreadsheet-style table, and lets the user **add new rows** and
**edit existing rows** in place. Every save overwrites `Bc_Cage_SP` with the
full table the app holds.

The form and table are generated **dynamically from the dataset schema**,
so column changes are picked up automatically.

## The dataset

The app reads and writes **`Bc_Cage_SP`** — sync it once from the cleaned
`bc_cage_log_prepared` (built by `python_recipes/clean_bc_cage_log.py` from
the messy `BC_Cage_Log` Excel import). That cleaned data:

- keeps the full Excel header names (`RACK ID`, `Date (START HERE)`,
  `Release/Repair Removal Date < 10 days`, … `Date Removed`);
- drops empty / near-empty rows (keeps real records even when `RACK ID`
  is blank);
- derives a **`Status`** column: `Open` while `Date Removed` is blank (item
  still in the cage), `Closed` once it has a date.

Dates are kept as text on purpose — the source dates have no year.

> Whole-table overwrite = last write wins, so this suits one editor at a
> time. The app reloads after every save to show the latest.

## Look & feel

BFGoodrich-themed data grid: brand top bar with the BFGoodrich logo, a
centered **BC CAGE LOG** title, a red→navy accent stripe, a compact sortable
grid (click a header to sort), a **per-column filter row**, a global search
box, coloured Open/Closed status pills, and an **Add entry** modal dialog.
Long Excel headers are shown as short labels (e.g. `Removal Date`,
`Recoup By`, `Date Out`) with the full name on hover.

Filters are **adaptive**: a column with up to ~40 distinct values renders as a
**dropdown** (Location, Responsible, Entered By, Disposition, Status,
Quantity…); higher-variety columns (Tire Code, dates) stay a text box with
autocomplete, since a dropdown of hundreds of values is unusable. Tune the
threshold via `DROPDOWN_MAX` in `webapp.js`.

The logo is loaded from `/local/static/BFGoodrich_logo.svg.png` (a file in
**Global Shared Code → Static Web Resources**). If your logo lives at a
different path, change the `src` of `#brand-logo` in `webapp.html`; a
missing logo is hidden automatically so the layout stays clean.

## Status is automatic

`Status` is **derived, never typed**. The add-entry form hides it; a new
entry is `Open` until someone fills in `Date Removed`, at which point the
backend recomputes it to `Closed` on save. The table shows a coloured
Open/Closed badge and a dropdown to filter by status.

## How it works

1. On load the app reads all rows of `Bc_Cage_SP` into memory.
2. **Add entry** opens a modal; the new row appears at the top of the grid,
   highlighted amber (red edge), as *unsaved*.
3. The **✎** button on any row opens the same modal pre-filled; edits mark
   the row *unsaved*, highlighted blue (navy edge). `Status` updates as soon
   as you fill/clear **Date Out**.
4. **Save changes** sends the whole in-memory table to the backend, which
   recomputes `Status` and overwrites `Bc_Cage_SP` with `write_with_schema`,
   then the grid reloads.

## Setup in Dataiku

1. Sync `bc_cage_log_prepared` into a dataset named **`Bc_Cage_SP`** (any
   writable connection).
2. **Webapps → + New webapp → Code webapp → Standard** (pick the
   "Simple webapp" starter), name it e.g. *BC Cage Log Editor*.
3. Paste each file into its tab:
   | File | Tab |
   |---|---|
   | `webapp.html` | HTML |
   | `webapp.js` | JS |
   | `webapp.css` | CSS |
   | `backend.py` | Python |
4. In the webapp **Settings → Security** (or the "Datasets" panel), grant
   `Bc_Cage_SP` → **Read/Write**.
5. Enable the Python backend (toggle in the Python tab) and **Start** it,
   then **Preview**.

## Endpoints (backend.py)

| Route | Method | Purpose |
|---|---|---|
| `/schema` | GET | Column names/labels/types + derived flag → grid + form |
| `/data` | GET | Current rows of `Bc_Cage_SP` |
| `/save` | POST | Overwrite `Bc_Cage_SP` with the full table (edits + additions) |
