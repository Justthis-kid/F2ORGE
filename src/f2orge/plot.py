"""Portable SVG rendering for sampled equation outputs."""
from __future__ import annotations

import html
from xml.sax.saxutils import escape
from typing import Sequence, Tuple

from .quantity import format_number


def render_svg(
    title: str,
    x_label: str,
    y_label: str,
    series: Sequence[Tuple[str, Sequence[Tuple[float, float]]]],
) -> str:
    width, height = 800, 500
    left, right, top, bottom = 82, 24, 48, 68
    plot_width, plot_height = width - left - right, height - top - bottom
    xs = [x for _, curve in series for x, _ in curve]
    ys = [y for _, curve in series for _, y in curve]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    if xmin == xmax:
        padding = max(abs(xmin) * 0.05, 1.0)
        xmin, xmax = xmin - padding, xmax + padding
    if ymin == ymax:
        padding = max(abs(ymin) * 0.05, 1.0)
        ymin, ymax = ymin - padding, ymax + padding
    xpad, ypad = (xmax - xmin) * 0.04, (ymax - ymin) * 0.04
    xmin, xmax = xmin - xpad, xmax + xpad
    ymin, ymax = ymin - ypad, ymax + ypad

    def sx(value: float) -> float:
        return left + (value - xmin) / (xmax - xmin) * plot_width

    def sy(value: float) -> float:
        return top + (ymax - value) / (ymax - ymin) * plot_height

    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">',
        f"<title>{escape(title)}</title>",
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width / 2:g}" y="27" text-anchor="middle" font-family="sans-serif" '
        f'font-size="18">{escape(title)}</text>',
    ]
    for index in range(6):
        xvalue = xmin + (xmax - xmin) * index / 5
        yvalue = ymin + (ymax - ymin) * index / 5
        x, y = sx(xvalue), sy(yvalue)
        elements.append(f'<path d="M {x:g} {top} V {height - bottom} M {left} {y:g} H {width - right}" '
                        'stroke="#e5e7eb" stroke-width="1"/>')
        elements.append(f'<text x="{x:g}" y="{height - bottom + 22}" text-anchor="middle" '
                        f'font-family="sans-serif" font-size="12">{format_number(xvalue)}</text>')
        elements.append(f'<text x="{left - 10}" y="{y + 4:g}" text-anchor="end" '
                        f'font-family="sans-serif" font-size="12">{format_number(yvalue)}</text>')
    elements.extend([
        f'<path d="M {left} {top} V {height - bottom} H {width - right}" fill="none" '
        'stroke="#374151" stroke-width="1.5"/>',
    ])
    colors = ("#2563eb", "#dc2626", "#059669", "#9333ea", "#d97706", "#0891b2")
    for index, (label, curve) in enumerate(series):
        color = colors[index % len(colors)]
        elements.append(
            f'<polyline points="{" ".join(f"{sx(x):g},{sy(y):g}" for x, y in curve)}" '
            f'fill="none" stroke="{color}" stroke-width="2.5" stroke-linejoin="round" '
            'stroke-linecap="round"/>'
        )
        if len(series) > 1:
            row_y = top + 18 + index * 19
            elements.append(f'<path d="M {width - 164} {row_y} H {width - 145}" '
                            f'stroke="{color}" stroke-width="3"/>')
            elements.append(f'<text x="{width - 139}" y="{row_y + 4}" font-family="sans-serif" '
                            f'font-size="12">{escape(label)}</text>')
    elements.extend([
        f'<text x="{left + plot_width / 2:g}" y="{height - 16}" text-anchor="middle" '
        f'font-family="sans-serif" font-size="14">{escape(x_label)}</text>',
        f'<text x="20" y="{top + plot_height / 2:g}" text-anchor="middle" '
        f'font-family="sans-serif" font-size="14" '
        f'transform="rotate(-90 20 {top + plot_height / 2:g})">{escape(y_label)}</text>',
        "</svg>",
    ])
    return "\n".join(elements) + "\n"


