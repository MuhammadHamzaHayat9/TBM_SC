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

`Bc_Cage_SP` is a **PostgreSQL** dataset, so the app writes **per row**:
`INSERT` for a new row, `UPDATE ... WHERE row_id = ...` for an edit — it does
**not** rewrite the whole table. This needs a stable key column **`row_id`**;
add it once with the setup script below.

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

1. On load the app reads all rows of `Bc_Cage_SP` (incl. `row_id`) into memory.
   `row_id` is hidden from the grid and the form.
2. **Add entry** opens a modal; the new row appears at the top of the grid,
   highlighted amber (red edge), as *unsaved*.
3. The **✎** button on any row opens the same modal pre-filled; edits mark
   the row *unsaved*, highlighted blue (navy edge). `Status` updates as soon
   as you fill/clear **Date Out**.
4. **Save changes** sends only the changed rows. The backend runs one `INSERT`
   per new row (assigning `row_id` = max+1) and one `UPDATE ... WHERE row_id`
   per edited row, in a single transaction with `COMMIT`, then the grid reloads.

## Setup in Dataiku

1. Sync `bc_cage_log_prepared` into a **PostgreSQL** dataset named
   **`Bc_Cage_SP`**.
2. **Add the `row_id` key once** — run `python_recipes/add_row_id.py` in a
   notebook (reads `Bc_Cage_SP`, adds `row_id` = 1…N, writes back once).
3. **Webapps → + New webapp → Code webapp → Standard** (pick the
   "Simple webapp" starter), name it e.g. *BC Cage Log Editor*.
3. Paste each file into its tab:
   | File | Tab |
   |---|---|
   | `webapp.html` | HTML |
   | `webapp.js` | JS |
   | `webapp.css` | CSS |
   | `backend.py` | Python |
5. In the webapp **Settings → Security** (or the "Datasets" panel), grant
   `Bc_Cage_SP` → **Read/Write**.
6. Enable the Python backend (toggle in the Python tab) and **Start** it,
   then **Preview**.

## Endpoints (backend.py)

| Route | Method | Purpose |
|---|---|---|
| `/schema` | GET | Column names/labels/types + derived flag → grid + form (row_id hidden) |
| `/data` | GET | Current rows of `Bc_Cage_SP` (incl. row_id) |
| `/save` | POST | Per-row `INSERT` (new) + `UPDATE … WHERE row_id` (edited), one COMMIT |
