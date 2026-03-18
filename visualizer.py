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
_INTER_EDGE_COLOR = "rgba(148, 163, 184, 0.4)"
_SUCC_EDGE_COLOR = "rgba(37, 99, 235, 0.9)"    # blue  — successor arrows on hover
_PRED_EDGE_COLOR = "rgba(147, 51, 234, 0.9)"    # purple — predecessor arrows on hover


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
      - Successor arrows (outgoing) turn blue; predecessor arrows (incoming) turn purple.
      - Float labels appear on each arrow in the matching color.
      - Unconnected edges fade; unconnected nodes/labels fade.
      - The hovered node's outline and labels turn red.
    On unhover: hover state clears but float filter is re-applied.
    Float slider: hides nodes/arrows whose float exceeds the chosen threshold.
    """
    succ_edge_map_json   = json.dumps(js_data["succ_edge_map"])
    pred_edge_map_json   = json.dumps(js_data["pred_edge_map"])
    succ_conn_map_json   = json.dumps(js_data["succ_conn_map"])
    pred_conn_map_json   = json.dumps(js_data["pred_conn_map"])
    all_edge_json        = json.dumps(js_data["all_edge_indices"])
    edge_line_json       = json.dumps(js_data["edge_line_indices"])
    edge_arrow_json      = json.dumps(js_data["edge_arrow_indices"])
    num_connections      = js_data["num_connections"]
    pred_label_trace_idx = js_data["pred_label_trace_idx"]
    succ_label_trace_idx = js_data["succ_label_trace_idx"]
    node_neighbors_json  = json.dumps(js_data["node_neighbors"])
    node_codes_json      = json.dumps(js_data["node_codes"])
    node_floats_json     = json.dumps(js_data["node_floats"])
    conn_src_floats_json = json.dumps(js_data["conn_src_floats"])
    conn_tgt_floats_json = json.dumps(js_data["conn_tgt_floats"])
    node_trace_idx       = js_data["node_trace_idx"]
    below_trace_idx      = js_data["below_label_trace_idx"]
    slider_max           = js_data["slider_max"]
    node_label_color     = _KEY_BORDER
    below_label_color    = "#64748b"
    default_edge_color   = _EDGE_COLOR
    succ_color           = _SUCC_EDGE_COLOR
    pred_color           = _PRED_EDGE_COLOR

    return f"""
