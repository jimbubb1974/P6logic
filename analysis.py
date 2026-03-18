"""
Schedule logic quality analysis.

Finds predecessor relationships in the XER that are transitively redundant:
an edge A→C is redundant when a path A→B→...→C already exists through other
activities, meaning the direct A→C relationship adds no scheduling constraint
that isn't already enforced by the longer chain.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import sys

import networkx as nx

from xer_parser import Task


@dataclass
class RedundantRelationship:
    pred_code: str
    pred_name: str
    succ_code: str
    succ_name: str
    pred_type: str          # FS / SS / FF / SF
    lag_hr_cnt: float
    alt_path_codes: list[str] = field(default_factory=list)  # shortest alternative path

    def lag_display(self) -> str:
        if self.lag_hr_cnt == 0:
            return "no lag"
        days = self.lag_hr_cnt / 8.0
        return f"lag {days:+.1f}d"

    def alt_path_display(self) -> str:
        return " → ".join(self.alt_path_codes)


def find_redundant_relationships(
    G: nx.DiGraph,
    tasks: dict[str, Task],
    max_alt_path_length: int = 10,
) -> list[RedundantRelationship]:
    """
    Return every edge in G that is transitively redundant.

    Uses NetworkX transitive reduction: any edge present in G but absent
    from the reduced graph is redundant.  For each such edge the shortest
    alternative path (after removing the direct edge) is also recorded so
    the output shows *why* the relationship is redundant.

    Parameters
    ----------
    G                   : full directed schedule graph
    tasks               : task_id -> Task lookup
    max_alt_path_length : skip recording the alt-path if it is longer than
                          this (keeps the output readable for very deep chains)
    """
    if not nx.is_directed_acyclic_graph(G):
        print(
            "WARNING: Schedule graph contains cycles — logic check cannot run.\n"
            "         Fix the out-of-sequence relationships in P6 first.",
            file=sys.stderr,
        )
        return []

    print("  Computing transitive reduction (this may take a moment for large schedules)...")
    G_tr = nx.transitive_reduction(G)

    def code(task_id: str) -> str:
        t = tasks.get(task_id)
        return t.task_code if t else task_id

    def name(task_id: str) -> str:
        t = tasks.get(task_id)
        return t.task_name if t else ""

    results: list[RedundantRelationship] = []

    for pred_id, succ_id, edge_data in G.edges(data=True):
        if G_tr.has_edge(pred_id, succ_id):
            continue  # edge survives reduction → not redundant

        # Find the shortest alternative path to explain the redundancy.
        G_temp = G.copy()
        G_temp.remove_edge(pred_id, succ_id)
        try:
            alt = nx.shortest_path(G_temp, pred_id, succ_id)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            alt = [pred_id, succ_id]

        alt_codes = [code(n) for n in alt]
        if len(alt_codes) > max_alt_path_length:
            # Truncate and note the omission
            alt_codes = alt_codes[:max_alt_path_length] + [f"… ({len(alt_codes)} steps total)"]

        results.append(RedundantRelationship(
            pred_code=code(pred_id),
            pred_name=name(pred_id),
            succ_code=code(succ_id),
            succ_name=name(succ_id),
            pred_type=edge_data.get("pred_type", "FS"),
            lag_hr_cnt=float(edge_data.get("lag_hr_cnt", 0) or 0),
            alt_path_codes=alt_codes,
        ))

    # Sort: successor code first, then predecessor code — groups by successor
    # so a reviewer can see all redundant drivers of the same activity together.
    results.sort(key=lambda r: (r.succ_code, r.pred_code))
    return results


def format_report(results: list[RedundantRelationship], total_relationships: int) -> str:
    """Format the redundancy list as a human-readable report string."""
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append("REDUNDANT LOGIC REPORT")
    lines.append("=" * 70)

    if not results:
        lines.append("No redundant predecessor relationships found.")
        return "\n".join(lines)

    pct = 100.0 * len(results) / total_relationships if total_relationships else 0
    lines.append(
        f"Found {len(results)} redundant relationship(s) "
        f"out of {total_relationships} total ({pct:.1f}%)"
    )
    lines.append(
        "Each entry shows the redundant relationship and the alternative\n"
        "path that already enforces the same constraint.\n"
    )

    current_succ = None
    for i, r in enumerate(results, 1):
        # Print a separator when the successor changes
        if r.succ_code != current_succ:
            current_succ = r.succ_code
            lines.append("-" * 70)
            lines.append(f"Successor:  {r.succ_code}  —  {r.succ_name}")
            lines.append("")

        lines.append(
            f"  {i:>4}.  Redundant predecessor: {r.pred_code}  —  {r.pred_name}"
        )
        lines.append(
            f"         Relationship: {r.pred_type}, {r.lag_display()}"
        )
        lines.append(
            f"         Alternative:  {r.alt_path_display()}"
        )
        lines.append("")

    lines.append("=" * 70)
    lines.append(
        "Recommended action: review each relationship in P6 and consider\n"
        "removing the redundant logic link. Always verify with the scheduler\n"
        "before deleting any relationship."
    )
    lines.append("=" * 70)
    return "\n".join(lines)


def run_logic_check(
    G: nx.DiGraph,
    tasks: dict[str, Task],
    output_file: Optional[str],
) -> None:
    """
    Run the redundancy check, print results to console, and optionally
    write the full report to a text file.
    """
    total_relationships = G.number_of_edges()
    print(f"  Checking {total_relationships} predecessor relationships for redundancy...")

    results = find_redundant_relationships(G, tasks)
    report  = format_report(results, total_relationships)

    print()
    print(report)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as fh:
            fh.write(report)
            fh.write("\n")
        print(f"\nLogic check report saved to: {output_file}")
