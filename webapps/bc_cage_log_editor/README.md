# BC Cage Log Editor — Dataiku Standard Webapp

A simple data-entry webapp: shows the `BC_Cage_Log` dataset as a table,
lets the user add new entries through a form, and saves everything
(original rows + additions) to a new dataset `BC_Cage_Log_updated`.

The form and table are generated **dynamically from the dataset schema**,
so column changes in `BC_Cage_Log` are picked up automatically.

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
