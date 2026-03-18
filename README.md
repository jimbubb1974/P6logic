# P6logic — Primavera XER Schedule Logic Visualizer & Analyzer

Reads a Primavera P6 schedule in XER format and provides two capabilities:

1. **Visualizer** — traces the logic network between a user-defined set of key activities/milestones and produces a standalone interactive HTML diagram.
2. **Logic Quality Check** — analyzes the full schedule for transitively redundant predecessor relationships and reports them to the console and/or a log file for the scheduler to investigate.

The X-axis of the diagram is proportional to scheduled dates. The Y-axis is auto-arranged so nodes spread evenly across the available vertical space. Hovering over any node highlights its direct connections and fades everything else.

---

## Requirements

```
pip install networkx plotly python-dateutil openpyxl
```

| Package | Purpose |
|---|---|
| `networkx` | Graph construction, path-finding, and transitive reduction |
| `plotly` | Interactive HTML diagram |
| `python-dateutil` | Parsing P6 date strings |
| `openpyxl` | Reading `.xlsx` key-activity files |

---

## Quick Start

1. Copy `config_example.json` and edit it for your project.
2. Create a key-activities file (Excel or CSV) listing the activity IDs you care about.
3. Run:

```
python main.py --config "My Config.json"
```

4. Open the output HTML file in any browser.

> **Note:** If your config filename contains spaces, wrap it in quotes as shown above.

---

## File Structure

```
P6logic/
├── main.py              # CLI entry point
├── xer_parser.py        # XER file → Python data structures
├── network.py           # NetworkX graph + path-finding (transitive reduction)
├── layout.py            # Node position calculation
├── visualizer.py        # Plotly figure + interactive hover JS
├── analysis.py          # Logic quality / redundancy check
├── config.py            # Config loader and validator
└── config_example.json  # Annotated example config
```

---

## Config File Reference

All options live in a single JSON file passed via `--config`.

```json
{
  "xer_file": "project.xer",

  "key_activities_file": "KeyActivities.xlsx",

  "key_activities": ["A1000", "A1050", "M0010"],

  "date_field": "early_start_date",
  "show_intermediate": false,
  "drop_unconnected": true,
  "max_float_days": null,
  "show_activity_name": false,
  "use_shorthand_label": false,
  "logic_check": false,
  "logic_check_output": "logic_check.txt",
  "output": "diagram.html",

  "y_positions": {
    "A1000": 0,
    "A1050": 3.0
  },

  "shorthand_names": {
    "A1000": "Civil Start",
    "A1050": "I&C Complete"
  }
}
```

### Field Descriptions

#### `xer_file` *(required)*
Path to the Primavera P6 XER export file.

---

#### `key_activities_file`
Path to a CSV or Excel (`.xlsx`/`.xls`) file listing the activity IDs to include in the diagram. The first column is the Activity ID; the optional second column is a shorthand name (see `use_shorthand_label`).

**Example spreadsheet:**

| Activity ID | Shorthand |
|---|---|
| TRP-0001-MS | I&C Systems |
| TRP-0007-MS | Electrical Duct Bank |
| TRP-0034-MS | Mechanical Complete |

- A header row is detected and skipped automatically if the first cell matches common labels (`Activity ID`, `task_code`, `ID`, etc.).
- If both `key_activities_file` and `key_activities` are provided, the file takes precedence.

---

#### `key_activities`
Inline list of Activity ID strings. Used when you don't have a separate file.

```json
"key_activities": ["A1000", "A1050", "M0010"]
```

---

#### `date_field`
Which P6 date field to use for the X-axis position of each node.

| Value | Meaning |
|---|---|
| `"early_start_date"` | Early Start *(default)* |
| `"early_end_date"` | Early Finish |
| `"late_start_date"` | Late Start |
| `"late_end_date"` | Late Finish |

---

#### `show_intermediate`
`true` / `false` *(default `false`)*

When `true`, the activities that lie along the logic path *between* two key nodes are drawn as smaller, faded nodes with dotted connecting lines.

---

#### `drop_unconnected`
`true` / `false` *(default `true`)*

When `true`, any key activity that has no network path to any other key activity is removed from the diagram before rendering. Useful for cleaning up the canvas when your activity list contains milestones that belong to an unrelated sub-network.

The console prints a list of which nodes were dropped.

---

#### `max_float_days`
Number or `null` *(default `null` = no filtering)*

