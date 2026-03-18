"""Compute node positions: X=time (days from project start), Y=evenly distributed per X-cluster."""

from __future__ import annotations
from collections import defaultdict
from datetime import datetime
from typing import Optional

from dateutil import parser as dateparser

from xer_parser import Task

LANE_HEIGHT = 2.0   # vertical spacing unit between lanes


def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        return dateparser.parse(date_str)
    except Exception:
        return None


def _gather_dates(
    tasks: dict[str, Task],
    ids: list[str],
    date_field: str,
) -> dict[str, datetime]:
    dates: dict[str, datetime] = {}
    for tid in ids:
        task = tasks.get(tid)
        if task is None:
            continue
        raw = getattr(task, date_field, None)
        dt = _parse_date(raw)
        if dt:
            dates[tid] = dt
    return dates


def _build_clusters(
    ids_sorted_by_x: list[str],
    x_values: dict[str, float],
    cluster_resolution: float,
) -> list[list[str]]:
    """
    Group nodes into clusters where all members fall within cluster_resolution
    days of the first node in the cluster.
    """
    clusters: list[list[str]] = []
    for tid in ids_sorted_by_x:
        x = x_values.get(tid, 0.0)
        if clusters and x - x_values.get(clusters[-1][0], 0.0) <= cluster_resolution:
            clusters[-1].append(tid)
        else:
            clusters.append([tid])
    return clusters


def compute_positions(
    tasks: dict[str, Task],
    key_task_ids: list[str],
    intermediate_ids: list[str],
    date_field: str,
    y_overrides: dict[str, float],
) -> dict[str, tuple[float, float]]:
    """
    Returns a dict: task_id -> (x, y) position.

    X = days from the earliest date in the set.
    Y = nodes within the same X-cluster are distributed evenly across the full
        Y range so that every cluster, regardless of size, uses the same vertical
        real estate.  The cluster with the most nodes sets the total Y height.
    Optional y_overrides keyed by task_code override the auto Y.
    """
    all_ids = list(dict.fromkeys(key_task_ids + intermediate_ids))
    dates = _gather_dates(tasks, all_ids, date_field)

    if not dates:
        return {tid: (float(i), 0.0) for i, tid in enumerate(all_ids)}

    min_date = min(dates.values())
    max_date = max(dates.values())
    total_days = max((max_date - min_date).total_seconds() / 86400.0, 1.0)

    def days_from_start(tid: str) -> float:
        if tid in dates:
            return (dates[tid] - min_date).total_seconds() / 86400.0
        return 0.0

    # cluster_resolution: nodes within this many days share an X-cluster.
    # ~3 % of span, minimum 7 days.
    cluster_resolution = max(7.0, total_days * 0.03)

    # ------------------------------------------------------------------ key nodes
    override_set = {
        tasks[tid].task_code if tid in tasks else tid
        for tid in key_task_ids
        if (tasks[tid].task_code if tid in tasks else tid) in y_overrides
    }
    auto_ids = [tid for tid in key_task_ids if (tasks[tid].task_code if tid in tasks else tid) not in y_overrides]
    auto_sorted = sorted(auto_ids, key=days_from_start)
    x_vals = {tid: days_from_start(tid) for tid in auto_ids}

    clusters = _build_clusters(auto_sorted, x_vals, cluster_resolution)

    # The largest cluster sets the total Y range all clusters will span.
    max_cluster_size = max((len(c) for c in clusters), default=1)
    total_y = (max_cluster_size - 1) * LANE_HEIGHT

    positions: dict[str, tuple[float, float]] = {}

    for cluster in clusters:
        n = len(cluster)
        # Sort within cluster by task_code for a consistent, reproducible order.
        cluster_sorted = sorted(
            cluster,
            key=lambda t: tasks[t].task_code if t in tasks else t,
        )
        for i, tid in enumerate(cluster_sorted):
            x = days_from_start(tid)

            if n == 1:
                # Single nodes sit in the vertical middle so connections to
                # multi-node clusters don't need to travel far vertically.
                y = total_y / 2.0
            else:
                # Evenly distribute 0 → total_y
                y = i * total_y / (n - 1)

            # Small X nudge within a cluster so labels don't pile on top of
            # each other at exactly the same horizontal position.
            x = x + i * cluster_resolution * 0.12

            positions[tid] = (x, y)

    # Apply manual Y overrides
    for tid in key_task_ids:
        if tid in positions:
            continue
        task = tasks.get(tid)
        code = task.task_code if task else tid
        if code in y_overrides:
            positions[tid] = (days_from_start(tid), float(y_overrides[code]))

    # ------------------------------------------------------------------ intermediate nodes
    if intermediate_ids:
        inter_auto = [
            tid for tid in intermediate_ids
            if tid not in positions
            and (tasks[tid].task_code if tid in tasks else tid) not in y_overrides
        ]
        inter_sorted = sorted(inter_auto, key=days_from_start)
        inter_x = {tid: days_from_start(tid) for tid in inter_auto}
        inter_clusters = _build_clusters(inter_sorted, inter_x, cluster_resolution)

        inter_max_size = max((len(c) for c in inter_clusters), default=1)
        inter_total_y = (inter_max_size - 1) * LANE_HEIGHT

        for cluster in inter_clusters:
            n = len(cluster)
            cluster_sorted = sorted(
                cluster,
                key=lambda t: tasks[t].task_code if t in tasks else t,
            )
            for i, tid in enumerate(cluster_sorted):
                x = days_from_start(tid)
                if n == 1:
                    y = -(inter_total_y / 2.0) - LANE_HEIGHT
                else:
                    y = -(i * inter_total_y / (n - 1)) - LANE_HEIGHT
                x = x + i * cluster_resolution * 0.12
                positions[tid] = (x, y)

        # Apply overrides to intermediate nodes
        for tid in intermediate_ids:
            if tid in positions:
                continue
            task = tasks.get(tid)
            code = task.task_code if task else tid
            if code in y_overrides:
                positions[tid] = (days_from_start(tid), float(y_overrides[code]))

    return positions
