"""Build NetworkX graph from XER data and find paths between key activities."""

from __future__ import annotations
from dataclasses import dataclass

import networkx as nx

from xer_parser import Task, TaskPred


@dataclass
class Connection:
    source_code: str   # task_code of source key activity
    target_code: str   # task_code of target key activity
    source_id: str
    target_id: str
    intermediate_ids: list[str]  # task_ids along the path (excl. source/target)


def build_graph(
    tasks: dict[str, Task],
    preds: dict[str, list[TaskPred]],
) -> nx.DiGraph:
    """Build a directed graph: edges go from predecessor → successor."""
    G = nx.DiGraph()

    for task_id, task in tasks.items():
        G.add_node(task_id, task_code=task.task_code, task_name=task.task_name)

    for task_id, pred_list in preds.items():
        for tp in pred_list:
            G.add_edge(
                tp.pred_task_id,
                task_id,
                pred_type=tp.pred_type,
                lag_hr_cnt=tp.lag_hr_cnt,
            )

    return G


def find_connections(
    G: nx.DiGraph,
    key_task_ids: list[str],
) -> list[Connection]:
    """
    Find direct connections between key activities using transitive reduction.

    A connection A→B is only drawn if no other key activity lies on the
    shortest path between A and B.  This prevents the diagram from showing
    redundant long-range arrows when shorter A→C and C→B arrows already
    capture the same relationship.
    """
    key_set = set(key_task_ids)
    id_to_code = {
        nid: data.get("task_code", nid)
        for nid, data in G.nodes(data=True)
    }

    connections: list[Connection] = []
    seen_pairs: set[tuple[str, str]] = set()

    for i, src_id in enumerate(key_task_ids):
        for tgt_id in key_task_ids[i + 1:]:
            if src_id == tgt_id:
                continue

            # Determine direction: try forward first, then reverse
            forward = src_id in G and tgt_id in G and nx.has_path(G, src_id, tgt_id)
            reverse = (
                not forward
                and src_id in G and tgt_id in G
                and nx.has_path(G, tgt_id, src_id)
            )

            if not forward and not reverse:
                continue

            actual_src, actual_tgt = (src_id, tgt_id) if forward else (tgt_id, src_id)
            pair = (actual_src, actual_tgt)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            path = nx.shortest_path(G, actual_src, actual_tgt)
            intermediate = path[1:-1]

            # Transitive reduction: skip this connection if any key activity
            # appears along the path — it is already covered by shorter arrows.
            if any(node in key_set for node in intermediate):
                continue

            connections.append(Connection(
                source_code=id_to_code.get(actual_src, actual_src),
                target_code=id_to_code.get(actual_tgt, actual_tgt),
                source_id=actual_src,
                target_id=actual_tgt,
                intermediate_ids=intermediate,
            ))

    return connections
