"""CLI entry point for the Primavera XER Schedule Logic Visualizer."""

from __future__ import annotations
import argparse
import sys
from datetime import datetime

from dateutil import parser as dateparser

from config import load_config
from xer_parser import parse_xer, Task
from network import build_graph, find_connections
from layout import compute_positions, _parse_date
from visualizer import build_figure, write_html
from analysis import run_logic_check


def _resolve_key_ids(
    tasks: dict[str, Task],
    key_codes: list[str],
) -> list[str]:
    code_to_id = {t.task_code: tid for tid, t in tasks.items()}
    resolved = []
    missing = []
    for code in key_codes:
        if code in code_to_id:
            resolved.append(code_to_id[code])
        else:
            missing.append(code)
    if missing:
        print(f"WARNING: key activities not found in XER: {missing}", file=sys.stderr)
    return resolved


def _find_project_min_date(
    tasks: dict[str, Task],
    key_task_ids: list[str],
    intermediate_ids: list[str],
    date_field: str,
) -> datetime:
    all_ids = list(dict.fromkeys(key_task_ids + intermediate_ids))
    dates = []
    for tid in all_ids:
        task = tasks.get(tid)
        if task is None:
            continue
        raw = getattr(task, date_field, None)
        dt = _parse_date(raw)
        if dt:
            dates.append(dt)
    return min(dates) if dates else datetime(2000, 1, 1)


def main() -> None:
    ap = argparse.ArgumentParser(description="Primavera XER Schedule Logic Visualizer")
    ap.add_argument("--config", required=True, help="Path to JSON config file")
    args = ap.parse_args()

    # 1. Load config
    print(f"Loading config: {args.config}")
    cfg = load_config(args.config)

    # 2. Parse XER
    print(f"Parsing XER: {cfg.xer_file}")
    tasks, preds = parse_xer(cfg.xer_file)
    print(f"  {len(tasks)} tasks, {sum(len(v) for v in preds.values())} predecessors loaded")

    # 3. Resolve key activity codes -> internal IDs
    key_task_ids = _resolve_key_ids(tasks, cfg.key_activities)
    if not key_task_ids:
        print("ERROR: No key activities resolved. Check task_code values in config.", file=sys.stderr)
        sys.exit(1)
    print(f"  {len(key_task_ids)} key activities resolved")

    # 4. Filter by total float (optional)
    if cfg.max_float_days is not None:
        threshold_hrs = cfg.max_float_days * 8.0
        before = len(key_task_ids)
        filtered_codes = []
        kept = []
        for tid in key_task_ids:
            task = tasks.get(tid)
            float_hrs = task.total_float_hr_cnt if task else None
            if float_hrs is not None and float_hrs > threshold_hrs:
                filtered_codes.append(task.task_code)
            else:
                kept.append(tid)
        key_task_ids = kept
        if filtered_codes:
            print(f"  Float filter (>{cfg.max_float_days}d): removed {len(filtered_codes)} node(s): {filtered_codes}")
        print(f"  {len(key_task_ids)} key activities remaining after float filter")

    # 5. Build graph
    print("Building network graph...")
    G = build_graph(tasks, preds)
    print(f"  Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # 5a. Logic quality check (optional — runs on the full schedule graph)
    if cfg.logic_check:
        print("\nRunning logic redundancy check...")
        run_logic_check(G, tasks, cfg.logic_check_output)
        print()

    # 5. Find connections
    print("Finding paths between key activities...")
    connections = find_connections(G, key_task_ids)
    print(f"  {len(connections)} connections found")
    for conn in connections:
        n_inter = len(conn.intermediate_ids)
        print(f"    {conn.source_code} → {conn.target_code}  ({n_inter} intermediate nodes)")

    # 6. Drop key activities that have no connections (optional)
    if cfg.drop_unconnected:
        connected_ids = {conn.source_id for conn in connections} | {conn.target_id for conn in connections}
        dropped_codes = [tasks[tid].task_code for tid in key_task_ids if tid not in connected_ids]
        key_task_ids = [tid for tid in key_task_ids if tid in connected_ids]
        if dropped_codes:
            print(f"  Dropped {len(dropped_codes)} unconnected node(s): {dropped_codes}")

    # 7. Collect intermediate IDs (if needed for layout)
    intermediate_ids: list[str] = []
    if cfg.show_intermediate:
        for conn in connections:
            intermediate_ids.extend(conn.intermediate_ids)
        intermediate_ids = list(dict.fromkeys(intermediate_ids))

    # 8. Compute layout
    print("Computing layout...")
    positions = compute_positions(
        tasks=tasks,
        key_task_ids=key_task_ids,
        intermediate_ids=intermediate_ids,
        date_field=cfg.date_field,
        y_overrides=cfg.y_positions,
    )

    # 9. Find minimum date for axis labels
    min_date = _find_project_min_date(tasks, key_task_ids, intermediate_ids, cfg.date_field)

    # 10. Build and write diagram
    print("Rendering diagram...")
    fig, js_data = build_figure(
        tasks=tasks,
        positions=positions,
        key_task_ids=key_task_ids,
        connections=connections,
        date_field=cfg.date_field,
        show_intermediate=cfg.show_intermediate,
        show_activity_name=cfg.show_activity_name,
        shorthand_names=cfg.shorthand_names,
        use_shorthand_label=cfg.use_shorthand_label,
        min_date=min_date,
    )
    write_html(fig, cfg.output, js_data)


if __name__ == "__main__":
    main()
