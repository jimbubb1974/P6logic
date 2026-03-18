"""Build Plotly interactive HTML diagram from layout and connection data."""

from __future__ import annotations
from datetime import datetime, timedelta
from typing import Optional
import json
import math

import plotly.graph_objects as go
from dateutil import parser as dateparser

from xer_parser import Task
from network import Connection


_KEY_COLOR = "#2563eb"
_KEY_BORDER = "#1e3a8a"
_INTER_COLOR = "#94a3b8"
_INTER_BORDER = "#64748b"
_EDGE_COLOR = "rgba(30, 58, 138, 0.35)"
_EDGE_COLOR_BRIGHT = "rgba(30, 58, 138, 0.9)"
_INTER_EDGE_COLOR = "rgba(148, 163, 184, 0.4)"


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return dateparser.parse(s)
    except Exception:
        return None


def _days_to_date(days: float, min_date: datetime) -> datetime:
    return min_date + timedelta(days=days)


def _arrow_angle_deg(x0: float, y0: float, x1: float, y1: float,
                     x_scale: float, y_scale: float) -> float:
    dx = (x1 - x0) * x_scale
    dy = (y1 - y0) * y_scale
    return math.degrees(math.atan2(dx, dy))


def _build_hover_js(js_data: dict) -> str:
    """
    Return a JavaScript snippet injected before </body>.

    On hover over a key node:
      - Connected edges brighten; unconnected edges fade to near-invisible.
      - Connected nodes stay fully visible; unconnected nodes + their labels fade.
    On unhover: everything is restored.
    """
    edge_map_json        = json.dumps(js_data["edge_map"])
    all_edge_json        = json.dumps(js_data["all_edge_indices"])
    node_neighbors_json  = json.dumps(js_data["node_neighbors"])
    node_codes_json      = json.dumps(js_data["node_codes"])
    node_trace_idx       = js_data["node_trace_idx"]
    below_trace_idx      = js_data["below_label_trace_idx"]   # -1 if absent
    node_label_color     = _KEY_BORDER        # "#1e3a8a"
    below_label_color    = "#64748b"

    return f"""
(function() {{
    var edgeMap       = {edge_map_json};
    var allEdgeIdx    = {all_edge_json};
    var nodeNeighbors = {node_neighbors_json};
    var nodeCodes     = {node_codes_json};
    var nodeTraceIdx  = {node_trace_idx};
    var belowTraceIdx = {below_trace_idx};

    var gd = document.querySelector('.js-plotly-plot');
    if (!gd || typeof gd.on !== 'function') return;

    // Capture default edge opacities.
    var defEdgeOpacity = {{}};
    allEdgeIdx.forEach(function(i) {{
        var t = gd.data[i];
        defEdgeOpacity[i] = (t && t.opacity != null) ? t.opacity : 1.0;
    }});

    gd.on('plotly_hover', function(eventData) {{
        var pt   = eventData.points[0];
        var code = pt.customdata;
        if (!code) return;

        // --- edges ---
        var connEdges    = new Set(edgeMap[code] || []);
        var dimEdgeIdx   = allEdgeIdx.filter(function(i) {{ return !connEdges.has(i); }});
        var brightEdgeIdx= allEdgeIdx.filter(function(i) {{ return  connEdges.has(i); }});
        if (dimEdgeIdx.length)    Plotly.restyle(gd, {{opacity: 0.04}}, dimEdgeIdx);
        if (brightEdgeIdx.length) Plotly.restyle(gd, {{opacity: 1.0}},  brightEdgeIdx);

        // --- nodes + above labels ---
        var connNodes = new Set(nodeNeighbors[code] || []);
        connNodes.add(code);   // always keep the hovered node fully visible

        var markerOpacities = nodeCodes.map(function(c) {{
            return connNodes.has(c) ? 1.0 : 0.06;
        }});
        var labelColors = nodeCodes.map(function(c) {{
            return connNodes.has(c) ? '{node_label_color}' : 'rgba(0,0,0,0.04)';
        }});
        Plotly.restyle(gd,
            {{'marker.opacity': [markerOpacities], 'textfont.color': [labelColors]}},
            [nodeTraceIdx]);

        // --- below labels (if present) ---
        if (belowTraceIdx >= 0) {{
            var belowColors = nodeCodes.map(function(c) {{
                return connNodes.has(c) ? '{below_label_color}' : 'rgba(0,0,0,0.04)';
            }});
            Plotly.restyle(gd, {{'textfont.color': [belowColors]}}, [belowTraceIdx]);
        }}
    }});

    gd.on('plotly_unhover', function() {{
        // Restore edges
        var edgeVals = allEdgeIdx.map(function(i) {{ return defEdgeOpacity[i]; }});
        Plotly.restyle(gd, {{opacity: edgeVals}}, allEdgeIdx);
        // Restore nodes + above labels (single value = all points)
        Plotly.restyle(gd,
            {{'marker.opacity': 1.0, 'textfont.color': '{node_label_color}'}},
            [nodeTraceIdx]);
        // Restore below labels
        if (belowTraceIdx >= 0) {{
            Plotly.restyle(gd, {{'textfont.color': '{below_label_color}'}}, [belowTraceIdx]);
        }}
    }});
}})();
"""


