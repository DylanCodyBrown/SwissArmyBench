---
name: swissarmygrid-use
description: How to use SwissArmyGrid once it's set up - the tabbed workspace, the ribbon's Table and Column tools, the steps strip and its Table Transformations tab, SQL in the notebook, column and table profiles, the Key Finder, side-by-side compare of two tables, the Sandbox tab (a dashboard of charts, notes, diagrams, figures and images), and what an agent may see (everything the page shows; exports wait for a click). Use when someone asks how to do something in the grid ("how do I compare two tables", "where did the profile go", "how do I launch Claude in the grid", "what can the agent see"), or wants a tour. For installing it, see the installers in the repository's installer/ folder (install.ps1 on Windows, install.sh elsewhere).
---

# Use SwissArmyGrid

The person's guide, with a screenshot of each feature, is
[swissarmygrid-user-guide.md](swissarmygrid-user-guide.md). Answer from it, and point them at the
section that covers their question.

When you are the agent working on their grids (through the swissarmygrid MCP server), call
the `guide` tool first: it is the agent's side of the same story (the commands, what it sees,
which command to use when), and `agent_context` says which table they have in front of them.

## Things people ask that the guide answers

| They ask | Point them at |
|---|---|
| Where are the settings / the theme / the agent's access? | **Settings**, first in the Application row (the top row of the ribbon, on every tab) |
| Where did the column profile go? | Select the column, then Profile on the ribbon's Column row (a popup) |
| How do I compare two tables? | Right-click a table's tab, Compare with… (or drag one tab onto another); the key picker opens with the Key Finder already run and the key unique on both sides ticked |
| Where did a table I closed go? | The ≡ button beside + in the tab strip: Tables lists the closed ones, each with Open (the same table, not a copy) |
| Where are the header profiles / the zoom? | Profiles: the small button in the grid's top-left corner, above the row numbers. Zoom: the Application row (the whole page, the Sandbox too) |
| How do I undo a step? / Is there a list of every command? | Ctrl+Z (Ctrl+Y redoes), or hover "N steps" under the title and remove any one. Ctrl+Shift+P lists every action of the page |
| How are my tables related? / Draw an ERD | The Diagram tab, right after Sandbox: Import relationships (a .tang or a model as JSON), apply a shared model, or ask the agent to build one |
| How do I read a Power BI dataset? / Bring its relationships in / Run DAX | Connections, Add connection, **Power BI workspace**: the workspace id (no dataset: one connection reaches every dataset in the workspace), and an app registration whose tenant id, client id and client secret are entries of their key vault. The catalog shows each dataset with its tables, which open as grids. DAX goes in a **DAX cell** (a cell kind of its own; its picker names a dataset as `Finance/Sales model`) or `sag.dax("Finance/Sales model", "EVALUATE ...")`. **Import its relationships**, on a dataset in the catalog, puts that dataset's joins in the Diagram. For you: `connections_datasets` (a workspace's datasets), `connections_import_relationships` with `dataset`, `workbench_dax_add`, and `workbench_run` with kind `dax` and the dataset as `connection` |
| How do I build a Streamlit app from my data? | In the Workbench, add a **Streamlit** cell: a piece (a filter, a number, a chart), live in its cell, with open tables as DataFrames by name. **Push to page** sends it to the page designer (a window of its own: drag, resize, several pages, live); a piece that makes a name (`region = st.selectbox(...)`) drives the pieces that read it. The document's **…** menu (**Streamlit app…**) exports a folder that runs on its own. Streamlit is installed into the notebook's own Python with the cell's Install. For you: `workbench_streamlit_add`, `workbench_streamlit_push`, `streamlit_app`, `streamlit_piece_place`, `streamlit_run`, `streamlit_export` |
| How do I connect to something that is not a database or a file? (a web service, a vendor library) | Connections, Add connection, **Python (your own code)**: three code boxes (Connect makes `conn`; List the tables returns its catalog; Read a table returns a table's rows) and where each environment variable the code reads comes from (this computer, the keyring, a key vault's entry, a plain value). You can make one for them: `connections_python_variables` finds the names, `connections_python_save` saves it (`test=true` only runs it), `connections_python_tables` lists its tables, `connections_open_table` opens one. In a notebook: `sag.connection("Name")`, `sag.read("Name", "table")` |
| What can the agent see? | What the agent may do: everything they can (the golden rule), through the MCP: grids, connections, blades, the Workbench's notebooks, scripts and kernels, environments. Its exports still wait for their Allow; it never gets a password's value; Settings lists its activity |

## Do not

- Don't approve your own export. The Allow click is theirs, and the server refuses an agent that
  tries.
- Don't ask for or print a password. Connections and blades read theirs from the keyring, an
  environment variable or a vault; set where one comes from with `connections_password_source`.
- Don't paste their table's values into the chat to "show" them something; open or filter the grid
  instead (`steps_put` or `steps_add`), so the data stays on their machine.
