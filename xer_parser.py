"""Parse Primavera XER files into Python data structures."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import re


@dataclass
class Task:
    task_id: str
    task_code: str
    task_name: str
    early_start_date: Optional[str] = None
    early_end_date: Optional[str] = None
    late_start_date: Optional[str] = None
    late_end_date: Optional[str] = None
    total_float_hr_cnt: Optional[float] = None
    task_type: Optional[str] = None


@dataclass
class TaskPred:
    task_id: str
    pred_task_id: str
    pred_type: str = "FS"
    lag_hr_cnt: float = 0.0


def _parse_rows(lines: list[str], fields: list[str]) -> list[dict]:
    rows = []
    for line in lines:
        if not line.startswith("%R\t"):
            continue
        values = line[3:].rstrip("\n").split("\t")
        row = {}
        for i, f in enumerate(fields):
            row[f] = values[i] if i < len(values) else ""
        rows.append(row)
    return rows


def parse_xer(path: str) -> tuple[dict[str, Task], dict[str, list[TaskPred]]]:
    """
    Parse an XER file.

    Returns:
        tasks: dict keyed by task_id -> Task
        preds: dict keyed by task_id (successor) -> list[TaskPred]
    """
    with open(path, encoding="latin-1") as fh:
        content = fh.read()

    # Split into table blocks: each block starts with %T
    blocks = re.split(r"(?=^%T\t)", content, flags=re.MULTILINE)

    table_data: dict[str, tuple[list[str], list[str]]] = {}  # table_name -> (fields, raw_lines)

    for block in blocks:
        lines = block.splitlines(keepends=False)
        if not lines:
            continue
        # Find %T line
        t_line = next((l for l in lines if l.startswith("%T\t")), None)
        if t_line is None:
            continue
        table_name = t_line[3:].strip()

        # Find %F line
        f_line = next((l for l in lines if l.startswith("%F\t")), None)
        if f_line is None:
            continue
        fields = f_line[3:].strip().split("\t")

        table_data[table_name] = (fields, lines)

    tasks: dict[str, Task] = {}
    preds: dict[str, list[TaskPred]] = {}

    # Parse TASK table
    if "TASK" in table_data:
        fields, lines = table_data["TASK"]
        for row in _parse_rows(lines, fields):
            task_id = row.get("task_id", "")
            if not task_id:
                continue

            def _float(val: str) -> Optional[float]:
                try:
                    return float(val)
                except (ValueError, TypeError):
                    return None

            tasks[task_id] = Task(
                task_id=task_id,
                task_code=row.get("task_code", ""),
                task_name=row.get("task_name", ""),
                early_start_date=row.get("early_start_date") or None,
                early_end_date=row.get("early_end_date") or None,
                late_start_date=row.get("late_start_date") or None,
                late_end_date=row.get("late_end_date") or None,
                total_float_hr_cnt=_float(row.get("total_float_hr_cnt", "")),
                task_type=row.get("task_type") or None,
            )

    # Parse TASKPRED table
    if "TASKPRED" in table_data:
        fields, lines = table_data["TASKPRED"]
        for row in _parse_rows(lines, fields):
            task_id = row.get("task_id", "")
            pred_task_id = row.get("pred_task_id", "")
            if not task_id or not pred_task_id:
                continue

            try:
                lag = float(row.get("lag_hr_cnt", 0) or 0)
            except ValueError:
                lag = 0.0

            tp = TaskPred(
                task_id=task_id,
                pred_task_id=pred_task_id,
                pred_type=row.get("pred_type", "PR_FS") or "PR_FS",
                lag_hr_cnt=lag,
            )
            preds.setdefault(task_id, []).append(tp)

    return tasks, preds