def build_figure(
    tasks: dict[str, Task],
    positions: dict[str, tuple[float, float]],
    key_task_ids: list[str],
    connections: list[Connection],
    date_field: str,
    show_intermediate: bool,
    show_activity_name: bool,
    shorthand_names: dict[str, str],
    use_shorthand_label: bool,
    min_date: datetime,
) -> tuple[go.Figure, dict]:
    """
    Returns (figure, js_data).

    js_data contains everything the hover JavaScript needs:
      edge_map, all_edge_indices, node_trace_idx, node_codes,
      node_neighbors, below_label_trace_idx.
    """
    fig = go.Figure()
    trace_idx = 0

    # JS data
    edge_map: dict[str, list[int]] = {}
    all_edge_indices: list[int] = []
    node_trace_idx: int = -1
    below_label_trace_idx: int = -1

    # node_neighbors: task_code -> [directly connected task_codes] (for node fading)
    node_neighbors: dict[str, list[str]] = {}
    for conn in connections:
        node_neighbors.setdefault(conn.source_code, []).append(conn.target_code)
        node_neighbors.setdefault(conn.target_code, []).append(conn.source_code)

    # ------------------------------------------------------------------ axis ranges
    all_x = [v[0] for v in positions.values()] if positions else [0, 100]
    all_y = [v[1] for v in positions.values()] if positions else [0, 1]
    x_min, x_max = min(all_x), max(all_x)
    y_min, y_max = min(all_y), max(all_y)
    x_span = max(x_max - x_min, 1.0)
    y_span = max(y_max - y_min, 1.0)
    px_per_day  = 1200.0 / x_span
    px_per_lane = 900.0  / y_span

    # ------------------------------------------------------------------ intermediate path edges
    if show_intermediate:
        for conn in connections:
            path_ids = [conn.source_id] + conn.intermediate_ids + [conn.target_id]
            for a, b in zip(path_ids, path_ids[1:]):
                if a not in positions or b not in positions:
                    continue
                x0, y0 = positions[a]
                x1, y1 = positions[b]
                fig.add_trace(go.Scatter(
                    x=[x0, x1, None],
                    y=[y0, y1, None],
                    mode="lines",
                    line=dict(color=_INTER_EDGE_COLOR, width=1, dash="dot"),
                    hoverinfo="skip",
                    showlegend=False,
                ))
                trace_idx += 1   # intermediate edges not in edge_map

    # ------------------------------------------------------------------ key-node edges
    for conn in connections:
        src, tgt = conn.source_id, conn.target_id
        if src not in positions or tgt not in positions:
            continue
        x0, y0 = positions[src]
        x1, y1 = positions[tgt]
        angle = _arrow_angle_deg(x0, y0, x1, y1, px_per_day, px_per_lane)

        # Line segment
        fig.add_trace(go.Scatter(
            x=[x0, x1],
            y=[y0, y1],
            mode="lines",
            line=dict(color=_EDGE_COLOR, width=1.5),
            hoverinfo="skip",
            showlegend=False,
        ))
        for code in (conn.source_code, conn.target_code):
            edge_map.setdefault(code, []).append(trace_idx)
        all_edge_indices.append(trace_idx)
        trace_idx += 1

        # Arrowhead marker at target
        fig.add_trace(go.Scatter(
            x=[x1],
            y=[y1],
            mode="markers",
            marker=dict(
                symbol="arrow",
                size=10,
                angle=angle,
                color=_EDGE_COLOR,
                line=dict(width=0),
            ),
            hoverinfo="skip",
            showlegend=False,
        ))
        for code in (conn.source_code, conn.target_code):
            edge_map.setdefault(code, []).append(trace_idx)
        all_edge_indices.append(trace_idx)
        trace_idx += 1

    # ------------------------------------------------------------------ intermediate nodes
    if show_intermediate:
        inter_ids = list(dict.fromkeys(
            tid
            for conn in connections
            for tid in conn.intermediate_ids
            if tid not in set(key_task_ids)
        ))
        if inter_ids:
            ix, iy, itext, ihover = [], [], [], []
            for tid in inter_ids:
                if tid not in positions:
                    continue
                x, y = positions[tid]
                task = tasks.get(tid)
                if task is None:
                    continue
                ix.append(x)
                iy.append(y)
                itext.append(task.task_code)
                early_start = _parse_date(task.early_start_date)
                tf = task.total_float_hr_cnt
                float_str = f"{tf / 8:.1f}d" if tf is not None else "N/A"
                ihover.append(
                    f"<b>{task.task_code}</b><br>"
                    f"{task.task_name}<br>"
                    f"Early Start: {early_start.strftime('%Y-%m-%d') if early_start else 'N/A'}<br>"
                    f"Total Float: {float_str}"
                )
            fig.add_trace(go.Scatter(
                x=ix, y=iy,
                mode="markers+text",
                marker=dict(size=10, color=_INTER_COLOR,
                            line=dict(color=_INTER_BORDER, width=1), opacity=0.7),
                text=itext,
                textposition="top center",
                textfont=dict(size=9, color=_INTER_BORDER),
                hovertext=ihover,
                hoverinfo="text",
                opacity=0.7,
                name="Intermediate",
                showlegend=True,
            ))
            trace_idx += 1

    # ------------------------------------------------------------------ key nodes (last → on top)
    kx, ky, kcodes, knames, khover = [], [], [], [], []
    above_labels: list[str] = []   # text rendered above each node (bold)
    below_labels: list[str] = []   # text rendered below each node (small grey)

    for tid in key_task_ids:
        if tid not in positions:
            continue
        x, y = positions[tid]
        task = tasks.get(tid)
        if task is None:
            continue

        kx.append(x)
        ky.append(y)
        kcodes.append(task.task_code)
        knames.append(task.task_name)

        shorthand = shorthand_names.get(task.task_code, "")

        if use_shorthand_label and shorthand:
            # Shorthand is the hero label; activity ID shown below in grey
            above_labels.append(f"<b>{shorthand}</b>")
            below_labels.append(task.task_code)
        else:
            # Activity ID is the hero label
            above_labels.append(f"<b>{task.task_code}</b>")
            # Show activity name below only when the flag is set
            below_labels.append(task.task_name if show_activity_name else "")

        early_start = _parse_date(task.early_start_date)
        early_end   = _parse_date(task.early_end_date)
        tf = task.total_float_hr_cnt
        float_str = f"{tf / 8:.1f}d" if tf is not None else "N/A"
        # Hover always shows full detail regardless of label mode
        hover_shorthand = f"Shorthand: {shorthand}<br>" if shorthand else ""
        khover.append(
            f"<b>{task.task_code}</b><br>"
            f"{hover_shorthand}"
            f"{task.task_name}<br>"
            f"Early Start: {early_start.strftime('%Y-%m-%d') if early_start else 'N/A'}<br>"
            f"Early Finish: {early_end.strftime('%Y-%m-%d') if early_end else 'N/A'}<br>"
            f"Total Float: {float_str}<br>"
            f"Type: {task.task_type or 'N/A'}"
        )

    node_trace_idx = trace_idx
    fig.add_trace(go.Scatter(
        x=kx, y=ky,
        mode="markers+text",
        marker=dict(
            size=10,
            color=_KEY_COLOR,
            line=dict(color=_KEY_BORDER, width=1.5),
            symbol="circle",
        ),
        text=above_labels,
        textposition="top center",
        textfont=dict(size=11, color=_KEY_BORDER),
        customdata=kcodes,          # raw task_code used by hover JS
        hoverinfo="none",           # fire hover events but show no popup
        name="Key Activities",
        showlegend=True,
    ))
    trace_idx += 1

    # ------------------------------------------------------------------ below-node labels (optional)
    # Rendered as a separate text-only trace positioned further below the node.
    # We shift the Y coordinates down by a fraction of LANE_HEIGHT so the label
    # clears both the marker and the "bottom center" text anchor gap.
    _BELOW_OFFSET = 0.55   # data units — tune if lanes are tighter/looser
    if any(below_labels) and kx:
        below_label_trace_idx = trace_idx
        fig.add_trace(go.Scatter(
            x=kx,
            y=[y - _BELOW_OFFSET for y in ky],
            mode="text",
            text=below_labels,
            textposition="bottom center",
            textfont=dict(size=9, color="#64748b"),
            hoverinfo="skip",
            showlegend=False,
        ))
        trace_idx += 1

    # ------------------------------------------------------------------ layout
    x_padding = max(x_span * 0.06, 5)
    y_padding = max(y_span * 0.08, 1.0)

    step = max(1, round(x_span / 10))
    tick_vals = list(range(int(x_min), int(x_max) + step + 1, step))
    tick_text = [_days_to_date(v, min_date).strftime("%b %Y") for v in tick_vals]

    fig.update_layout(
        title=None,
        xaxis=dict(
            title="Date",
            tickvals=tick_vals,
            ticktext=tick_text,
            range=[x_min - x_padding, x_max + x_padding],
            showgrid=True,
            gridcolor="#e2e8f0",
            gridwidth=1,
        ),
        yaxis=dict(
            title="",
            showticklabels=False,
            showgrid=False,
            range=[y_min - y_padding, y_max + y_padding],
            zeroline=False,
        ),
        plot_bgcolor="#f8fafc",
        paper_bgcolor="#ffffff",
        hovermode="closest",
        showlegend=False,
        margin=dict(l=40, r=40, t=20, b=60),
        width=1400,
        height=800,
    )

    js_data = {
        "edge_map": edge_map,
        "all_edge_indices": all_edge_indices,
        "node_trace_idx": node_trace_idx,
        "node_codes": kcodes,
        "node_neighbors": node_neighbors,
        "below_label_trace_idx": below_label_trace_idx,
    }
    return fig, js_data


def write_html(fig: go.Figure, output_path: str, js_data: dict) -> None:
    fig.write_html(output_path, include_plotlyjs="cdn")

    with open(output_path, "r", encoding="utf-8") as fh:
        html = fh.read()

    js = _build_hover_js(js_data)
    script_block = f"\n<script type=\"text/javascript\">{js}</script>\n"
    html = html.replace("</body>", script_block + "</body>", 1)

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    print(f"Diagram written to: {output_path}")
