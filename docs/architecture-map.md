# The architecture map

Made by `python tools/architecture_map.py` from the real imports of `src/swissarmybench` and every
extension (read with `ast`; nothing is run). Do not edit it by hand: run the tool again after a
change to what imports what. `tests/test_architecture_map.py` refuses a stale file and an import
cycle.

## The components and what depends on what

Each box is a component: a folder of the base (its layers after REFACTOR.md; `root` is the package's
own modules, `bootstrap` the composition root, `settings` the limits) or a whole extension. An arrow
goes from the component
that imports to the one it imports, with the number of module-to-module imports that make it. A solid
arrow points inward or sideways, as the dependency rule asks; a dotted one points outward (listed
below the picture).

```mermaid
flowchart TB
    subgraph base["swissarmybench (the base)"]
        domain["domain<br/>135 modules"]
        settings["settings<br/>1 module"]
        services["services<br/>95 modules"]
        adapters["adapters<br/>47 modules"]
        cli["cli<br/>42 modules"]
        client["client<br/>24 modules"]
        root["root<br/>4 modules"]
        server["server<br/>94 modules"]
        bootstrap["bootstrap<br/>1 module"]
        mcp["mcp<br/>2 modules"]
    end
    subgraph extensions["extensions"]
        ext_accounting["accounting<br/>9 modules"]
        ext_copilot["copilot<br/>9 modules"]
        ext_git["git<br/>9 modules"]
        ext_powerapps["powerapps<br/>20 modules"]
        ext_powerbi["powerbi<br/>18 modules"]
        ext_streamlit["streamlit<br/>32 modules"]
    end
    adapters -->|55| domain
    adapters -->|1| root
    adapters -->|3| services
    bootstrap -->|43| adapters
    bootstrap -->|1| client
    bootstrap -->|14| domain
    bootstrap -->|2| root
    bootstrap -->|14| server
    bootstrap -->|85| services
    bootstrap -->|1| settings
    cli -->|2| client
    cli -->|1| root
    client -->|8| adapters
    client -->|18| domain
    client -->|2| root
    client -->|1| services
    ext_accounting -->|1| adapters
    ext_accounting -->|2| cli
    ext_accounting -->|3| domain
    ext_accounting -->|2| root
    ext_accounting -->|1| server
    ext_accounting -->|4| services
    ext_copilot -->|1| adapters
    ext_copilot -->|2| cli
    ext_copilot -->|1| domain
    ext_copilot -->|1| root
    ext_copilot -->|1| server
    ext_copilot -->|4| services
    ext_git -->|2| adapters
    ext_git -->|2| cli
    ext_git -->|1| server
    ext_git -->|5| services
    ext_powerapps -->|2| adapters
    ext_powerapps -->|2| cli
    ext_powerapps -->|14| domain
    ext_powerapps -->|2| server
    ext_powerapps -->|5| services
    ext_powerbi -->|1| adapters
    ext_powerbi -->|2| cli
    ext_powerbi -->|21| domain
    ext_powerbi -->|4| server
    ext_powerbi -->|9| services
    ext_streamlit -->|4| adapters
    ext_streamlit -->|2| cli
    ext_streamlit -->|7| domain
    ext_streamlit -->|4| server
    ext_streamlit -->|14| services
    mcp -->|2| cli
    mcp -->|1| domain
    root -->|9| client
    root -->|6| domain
    root -->|3| services
    server -->|9| adapters
    server -.->|1| bootstrap
    server -->|10| client
    server -->|50| domain
    server -->|10| root
    server -->|90| services
    server -->|2| settings
    services -->|378| domain
    services -->|3| settings
    settings -->|1| domain
```

### Arrows that point outward

From a component further in to one further out (settings, domain 0; services 1; adapters, server,
client, cli, root 2; mcp, bootstrap 3; an extension 4). `tests/test_architecture.py` is what enforces the layers;
this list is everything the picture draws dotted, including what that test allows on purpose (the
plain client borrowing a rule, the server starting the composition root).

- **server → bootstrap** (1):
  - `swissarmybench.server.app` imports `swissarmybench.bootstrap`

## The couplings (Robert Martin's component measures)

- **Ca** (afferent): modules outside the component that depend on it. **Ce** (efferent): modules
  outside that it depends on. Only this repository's code is counted, never a library.
- **I** = Ce / (Ca + Ce): 0 is stable (much depends on it, it depends on little), 1 is free to change.
- **A**: the share of its classes that are a `Protocol`, an abstract base class or have an abstract
  method. **D** = |A + I - 1|: the distance from the line where stable things are abstract and
  changeable things are concrete; 0 is on it.

