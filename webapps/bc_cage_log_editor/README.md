# BC Cage Log Editor — Dataiku Standard Webapp

A simple data-entry webapp: shows the cage log as a table, lets the user
add new entries through a form, and saves everything (original rows +
additions) to a new dataset `BC_Cage_Log_updated`.

The form and table are generated **dynamically from the dataset schema**,
so column changes are picked up automatically.

## Prerequisite: clean the raw import

The raw `BC_Cage_Log` import is messy — the Excel has three banner/header
rows on top, so Dataiku named the columns `col_0 … col_13` and pulled the
real headers in as data rows. Before using this app, build a clean version `BC_Cage_Log_clean`:

1. Create an empty **managed** dataset named `BC_Cage_Log_clean`.
2. Run `python_recipes/clean_bc_cage_log.py` in a Dataiku notebook (or as a
   Python recipe: input `BC_Cage_Log`, output `BC_Cage_Log_clean`). It
   renames `col_0 … col_13` to the 14 real headers **by position** and keeps
   only rows whose `RACK ID` is numeric — dropping the two banner rows, the
   embedded header row, and blank rows.

The app reads `BC_Cage_Log_clean` (see `INPUT_DATASET` in `backend.py`).
Dates are kept as text on purpose — the source dates have no year.

## How it works

1. On load the app reads `BC_Cage_Log_updated` if it already has rows
   (so previously added entries show up), otherwise `BC_Cage_Log`.
2. "**+ Add to table**" puts the form row at the top of the table,
   highlighted yellow, as an *unsaved* row.
3. "**Save all**" sends the unsaved rows to the backend, which appends
   them to the current data and writes the full table to
   `BC_Cage_Log_updated` with `write_with_schema`. `BC_Cage_Log` is
   never modified.

## Setup in Dataiku

1. In the Flow: **+ Dataset → Internal → Managed** (any writable
   connection, e.g. filesystem) and name it exactly `BC_Cage_Log_updated`.
   Create it empty — the webapp writes the schema on first save.
2. **Webapps → + New webapp → Code webapp → Standard** (pick the
   "Simple webapp" starter), name it e.g. *BC Cage Log Editor*.
3. Paste each file into its tab:
   | File | Tab |
   |---|---|
   | `webapp.html` | HTML |
   | `webapp.js` | JS |
   | `webapp.css` | CSS |
   | `backend.py` | Python |
4. In the webapp **Settings → Security** (or the "Datasets" panel),
   grant: `BC_Cage_Log` → **Read**, `BC_Cage_Log_updated` → **Read/Write**.
5. Enable the Python backend (toggle in the Python tab) and **Start** the
   backend, then **Preview**.

## Endpoints (backend.py)

| Route | Method | Purpose |
|---|---|---|
| `/schema` | GET | Column names/types → drives table header + form inputs |
| `/data` | GET | Current rows (output dataset if saved before, else input) |
| `/save` | POST | Append new rows, write full table to `BC_Cage_Log_updated` |