Removes key activities whose Total Float exceeds this threshold (in working days, converted from P6's hours using an 8-hour day). Applied before connection-finding, so filtered nodes do not influence which paths are drawn.

Use this to focus the diagram on the critical or near-critical path:

| Value | Effect |
|---|---|
| `null` | Show all activities regardless of float |
| `0` | Critical path only (zero float) |
| `10` | Activities with ≤ 10 days of float |
| `20` | Activities with ≤ 20 days of float |
| `40` | Activities with ≤ 40 days of float |

---

#### `show_activity_name`
`true` / `false` *(default `false`)*

When `true` and `use_shorthand_label` is `false`, the full P6 activity name is displayed in small grey text below each node.

---

#### `use_shorthand_label`
`true` / `false` *(default `false`)*

When `true`, the shorthand name (from the spreadsheet's second column or from `shorthand_names` in the config) becomes the primary bold label above each node. The Activity ID is displayed as smaller grey text below the node.

When `false`, the Activity ID is the primary label.

---

#### `shorthand_names`
Optional JSON object mapping Activity ID → shorthand name. These override (or supplement) any shorthand names read from the spreadsheet's second column. Useful for adding or correcting a handful of names without editing the spreadsheet.

```json
"shorthand_names": {
  "TRP-0001-MS": "I&C Systems",
  "TRP-0034-MS": "Mechanical Complete"
}
```

---

#### `logic_check`
`true` / `false` *(default `false`)*

When `true`, runs a full redundant-logic analysis on the entire schedule (all activities, not just key activities) before producing the diagram. Results are printed to the console and optionally saved to a file.

See [Logic Quality Check](#logic-quality-check) below for details.

---

#### `logic_check_output`
Filename for the logic check report. Defaults to `"logic_check.txt"`. Set to `null` to print to the console only without writing a file.

---

#### `output`
Output filename for the HTML diagram. Defaults to `"diagram.html"`.

---

#### `y_positions`
Optional manual Y-coordinate overrides keyed by Activity ID. Useful when the auto-layout places a specific node in an inconvenient position.

```json
"y_positions": {
  "A1000": 0,
  "A1050": 6.0
}
```

Y values are in the same data units as the auto-layout (multiples of ~2.0 per lane). Leave this empty `{}` to use fully automatic placement.

---

## The Key Activities File

The simplest format is a single-column spreadsheet with no header:

```
TRP-0001-MS
TRP-0007-MS
TRP-0034-MS
```

To use shorthand labels, add a second column:

```
TRP-0001-MS    I&C Systems
TRP-0007-MS    Electrical Duct Bank
TRP-0034-MS    Mechanical Complete
```

Both CSV (`.csv`) and Excel (`.xlsx`, `.xlsm`, `.xls`) are accepted.

---

## How the Diagram Works

### Layout
- **X-axis** — proportional to the chosen date field. Tick labels show month/year.
- **Y-axis** — automatic. Nodes are grouped into time clusters (dates within ~3% of the total project span). Within each cluster, nodes are distributed evenly across the full vertical range so no cluster wastes vertical real estate.

### Logic paths
The tool builds a full directed graph of all predecessor relationships from the XER file, then finds shortest paths between all pairs of key activities. A **transitive reduction** is applied at the key-activity level: if the path from A→C passes through another key activity B, only the arrows A→B and B→C are drawn (not A→C directly). This prevents redundant long-range arrows from cluttering the diagram.

### Interaction
- **Hover over a node** — that node's direct connections are highlighted. All unconnected nodes, their labels, and their edges fade to near-invisible. Move off to restore.
- **Zoom / pan** — standard Plotly controls: scroll to zoom, drag to pan, double-click to reset view.
- **Legend** — click legend items to toggle the visibility of node groups.

---

## Logic Quality Check

Enable with `"logic_check": true` in the config. This runs on the **full schedule** — every activity and every predecessor relationship in the XER, not just your key activities list.

### What it detects

A predecessor relationship **A → C** is flagged as redundant when a path of length ≥ 2 already connects the same two activities through other activities (e.g. **A → B → C**). The direct A→C link adds no scheduling constraint that isn't already enforced by the longer chain, and is therefore a candidate for removal.

This is sometimes called **over-logic** or **redundant logic** in scheduling practice. Common causes:
- Copy-paste errors when building the schedule
- Logic that made sense in an earlier draft but was superseded by additional detail
- Automatically generated links from scheduling templates

### Reading the output

```
======================================================================
REDUNDANT LOGIC REPORT
======================================================================
Found 23 redundant relationship(s) out of 847 total (2.7%)

----------------------------------------------------------------------
Successor:  TRP-0034-MS  —  TRP-034 Mechanical Complete

     1.  Redundant predecessor: TRP-0001-MS  —  TRP-001 Start Milestone
         Relationship: FS, no lag
         Alternative:  TRP-0001-MS → TRP-0007-MS → TRP-0019-MS → TRP-0034-MS

     2.  Redundant predecessor: TRP-0007-MS  —  TRP-007 Civil Foundations
         Relationship: FS, no lag
         Alternative:  TRP-0007-MS → TRP-0019-MS → TRP-0034-MS
...
```

Results are grouped by successor activity so all redundant drivers of the same activity appear together. The **Alternative** path shows the chain that already enforces the constraint, giving the scheduler enough context to make an informed decision.

### Important caveats

- **Do not delete relationships without review.** Some apparently redundant links may be intentional (e.g. contractual constraints, interface milestones, or soft logic that shouldn't be transitively inferred).
- The check requires a valid DAG. If P6 reports out-of-sequence warnings or the schedule has actual loops, the check will print a warning and skip.
- Large schedules (5 000+ activities) may take 30–60 seconds for the transitive reduction calculation.

---

## Workflow Tips

1. **Start broad** — include all milestones you might care about. Use `drop_unconnected: true` to auto-clean the list.
2. **Tune float** — set `max_float_days` progressively (e.g. try `40`, then `20`, then `10`) to focus on the driving path.
3. **Add shorthands** — once the diagram is readable, populate the second column of your key activities file with meaningful shorthand names and set `use_shorthand_label: true`.
4. **Fine-tune layout** — use `y_positions` to manually pin any node that the auto-layout places awkwardly.
5. **Explore** — the hover highlighting is the primary navigation tool in the final diagram. Clicking through each key node reveals the logical chain quickly.
6. **Clean the logic** — run `logic_check: true` periodically, especially after major schedule updates, to catch redundant relationships before they accumulate.