(function() {{
    var succEdgeMap      = {succ_edge_map_json};
    var predEdgeMap      = {pred_edge_map_json};
    var succConnMap      = {succ_conn_map_json};
    var predConnMap      = {pred_conn_map_json};
    var allEdgeIdx       = {all_edge_json};
    var edgeLineIndices  = {edge_line_json};
    var edgeArrowIndices = {edge_arrow_json};
    var edgeLineSet      = new Set(edgeLineIndices);
    var edgeArrowSet     = new Set(edgeArrowIndices);
    var numConns         = {num_connections};
    var predLabelTraceIdx= {pred_label_trace_idx};
    var succLabelTraceIdx= {succ_label_trace_idx};
    var nodeNeighbors    = {node_neighbors_json};
    var nodeCodes        = {node_codes_json};
    var nodeFloats       = {node_floats_json};
    var connSrcFloats    = {conn_src_floats_json};
    var connTgtFloats    = {conn_tgt_floats_json};
    var nodeTraceIdx     = {node_trace_idx};
    var belowTraceIdx    = {below_trace_idx};
    var sliderMax        = {slider_max};

    var gd = document.querySelector('.js-plotly-plot');
    if (!gd || typeof gd.on !== 'function') return;

    var currentFilter = Infinity;   // no filter by default

    // ---------------------------------------------------------------- float filter
    function nodeVisible(c) {{
        var f = nodeFloats[c];
        return f === null || f === undefined || f <= currentFilter;
    }}

    function applyFloatFilter(maxDays) {{
        currentFilter = maxDays;

        // Nodes
        var nodeOp = nodeCodes.map(function(c) {{ return nodeVisible(c) ? 1.0 : 0.0; }});
        var nodeLabelCol = nodeCodes.map(function(c) {{
            return nodeVisible(c) ? '{node_label_color}' : 'rgba(0,0,0,0)';
        }});
        Plotly.restyle(gd,
            {{'marker.opacity': [nodeOp], 'textfont.color': [nodeLabelCol],
              'marker.line.color': [nodeLabelCol]}},
            [nodeTraceIdx]);
        if (belowTraceIdx >= 0) {{
            var belowCol = nodeCodes.map(function(c) {{
                return nodeVisible(c) ? '{below_label_color}' : 'rgba(0,0,0,0)';
            }});
            Plotly.restyle(gd, {{'textfont.color': [belowCol]}}, [belowTraceIdx]);
        }}

        // Edges — hide if either endpoint exceeds filter
        var showLineIdx = [], showArrowIdx = [], hideLineIdx = [], hideArrowIdx = [];
        for (var k = 0; k < numConns; k++) {{
            var sf = connSrcFloats[k], tf = connTgtFloats[k];
            var show = (sf === null || sf <= maxDays) && (tf === null || tf <= maxDays);
            if (show) {{
                showLineIdx.push(edgeLineIndices[k]);
                showArrowIdx.push(edgeArrowIndices[k]);
            }} else {{
                hideLineIdx.push(edgeLineIndices[k]);
                hideArrowIdx.push(edgeArrowIndices[k]);
            }}
        }}
        if (showLineIdx.length)  Plotly.restyle(gd, {{'line.color':   '{default_edge_color}', opacity: 1.0}}, showLineIdx);
        if (showArrowIdx.length) Plotly.restyle(gd, {{'marker.color': '{default_edge_color}', opacity: 1.0}}, showArrowIdx);
        if (hideLineIdx.length)  Plotly.restyle(gd, {{opacity: 0.0}}, hideLineIdx);
        if (hideArrowIdx.length) Plotly.restyle(gd, {{opacity: 0.0}}, hideArrowIdx);

        // Hide float labels (hover will re-show relevant ones)
        if (predLabelTraceIdx >= 0) {{
            Plotly.restyle(gd, {{'textfont.color': 'rgba(0,0,0,0)'}}, [predLabelTraceIdx, succLabelTraceIdx]);
        }}
    }}

    // ---------------------------------------------------------------- hover
    gd.on('plotly_hover', function(eventData) {{
        var pt   = eventData.points[0];
        var code = pt.customdata;
        if (!code) return;

        // --- edges (respect float filter) ---
        // Only show arrows where the connected node passes the current filter
        var visSuccConnIdx = (succConnMap[code] || []).filter(function(k) {{
            var tf = connTgtFloats[k];
            return tf === null || tf <= currentFilter;
        }});
        var visPredConnIdx = (visPredConnIdx = (predConnMap[code] || []).filter(function(k) {{
            var sf = connSrcFloats[k];
            return sf === null || sf <= currentFilter;
        }}));

        // Build set of visible connected trace indices
        var visConnTraceSet = new Set();
        visSuccConnIdx.forEach(function(k) {{
            visConnTraceSet.add(edgeLineIndices[k]);
            visConnTraceSet.add(edgeArrowIndices[k]);
        }});
        visPredConnIdx.forEach(function(k) {{
            visConnTraceSet.add(edgeLineIndices[k]);
            visConnTraceSet.add(edgeArrowIndices[k]);
        }});

        // Build set of currently filtered-out trace indices (stay hidden at 0)
        var filteredOutSet = new Set();
        for (var k = 0; k < numConns; k++) {{
            var sf = connSrcFloats[k], tf2 = connTgtFloats[k];
            if ((sf !== null && sf > currentFilter) || (tf2 !== null && tf2 > currentFilter)) {{
                filteredOutSet.add(edgeLineIndices[k]);
                filteredOutSet.add(edgeArrowIndices[k]);
            }}
        }}

        var dimIdx  = allEdgeIdx.filter(function(i) {{ return !visConnTraceSet.has(i) && !filteredOutSet.has(i); }});
        var hideIdx = allEdgeIdx.filter(function(i) {{ return filteredOutSet.has(i); }});
        if (dimIdx.length)  Plotly.restyle(gd, {{opacity: 0.04}}, dimIdx);
        if (hideIdx.length) Plotly.restyle(gd, {{opacity: 0.0}},  hideIdx);

        // Successor arrows → blue
        var succLineIdx  = visSuccConnIdx.map(function(k) {{ return edgeLineIndices[k]; }});
        var succArrowIdx = visSuccConnIdx.map(function(k) {{ return edgeArrowIndices[k]; }});
        if (succLineIdx.length)  Plotly.restyle(gd, {{'line.color':   '{succ_color}', opacity: 1.0}}, succLineIdx);
        if (succArrowIdx.length) Plotly.restyle(gd, {{'marker.color': '{succ_color}', opacity: 1.0}}, succArrowIdx);

        // Predecessor arrows → purple
        var predLineIdx  = visPredConnIdx.map(function(k) {{ return edgeLineIndices[k]; }});
        var predArrowIdx = visPredConnIdx.map(function(k) {{ return edgeArrowIndices[k]; }});
        if (predLineIdx.length)  Plotly.restyle(gd, {{'line.color':   '{pred_color}', opacity: 1.0}}, predLineIdx);
        if (predArrowIdx.length) Plotly.restyle(gd, {{'marker.color': '{pred_color}', opacity: 1.0}}, predArrowIdx);

        // --- nodes + above labels (respect filter) ---
        var connNodes = new Set(nodeNeighbors[code] || []);
        connNodes.add(code);

        var markerOpacities = nodeCodes.map(function(c) {{
            if (!nodeVisible(c)) return 0.0;
            return connNodes.has(c) ? 1.0 : 0.06;
        }});
        var labelColors = nodeCodes.map(function(c) {{
            if (!nodeVisible(c)) return 'rgba(0,0,0,0)';
            if (c === code) return 'red';
            return connNodes.has(c) ? '{node_label_color}' : 'rgba(0,0,0,0.04)';
        }});
        var markerLineColors = nodeCodes.map(function(c) {{
            if (!nodeVisible(c)) return 'rgba(0,0,0,0)';
            return c === code ? 'red' : '{node_label_color}';
        }});
        Plotly.restyle(gd,
            {{'marker.opacity': [markerOpacities], 'textfont.color': [labelColors],
              'marker.line.color': [markerLineColors]}},
            [nodeTraceIdx]);

        // --- below labels ---
        if (belowTraceIdx >= 0) {{
            var belowColors = nodeCodes.map(function(c) {{
                if (!nodeVisible(c)) return 'rgba(0,0,0,0)';
                if (c === code) return 'red';
                return connNodes.has(c) ? '{below_label_color}' : 'rgba(0,0,0,0.04)';
            }});
            Plotly.restyle(gd, {{'textfont.color': [belowColors]}}, [belowTraceIdx]);
        }}

        // --- float labels on arrows (only for filter-passing connections) ---
        if (predLabelTraceIdx >= 0) {{
            var invis = 'rgba(0,0,0,0)';
            var predLabelColors = Array(numConns).fill(invis);
            visPredConnIdx.forEach(function(k) {{ predLabelColors[k] = '{pred_color}'; }});
            Plotly.restyle(gd, {{'textfont.color': [predLabelColors]}}, [predLabelTraceIdx]);

            var succLabelColors = Array(numConns).fill(invis);
            visSuccConnIdx.forEach(function(k) {{ succLabelColors[k] = '{succ_color}'; }});
            Plotly.restyle(gd, {{'textfont.color': [succLabelColors]}}, [succLabelTraceIdx]);
        }}
    }});

    // ---------------------------------------------------------------- unhover
    gd.on('plotly_unhover', function() {{
        applyFloatFilter(currentFilter);
    }});

    // ---------------------------------------------------------------- float slider
    var slider  = document.getElementById('float-slider');
    var valLabel= document.getElementById('float-val');
    if (slider) {{
        slider.addEventListener('input', function() {{
            var v = parseInt(this.value);
            if (v >= sliderMax) {{
                valLabel.textContent = 'All activities';
                applyFloatFilter(Infinity);
            }} else {{
                valLabel.textContent = '\u2264 ' + v + 'd float';
                applyFloatFilter(v);
            }}
        }});
    }}
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
    succ_edge_map: dict[str, list[int]] = {}   # source_code -> trace indices (outgoing)
    pred_edge_map: dict[str, list[int]] = {}   # target_code -> trace indices (incoming)
    succ_conn_map: dict[str, list[int]] = {}   # source_code -> connection indices
    pred_conn_map: dict[str, list[int]] = {}   # target_code -> connection indices
    all_edge_indices: list[int] = []
    edge_line_indices: list[int] = []
    edge_arrow_indices: list[int] = []
    conn_mid_x: list[float] = []
    conn_mid_y: list[float] = []
    pred_float_texts: list[str] = []        # source task float string, one per connection
    succ_float_texts: list[str] = []        # target task float string, one per connection
    conn_src_floats: list[float | None] = []  # source task float in days, one per connection
    conn_tgt_floats: list[float | None] = []  # target task float in days, one per connection
    node_floats: dict[str, float | None] = {}  # task_code -> float in days
    pred_label_trace_idx: int = -1
    succ_label_trace_idx: int = -1
    node_trace_idx: int = -1
    below_label_trace_idx: int = -1
    conn_k: int = 0   # connection counter

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
        succ_edge_map.setdefault(conn.source_code, []).append(trace_idx)
        pred_edge_map.setdefault(conn.target_code, []).append(trace_idx)
        all_edge_indices.append(trace_idx)
        edge_line_indices.append(trace_idx)
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
        succ_edge_map.setdefault(conn.source_code, []).append(trace_idx)
        pred_edge_map.setdefault(conn.target_code, []).append(trace_idx)
        all_edge_indices.append(trace_idx)
        edge_arrow_indices.append(trace_idx)
        trace_idx += 1

        # Per-connection data for float labels
        succ_conn_map.setdefault(conn.source_code, []).append(conn_k)
        pred_conn_map.setdefault(conn.target_code, []).append(conn_k)
        conn_mid_x.append((x0 + x1) / 2)
        conn_mid_y.append((y0 + y1) / 2)
        src_task = tasks.get(conn.source_id)
        tgt_task = tasks.get(conn.target_id)
        src_tf = src_task.total_float_hr_cnt if src_task else None
        tgt_tf = tgt_task.total_float_hr_cnt if tgt_task else None
        src_tf_days = src_tf / 8 if src_tf is not None else None
        tgt_tf_days = tgt_tf / 8 if tgt_tf is not None else None
        pred_float_texts.append(f"{src_tf_days:.1f}d" if src_tf_days is not None else "N/A")
        succ_float_texts.append(f"{tgt_tf_days:.1f}d" if tgt_tf_days is not None else "N/A")
        conn_src_floats.append(src_tf_days)
        conn_tgt_floats.append(tgt_tf_days)
        conn_k += 1

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

    # ------------------------------------------------------------------ float labels on edges (invisible until hover)
    _INVIS = "rgba(0,0,0,0)"
    if conn_mid_x:
        pred_label_trace_idx = trace_idx
        fig.add_trace(go.Scatter(
            x=conn_mid_x, y=conn_mid_y,
            mode="text",
            text=pred_float_texts,
            textposition="middle center",
            textfont=dict(size=8, color=[_INVIS] * len(conn_mid_x)),
            hoverinfo="skip",
            showlegend=False,
        ))
        trace_idx += 1

        succ_label_trace_idx = trace_idx
        fig.add_trace(go.Scatter(
            x=conn_mid_x, y=conn_mid_y,
            mode="text",
            text=succ_float_texts,
            textposition="middle center",
            textfont=dict(size=8, color=[_INVIS] * len(conn_mid_x)),
            hoverinfo="skip",
            showlegend=False,
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

        tf = task.total_float_hr_cnt
        tf_days = tf / 8 if tf is not None else None
        node_floats[task.task_code] = tf_days

        early_start = _parse_date(task.early_start_date)
        early_end   = _parse_date(task.early_end_date)
        float_str = f"{tf_days:.1f}d" if tf_days is not None else "N/A"
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

    known_floats = [v for v in node_floats.values() if v is not None]
    slider_max = int(math.ceil(max(known_floats) / 5) * 5) if known_floats else 60
    slider_max = max(slider_max, 10)

    js_data = {
        "succ_edge_map": succ_edge_map,
        "pred_edge_map": pred_edge_map,
        "succ_conn_map": succ_conn_map,
        "pred_conn_map": pred_conn_map,
        "all_edge_indices": all_edge_indices,
        "edge_line_indices": edge_line_indices,
        "edge_arrow_indices": edge_arrow_indices,
        "num_connections": conn_k,
        "pred_label_trace_idx": pred_label_trace_idx,
        "succ_label_trace_idx": succ_label_trace_idx,
        "node_trace_idx": node_trace_idx,
        "node_codes": kcodes,
        "node_neighbors": node_neighbors,
        "node_floats": node_floats,
        "conn_src_floats": conn_src_floats,
        "conn_tgt_floats": conn_tgt_floats,
        "below_label_trace_idx": below_label_trace_idx,
        "slider_max": slider_max,
    }
    return fig, js_data


def write_html(fig: go.Figure, output_path: str, js_data: dict) -> None:
    fig.write_html(output_path, include_plotlyjs="cdn")

    with open(output_path, "r", encoding="utf-8") as fh:
        html = fh.read()

    slider_max = js_data["slider_max"]
    slider_html = f"""
<div id="float-filter-bar" style="font-family:sans-serif;padding:10px 24px;background:#f8fafc;border-bottom:1px solid #e2e8f0;display:flex;align-items:center;gap:16px;">
  <span style="font-size:13px;color:#475569;white-space:nowrap;font-weight:600;">Float filter</span>
  <input type="range" id="float-slider" min="0" max="{slider_max}" step="1" value="{slider_max}"
         style="width:320px;accent-color:#2563eb;cursor:pointer;">
  <span id="float-val" style="font-size:13px;font-weight:700;color:#1e3a8a;min-width:80px;">All activities</span>
</div>
"""
    html = html.replace("<body>", "<body>" + slider_html, 1)

    js = _build_hover_js(js_data)
    script_block = f"\n<script type=\"text/javascript\">{js}</script>\n"
    html = html.replace("</body>", script_block + "</body>", 1)

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    print(f"Diagram written to: {output_path}")