def render_interactive_html(
    svg: str,
    title: str,
    series_labels: Sequence[str],
) -> str:
    """Wrap a portable SVG with offline zoom, pan, reset, and curve controls."""
    controls = ""
    if len(series_labels) > 1:
        controls = '<fieldset class="curves"><legend>Curves</legend>'
        for index, label in enumerate(series_labels):
            controls += (
                f'<label><input type="checkbox" data-series="{index}" checked> '
                f'{html.escape(label or f"Series {index + 1}")}</label>'
            )
        controls += "</fieldset>"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root{{color-scheme:light dark;font:16px system-ui,sans-serif}}
body{{max-width:1000px;margin:2rem auto;padding:0 1rem;background:Canvas;color:CanvasText}}
h1{{font-size:1.35rem}} .toolbar{{display:flex;align-items:center;gap:.8rem;flex-wrap:wrap;margin:1rem 0}}
button{{font:inherit;padding:.45rem .8rem;border:1px solid GrayText;border-radius:.35rem;background:Canvas;color:CanvasText;cursor:pointer}}
.hint{{color:GrayText;font-size:.9rem}} .curves{{display:flex;gap:1rem;flex-wrap:wrap;border:0;padding:0;margin:0}}
.curves label{{cursor:pointer}} #graph svg{{display:block;width:100%;height:auto;touch-action:none;cursor:grab}}
#graph svg.dragging{{cursor:grabbing}}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<div class="toolbar"><button id="reset" type="button">Reset view</button>
<span class="hint">Use the mouse wheel or trackpad to zoom; drag to pan.</span>{controls}</div>
<div id="graph">{svg}</div>
<script>
"use strict";
const svg=document.querySelector("#graph svg");
const original=svg.getAttribute("viewBox").split(/\\s+/).map(Number);
const bounds=()=>svg.viewBox.baseVal;
function zoom(event){{
  event.preventDefault();
  const box=bounds(),rect=svg.getBoundingClientRect();
  const px=box.x+(event.clientX-rect.left)*box.width/rect.width;
  const py=box.y+(event.clientY-rect.top)*box.height/rect.height;
  const scale=event.deltaY<0?0.8:1.25;
  const width=box.width*scale,height=box.height*scale;
  svg.setAttribute("viewBox",`${{px-(px-box.x)*scale}} ${{py-(py-box.y)*scale}} ${{width}} ${{height}}`);
}}
let drag=null;
svg.addEventListener("wheel",zoom,{{passive:false}});
svg.addEventListener("pointerdown",event=>{{
  if(event.button!==0)return;
  const box=bounds();
  drag={{x:event.clientX,y:event.clientY,left:box.x,top:box.y,width:box.width,height:box.height}};
  svg.classList.add("dragging");svg.setPointerCapture(event.pointerId);
}});
svg.addEventListener("pointermove",event=>{{
  if(!drag)return;
  const rect=svg.getBoundingClientRect();
  const dx=(event.clientX-drag.x)*drag.width/rect.width;
  const dy=(event.clientY-drag.y)*drag.height/rect.height;
  svg.setAttribute("viewBox",`${{drag.left-dx}} ${{drag.top-dy}} ${{drag.width}} ${{drag.height}}`);
}});
function stopDrag(){{drag=null;svg.classList.remove("dragging");}}
svg.addEventListener("pointerup",stopDrag);svg.addEventListener("pointercancel",stopDrag);
document.querySelector("#reset").addEventListener("click",()=>svg.setAttribute("viewBox",original.join(" ")));
document.querySelectorAll("[data-series]").forEach(control=>control.addEventListener("change",()=>{{
  const curve=svg.querySelectorAll("polyline")[Number(control.dataset.series)];
  if(curve)curve.style.display=control.checked?"":"none";
}}));
</script>
</body>
</html>
"""
