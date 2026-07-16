# BC Cage Log Editor — Dataiku Standard Webapp

A simple data-entry webapp: shows the cage log as a table, lets the user
add new entries through a form, and saves everything (original rows +
additions) to a new dataset `bc_cage_log_updated`.

The form and table are generated **dynamically from the dataset schema**,
so column changes are picked up automatically.

## Prerequisite: the prepared dataset

The app reads **`bc_cage_log_prepared`** — the cleaned log produced from the
messy `BC_Cage_Log` Excel import. Build it first with
`python_recipes/clean_bc_cage_log.py` (a Python recipe: input `BC_Cage_Log`,
output `bc_cage_log_prepared`). That recipe:

- keeps the full Excel header names (`RACK ID`, `Date (START HERE)`,
  `Release/Repair Removal Date < 10 days`, … `Date Removed`);
- drops only completely-empty rows (keeps real records even when `RACK ID`
  is blank);
- derives a **`Status`** column: `Open` while `Date Removed` is blank (item
  still in the cage), `Closed` once it has a date.

Dates are kept as text on purpose — the source dates have no year.

## Status is automatic

`Status` is **derived, never typed**. The add-entry form hides it; a new
entry is `Open` until someone fills in `Date Removed`, at which point the
backend recomputes it to `Closed` on save. The table shows a coloured
Open/Closed badge and a dropdown to filter by status.

## How it works

1. On load the app reads `bc_cage_log_updated` if it already has rows
   (so previously added entries show up), otherwise `bc_cage_log_prepared`.
2. "**+ Add to table**" puts the form row at the top of the table,
   highlighted yellow, as an *unsaved* row.
3. "**Save all**" sends the unsaved rows to the backend, which appends them
   to the current data, recomputes `Status`, and writes the full table to
   `bc_cage_log_updated` with `write_with_schema`. The input dataset is
   never modified.

## Setup in Dataiku

1. **Webapps → + New webapp → Code webapp → Standard** (pick the
   "Simple webapp" starter), name it e.g. *BC Cage Log Editor*.
2. Paste each file into its tab:
   | File | Tab |
   |---|---|
   | `webapp.html` | HTML |
   | `webapp.js` | JS |
   | `webapp.css` | CSS |
   | `backend.py` | Python |
3. In the webapp **Settings → Security** (or the "Datasets" panel), grant:
   `bc_cage_log_prepared` → **Read**, `bc_cage_log_updated` → **Read/Write**.
   The output dataset is auto-created on first save if it doesn't exist
   (reusing an existing dataset's connection); or create an empty managed
   `bc_cage_log_updated` yourself.
4. Enable the Python backend (toggle in the Python tab) and **Start** it,
   then **Preview**.

## Endpoints (backend.py)

| Route | Method | Purpose |
|---|---|---|
| `/schema` | GET | Column names/types + derived flag → table header + form inputs |
| `/data` | GET | Current rows (output dataset if saved before, else input) |
| `/save` | POST | Append new rows, recompute Status, write to `bc_cage_log_updated` |
