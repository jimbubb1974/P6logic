"""Load and validate JSON configuration."""

from __future__ import annotations
import json
import os
import csv
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    xer_file: str
    key_activities: list[str]
    date_field: str = "early_start_date"
    show_intermediate: bool = False
    drop_unconnected: bool = True
    max_float_days: Optional[float] = None   # None = no float filtering
    show_activity_name: bool = False
    shorthand_names: dict[str, str] = field(default_factory=dict)  # code -> shorthand
    use_shorthand_label: bool = False
    logic_check: bool = False
    logic_check_output: Optional[str] = "logic_check.txt"  # None = console only
    output: str = "diagram.html"
    y_positions: dict[str, float] = field(default_factory=dict)


# Header values in the activities file that should be skipped
_HEADER_LABELS = {
    "activity id", "activity_id", "task_code", "id", "code", "activity",
    "activity code",
}


def _load_activities_from_file(path: str) -> tuple[list[str], dict[str, str]]:
    """
    Read activity codes from column 1, optional shorthand names from column 2.

    Returns:
        codes       — list of activity ID strings
        shorthands  — dict mapping activity_code -> shorthand name (may be empty)
    """
    ext = os.path.splitext(path)[1].lower()
    rows: list[tuple[str, str]] = []   # (code, shorthand)

    if ext in (".xlsx", ".xlsm", ".xls"):
        try:
            import openpyxl
        except ImportError:
            raise ImportError(
                "openpyxl is required to read Excel files.\n"
                "  pip install openpyxl"
            )
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        for row in ws.iter_rows(min_col=1, max_col=2, values_only=True):
            code = str(row[0]).strip() if row[0] is not None else ""
            shorthand = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
            rows.append((code, shorthand))
        wb.close()

    elif ext == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            for r in reader:
                code = r[0].strip() if r else ""
                shorthand = r[1].strip() if len(r) > 1 else ""
                rows.append((code, shorthand))

    else:
        raise ValueError(f"Unsupported file type '{ext}'. Use .csv, .xlsx, or .xls")

    # Drop header row if first cell looks like a column label
    if rows and rows[0][0].lower() in _HEADER_LABELS:
        rows = rows[1:]

    codes: list[str] = []
    shorthands: dict[str, str] = {}
    for code, shorthand in rows:
        if not code:
            continue
        codes.append(code)
        if shorthand:
            shorthands[code] = shorthand

    return codes, shorthands


def load_config(path: str) -> Config:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path) as fh:
        data = json.load(fh)

    xer_file = data.get("xer_file")
    if not xer_file:
        raise ValueError("Config must include 'xer_file'")

    # key_activities_file takes precedence over inline key_activities list.
    # The file can supply shorthand names in its second column.
    shorthand_names: dict[str, str] = {}
    activities_file = data.get("key_activities_file")
    if activities_file:
        if not os.path.exists(activities_file):
            raise FileNotFoundError(f"key_activities_file not found: {activities_file}")
        key_activities, shorthand_names = _load_activities_from_file(activities_file)
        if not key_activities:
            raise ValueError(f"No activity codes found in: {activities_file}")
    else:
        key_activities = data.get("key_activities")
        if not key_activities or not isinstance(key_activities, list):
            raise ValueError(
                "Config must include either 'key_activities_file' (path to CSV/Excel) "
                "or 'key_activities' (inline list)"
            )
        key_activities = [str(k) for k in key_activities]

    # Shorthand names can also be supplied (or overridden) in the JSON directly.
    # JSON values win over file-column values for the same code.
    json_shorthands = data.get("shorthand_names", {})
    shorthand_names.update({str(k): str(v) for k, v in json_shorthands.items()})

    raw_float = data.get("max_float_days", None)
    max_float_days = float(raw_float) if raw_float is not None else None

    return Config(
        xer_file=xer_file,
        key_activities=key_activities,
        date_field=data.get("date_field", "early_start_date"),
        show_intermediate=bool(data.get("show_intermediate", False)),
        drop_unconnected=bool(data.get("drop_unconnected", True)),
        max_float_days=max_float_days,
        show_activity_name=bool(data.get("show_activity_name", False)),
        shorthand_names=shorthand_names,
        use_shorthand_label=bool(data.get("use_shorthand_label", False)),
        logic_check=bool(data.get("logic_check", False)),
        logic_check_output=data.get("logic_check_output", "logic_check.txt"),
        output=data.get("output", "diagram.html"),
        y_positions=data.get("y_positions", {}),
    )