Read with care: the domain here is functions and frozen records far more than classes, so its A is
low by design and its D says little; the measure bites for the components that hold ports.

| Component | What it is | Modules | Ca | Ce | I | Classes | Abstract | A | D |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| domain | the model and its rules | 135 | 175 | 0 | 0.00 | 359 | 1 | 0.00 | 1.00 |
| settings | every limit, one frozen record | 1 | 6 | 1 | 0.14 | 2 | 0 | 0.00 | 0.86 |
| services | the use cases | 95 | 98 | 120 | 0.55 | 343 | 183 | 0.53 | 0.08 |
| adapters | the driven edge: DuckDB, files, the keyring | 47 | 22 | 40 | 0.65 | 111 | 2 | 0.02 | 0.34 |
| cli | the agent's commands | 42 | 7 | 3 | 0.30 | 5 | 0 | 0.00 | 0.70 |
| client | the plain client and the kernel's helpers | 24 | 7 | 21 | 0.75 | 26 | 0 | 0.00 | 0.25 |
| root | the package's own modules: its public face, stats, sab_excel, extensions | 4 | 16 | 18 | 0.53 | 4 | 0 | 0.00 | 0.47 |
| server | the HTTP door and what starts a process | 94 | 12 | 136 | 0.92 | 43 | 2 | 0.05 | 0.03 |
| bootstrap | the composition root | 1 | 1 | 160 | 0.99 | 2 | 0 | 0.00 | 0.01 |
| mcp | the MCP server | 2 | 0 | 3 | 1.00 | 1 | 0 | 0.00 | 0.00 |
| accounting | an extension | 9 | 0 | 11 | 1.00 | 5 | 1 | 0.20 | 0.20 |
| copilot | an extension | 9 | 0 | 10 | 1.00 | 16 | 5 | 0.31 | 0.31 |
| git | an extension | 9 | 0 | 8 | 1.00 | 17 | 4 | 0.24 | 0.24 |
| powerapps | an extension | 20 | 0 | 22 | 1.00 | 39 | 15 | 0.38 | 0.38 |
| powerbi | an extension | 18 | 0 | 24 | 1.00 | 50 | 9 | 0.18 | 0.18 |
| streamlit | an extension | 32 | 0 | 17 | 1.00 | 58 | 3 | 0.05 | 0.05 |

### The modules most depended on

| Module | Modules that import it |
|---|---:|
| `swissarmybench.services.workspace` | 95 |
| `swissarmybench.server.http` | 77 |
| `swissarmybench.services.ports` | 59 |
| `swissarmybench.domain.datasets` | 53 |
| `swissarmybench.cli.api` | 47 |
| `swissarmybench.domain.blades` | 45 |
| `swissarmybench.cli.command_kit` | 38 |
| `swissarmybench.adapters.atomic_files` | 34 |
| `swissarmybench.domain.steps` | 31 |
| `swissarmybench.domain.grids` | 28 |
| `swissarmybench.domain.connections` | 26 |
| `swissarmybench.domain.table_cells` | 25 |
| `swissarmybench.domain.notebooks` | 24 |
| `swissarmybench.domain.packages` | 18 |
| `swissarmybench.domain.codegen` | 17 |

## Import cycles between modules

### While loading

Modules that import each other at their top, so one meets the other half made. None is allowed.

None.

### Only through an import inside a function

Rings that close through an import made when a function runs (or for type checking only): nothing
breaks while loading, but the modules know each other. Each group is listed whole.

- Group 1 (13 modules):
  - `swissarmybench`
  - `swissarmybench.client.analyze_client`
  - `swissarmybench.client.blades_client`
  - `swissarmybench.client.completion`
  - `swissarmybench.client.kernel_connections`
  - `swissarmybench.client.kernel_variables`
  - `swissarmybench.client.sql_cell`
  - `swissarmybench.client.standalone`
  - `swissarmybench.client.table_cells`
  - `swissarmybench.client.visualizations_client`
  - `swissarmybench.client.watcher`
  - `swissarmybench.client.write_sql`
  - `swissarmybench.client.writes`
- Group 2 (2 modules):
  - `swissarmybench.domain.blade_suggestions`
  - `swissarmybench.domain.blades`
- Group 3 (2 modules):
  - `swissarmybench.server.desktop`
  - `swissarmybench.server.desktop_shell`
