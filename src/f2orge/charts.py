"""Table validation and offline 2D/3D chart renderers."""
from __future__ import annotations

import html
import json
import math
from typing import Dict, List, Optional, Tuple

from .errors import ForgeError, Source
from .parser import parse
from .quantity import Quantity
from .syntax import Assign, QuantityLit
from .units import Unit


class ChartError(ForgeError):
    title = "Invalid chart"


def _column_unit(text: str) -> Optional[Unit]:
    if not text.strip():
        return None
    try:
        program = parse(Source("<chart unit>", f"chart_value = 1 {text}"))
        statement = program[0]
        if not isinstance(statement, Assign) or not isinstance(statement.expr, QuantityLit):
            raise ChartError(f"'{text}' is not a valid unit expression")
        return statement.expr.unit
    except ForgeError as err:
        raise ChartError(f"invalid unit '{text}': {err.message}") from None


def validate_table(table: object) -> Dict[str, object]:
    """Validate a JSON table and normalize columns/rows for rendering."""
    if not isinstance(table, dict):
        raise ChartError("table must be an object")
    columns = table.get("columns")
    rows = table.get("rows")
    if not isinstance(columns, list) or not 1 <= len(columns) <= 30:
        raise ChartError("table must contain between 1 and 30 columns")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 5000:
        raise ChartError("table must contain between 1 and 5000 rows")
    normalized_columns: List[Dict[str, object]] = []
    names = set()
    for column in columns:
        if not isinstance(column, dict):
            raise ChartError("each column must have a name and optional unit")
        name, unit_text = column.get("name"), column.get("unit", "")
        if not isinstance(name, str) or not name.strip() or len(name) > 80:
            raise ChartError("column names must contain 1 to 80 characters")
        if name in names:
            raise ChartError(f"duplicate column name '{name}'")
        if not isinstance(unit_text, str) or len(unit_text) > 40:
            raise ChartError(f"invalid unit for column '{name}'")
        names.add(name)
        normalized_columns.append({
            "name": name,
            "unit": unit_text.strip(),
            "parsedUnit": _column_unit(unit_text),
        })
    normalized_rows: List[List[str]] = []
    for row_index, row in enumerate(rows, start=1):
        if not isinstance(row, list) or len(row) != len(normalized_columns):
            raise ChartError(f"row {row_index} must have exactly {len(normalized_columns)} cells")
        if any(not isinstance(value, (str, int, float)) or isinstance(value, bool) for value in row):
            raise ChartError(f"row {row_index} contains an unsupported cell value")
        normalized_rows.append([str(value).strip() for value in row])
    return {"columns": normalized_columns, "rows": normalized_rows}


def _numeric_column(table: Dict[str, object], name: object) -> Tuple[Dict[str, object], List[float]]:
    columns = table["columns"]
    assert isinstance(columns, list)
    column = next((item for item in columns if item["name"] == name), None)
    if column is None:
        raise ChartError(f"unknown column '{name}'")
    rows = table["rows"]
    assert isinstance(rows, list)
    index = columns.index(column)
    values = []
    for row_index, row in enumerate(rows, start=1):
        try:
            number = float(row[index])
        except ValueError:
            raise ChartError(f"row {row_index}, column '{name}' must be numeric") from None
        if not math.isfinite(number):
            raise ChartError(f"row {row_index}, column '{name}' must be finite")
        values.append(number)
    return column, values


def _label(column: Dict[str, object]) -> str:
    unit = column["unit"]
    return f"{column['name']} ({unit})" if unit else str(column["name"])


def render_table_svg(table_data: object, chart_type: str, x_name: object,
                     y_names: object) -> str:
    table = validate_table(table_data)
    if chart_type not in ("line", "scatter", "bar"):
        raise ChartError("chart type must be line, scatter, or bar")
    columns = table["columns"]
    assert isinstance(columns, list)
    x_column = next((item for item in columns if item["name"] == x_name), None)
    if x_column is None:
        raise ChartError(f"unknown column '{x_name}'")
    if not isinstance(y_names, list) or not 1 <= len(y_names) <= 10:
        raise ChartError("select between 1 and 10 value columns")
    if chart_type == "bar":
        rows = table["rows"]
        assert isinstance(rows, list)
        x_index = columns.index(x_column)
        x_values = [row[x_index] for row in rows]
        if len(set(x_values)) != len(x_values):
            raise ChartError("bar chart category labels must be unique")
    else:
        x_column, x_values = _numeric_column(table, x_name)
    all_series = []
    for name in y_names:
        column, values = _numeric_column(table, name)
        if name == x_name:
            raise ChartError("the horizontal and value columns must be different")
        all_series.append((column, values))
    dimensions = [item[0]["parsedUnit"].dim if item[0]["parsedUnit"] else None
                  for item in all_series]
    if any(dim != dimensions[0] for dim in dimensions[1:]):
        raise ChartError("all value columns must use compatible units")
    reference_unit = all_series[0][0]["parsedUnit"]
    converted_series = []
    for column, values in all_series:
        unit = column["parsedUnit"]
        converted = []
        for value in values:
            quantity = Quantity.from_unit(value, unit) if unit else Quantity(value)
            magnitude = quantity.magnitude(reference_unit) if reference_unit else quantity.value
            if not math.isfinite(magnitude):
                raise ChartError(f"values in column '{column['name']}' exceed the supported numeric range")
            converted.append(magnitude)
        converted_series.append((column, converted))
    all_series = converted_series

    width, height = 900, 560
    left, top, right, bottom = 88, 65, 28, 72
    plot_w, plot_h = width - left - right, height - top - bottom
    flat = [value for _, values in all_series for value in values]
    y_min, y_max = min(0.0, min(flat)), max(0.0, max(flat))
    if y_min == y_max:
        y_min -= 1
        y_max += 1
    y_pad = (y_max - y_min) * 0.06
    y_min -= y_pad
    y_max += y_pad
    if chart_type == "bar":
        x_min, x_max = -0.5, len(x_values) - 0.5
    else:
        assert isinstance(x_values, list)
        x_min, x_max = min(x_values), max(x_values)
        if not math.isfinite(x_max - x_min):
            raise ChartError("horizontal values exceed the supported numeric range")
        if x_min == x_max:
            x_pad = max(abs(x_min) * 0.05, 1.0)
            x_min, x_max = x_min - x_pad, x_max + x_pad
            if not math.isfinite(x_min) or not math.isfinite(x_max):
                raise ChartError("horizontal values exceed the supported numeric range")
    if not math.isfinite(y_max - y_min):
        raise ChartError("value series exceed the supported numeric range")
    palette = ("#d66f32", "#4d8195", "#829477", "#ac715f", "#806ca0",
               "#b28e45", "#508d77", "#8b687c", "#697b9c", "#a17548")

    def sx(value: float) -> float:
        return left + (value - x_min) / (x_max - x_min) * plot_w

    def sy(value: float) -> float:
        return top + (y_max - value) / (y_max - y_min) * plot_h

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
           'role="img" aria-label="Table chart">', '<rect width="100%" height="100%" fill="#fff"/>']
    title = html.escape(f"{', '.join(str(item[0]['name']) for item in all_series)} vs {_label(x_column)}")
    out.append(f'<text x="{width/2}" y="29" text-anchor="middle" font-size="18" '
               f'font-family="sans-serif" fill="#30343a">{title}</text>')
    for i in range(6):
        val = y_min + (y_max - y_min) * i / 5
        y = sy(val)
        out.append(f'<line x1="{left}" y1="{y:.2f}" x2="{left+plot_w}" y2="{y:.2f}" '
                   'stroke="#e3e7e9"/>')
        out.append(f'<text x="{left-10}" y="{y+4:.2f}" text-anchor="end" font-size="11" '
                   f'font-family="sans-serif" fill="#5c6870">{val:.5g}</text>')
    out.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" stroke="#66727a"/>')
    out.append(f'<line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" '
               'stroke="#66727a"/>')
    if chart_type == "bar":
        labels = x_values
        group_width = plot_w / max(1, len(labels))
        bar_width = min(42, group_width * 0.72 / len(all_series))
        for series_index, (column, values) in enumerate(all_series):
            out.append(f'<g data-series="{series_index}">')
            for index, value in enumerate(values):
                x = sx(float(index)) - len(all_series) * bar_width / 2 + series_index * bar_width
                y = sy(max(value, 0))
                base = sy(min(value, 0))
                out.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width:.2f}" '
                           f'height="{max(1, base-y):.2f}" fill="{palette[series_index]}" '
                           f'opacity=".88"><title>{html.escape(str(labels[index]))}: '
                           f'{value:.6g} {_label(column)}</title></rect>')
            out.append("</g>")
        stride = max(1, math.ceil(len(labels) / 12))
        for index in range(0, len(labels), stride):
            out.append(f'<text x="{sx(float(index)):.2f}" y="{top+plot_h+20}" text-anchor="middle" '
                       f'font-size="10" font-family="sans-serif" fill="#58646b">'
                       f'{html.escape(str(labels[index])[:18])}</text>')
    else:
        for series_index, (column, values) in enumerate(all_series):
            out.append(f'<g data-series="{series_index}">')
            coords = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in zip(x_values, values))
            if chart_type == "line":
                out.append(f'<polyline points="{coords}" fill="none" stroke="{palette[series_index]}" '
                           'stroke-width="2.5" stroke-linejoin="round"/>')
            for x, y, value in zip(x_values, values, values):
                if chart_type == "scatter":
                    out.append(f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="4.3" '
                               f'fill="{palette[series_index]}"><title>{x:.6g}, {value:.6g} '
                               f'{html.escape(_label(column))}</title></circle>')
            out.append("</g>")
    x_label = html.escape(_label(x_column))
    y_label = html.escape(_label(all_series[0][0]))
    out.append(f'<text x="{left+plot_w/2}" y="{height-18}" text-anchor="middle" '
               f'font-size="12" font-family="sans-serif" fill="#39434a">{x_label}</text>')
    out.append(f'<text transform="translate(22 {top+plot_h/2}) rotate(-90)" text-anchor="middle" '
               f'font-size="12" font-family="sans-serif" fill="#39434a">{y_label}</text>')
    for i, (column, _) in enumerate(all_series):
        lx = left + 10 + i * min(180, plot_w / max(1, len(all_series)))
        out.append(f'<g data-series="{i}"><rect x="{lx}" y="43" width="10" height="10" '
                   f'fill="{palette[i]}"/><text x="{lx+15}" y="52" font-size="10" '
                   f'font-family="sans-serif" fill="#465159">{html.escape(str(column["name"]))}'
                   '</text></g>')
    out.append("</svg>")
    return "".join(out)


def render_3d_html(table_data: object, chart_type: str, x_name: object,
                   y_name: object, z_name: object, title: str = "") -> str:
    table = validate_table(table_data)
    if chart_type not in ("scatter3d", "line3d", "surface3d"):
        raise ChartError("3D chart type must be scatter3d, line3d, or surface3d")
    x_column, xs = _numeric_column(table, x_name)
    y_column, ys = _numeric_column(table, y_name)
    z_column, zs = _numeric_column(table, z_name)
    if len({x_name, y_name, z_name}) != 3:
        raise ChartError("select three different columns for the 3D axes")
    points = [[x, y, z] for x, y, z in zip(xs, ys, zs)]
    grid = None
    if chart_type == "surface3d":
        ux, uy = sorted(set(xs)), sorted(set(ys))
        if len(ux) < 2 or len(uy) < 2 or len(ux) * len(uy) != len(points):
            raise ChartError("surface data must form a complete grid with at least two x and y values")
        lookup = {(x, y): z for x, y, z in points}
        if len(lookup) != len(points) or any((x, y) not in lookup for x in ux for y in uy):
            raise ChartError("surface data must contain exactly one z value for each x/y pair")
        grid = [[[lookup[(x, y)] for y in uy] for x in ux], ux, uy]
    values = [xs, ys, zs]
    limits = []
    for axis in values:
        low, high = min(axis), max(axis)
        if low == high:
            padding = max(abs(low) * 0.05, 1.0)
            low, high = low - padding, high + padding
        span = high - low
        if not math.isfinite(low) or not math.isfinite(high):
            raise ChartError("3D axis values exceed the supported numeric range")
        if not math.isfinite(span):
            raise ChartError("3D axis values exceed the supported numeric range")
        limits.append([low, high, span])
    payload = {
        "type": chart_type, "points": points, "grid": grid, "limits": limits,
        "labels": [_label(x_column), _label(y_column), _label(z_column)],
        "title": title or f"{chart_type} table plot",
    }
    data = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).replace("<", "\\u003c")
    return _3D_TEMPLATE.replace("__DATA__", data).replace("__SCRIPT__", THREE_D_SCRIPT)


def render_3d_preview_html(table_data: object, chart_type: str, x_name: object,
                           y_name: object, z_name: object, title: str = "") -> str:
    page = render_3d_html(table_data, chart_type, x_name, y_name, z_name, title)
    return page.replace(f"<script>{THREE_D_SCRIPT}</script>", '<script src="/chart3d.js"></script>')


def render_table_html(svg: str, title: str) -> str:
    """Create a self-contained HTML page with zoom/pan controls around an SVG chart."""
    safe_title = html.escape(title)
    safe_svg = svg.replace("</script", "<\\/script")
    return f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{safe_title}</title><style>body{{margin:0;background:#f4f2ee;color:#29343a;
font:14px system-ui,sans-serif}}header{{padding:10px 16px}}svg{{display:block;width:100%;
height:calc(100vh - 60px);background:white;touch-action:none;cursor:grab}}svg.dragging{{cursor:grabbing}}
</style><header><strong>{safe_title}</strong> · scroll to zoom, drag to pan</header>{safe_svg}
<script>const s=document.querySelector("svg");let b=s.viewBox.baseVal,original=[b.x,b.y,b.width,b.height],d=null;
s.addEventListener("wheel",e=>{{e.preventDefault();let r=s.getBoundingClientRect(),k=e.deltaY<0?.9:1.1,
x=(e.clientX-r.left)/r.width*b.width+b.x,y=(e.clientY-r.top)/r.height*b.height+b.y;
b.width*=k;b.height*=k;b.x=x-(x-b.x)*k;b.y=y-(y-b.y)*k}},{{passive:false}});
s.addEventListener("pointerdown",e=>{{d=[e.clientX,e.clientY];s.setPointerCapture(e.pointerId);s.classList.add("dragging")}});
s.addEventListener("pointermove",e=>{{if(!d)return;let r=s.getBoundingClientRect();
b.x-=(e.clientX-d[0])*b.width/r.width;b.y-=(e.clientY-d[1])*b.height/r.height;d=[e.clientX,e.clientY]}});
s.addEventListener("pointerup",()=>{{d=null;s.classList.remove("dragging")}});
</script></html>"""


_3D_TEMPLATE = """<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>F²ORGE 3D Graph</title>
<style>body{margin:0;background:#f4f2ee;color:#29343a;font:14px system-ui,sans-serif}
header{padding:10px 16px}canvas{display:block;width:min(100vw,1100px);height:min(72vh,720px);
margin:auto;background:white;border:1px solid #d5dadd;touch-action:none}small{color:#65717a}</style>
<header><strong id="title"></strong><br><small>Drag to rotate · scroll to zoom · reset with the button</small>
<button id="reset">Reset view</button></header><canvas id="plot" width="1100" height="720"></canvas>
<script type="application/json" id="chart-data">__DATA__</script>
<script>__SCRIPT__</script></html>"""


THREE_D_SCRIPT = """const D=JSON.parse(document.querySelector("#chart-data").textContent), c=document.querySelector("#plot"),ctx=c.getContext("2d");
document.querySelector("#title").textContent=D.title;
let az=.75,el=.45,zoom=1,drag=null;
function project(p){const q=p.map((v,i)=>(v-(D.limits[i][0]+D.limits[i][1])/2)/D.limits[i][2]*2);
const ca=Math.cos(az),sa=Math.sin(az),ce=Math.cos(el),se=Math.sin(el);
const x=ca*q[0]-sa*q[1],y=sa*q[0]+ca*q[1],z=ce*q[2]-se*y;
const v=se*q[2]+ce*y,s=230*zoom/(3.8+v);
return [c.width*.5+x*s,c.height*.52-z*s,v]}
function axes(){const origin=project([D.limits[0][0],D.limits[1][0],D.limits[2][0]]);
const ends=D.limits.map((a,i)=>{const p=D.limits.map(x=>x[0]);p[i]=a[1];return project(p)});
ctx.strokeStyle="#65727a";ctx.fillStyle="#3c484f";ctx.lineWidth=1.5;
ends.forEach((p,i)=>{ctx.beginPath();ctx.moveTo(...origin.slice(0,2));ctx.lineTo(...p.slice(0,2));ctx.stroke();
ctx.fillText(D.labels[i],p[0]+5,p[1]-5)})}
function draw(){ctx.clearRect(0,0,c.width,c.height);axes();
if(D.type==="surface3d"){const [g,xs,ys]=D.grid,faces=[];
for(let i=0;i<xs.length-1;i++)for(let j=0;j<ys.length-1;j++){
const corners=[[xs[i],ys[j],g[i][j]],[xs[i+1],ys[j],g[i+1][j]],
[xs[i+1],ys[j+1],g[i+1][j+1]],[xs[i],ys[j+1],g[i][j+1]]].map(project);
faces.push({corners,depth:corners.reduce((a,p)=>a+p[2],0)/4,
z:(g[i][j]+g[i+1][j]+g[i+1][j+1]+g[i][j+1])/4})}
faces.sort((a,b)=>a.depth-b.depth);const zl=D.limits[2][0],zr=D.limits[2][1]||zl+1;
faces.forEach(f=>{const t=(f.z-zl)/(zr-zl),r=Math.round(40+190*t),b=Math.round(190-125*t);
ctx.beginPath();f.corners.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));
ctx.closePath();ctx.fillStyle=`rgba(${r},110,${b},.78)`;ctx.fill();ctx.strokeStyle="#ffffff99";ctx.stroke()})}
else{const pts=D.points.map(project);if(D.type==="line3d"){ctx.beginPath();pts.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));
ctx.strokeStyle="#d66f32";ctx.lineWidth=3;ctx.stroke()}
pts.forEach(p=>{ctx.beginPath();ctx.arc(p[0],p[1],4,0,Math.PI*2);ctx.fillStyle="#d66f32";ctx.fill()})}}
c.addEventListener("pointerdown",e=>{drag=[e.clientX,e.clientY];c.setPointerCapture(e.pointerId)});
c.addEventListener("pointermove",e=>{if(!drag)return;az+=(e.clientX-drag[0])*.009;el=Math.max(-1.45,Math.min(1.45,el+(e.clientY-drag[1])*.009));drag=[e.clientX,e.clientY];draw()});
c.addEventListener("pointerup",()=>drag=null);c.addEventListener("wheel",e=>{e.preventDefault();zoom=Math.max(.4,Math.min(3,zoom*(e.deltaY<0?1.1:.9)));draw()},{passive:false});
document.querySelector("#reset").addEventListener("click",()=>{az=.75;el=.45;zoom=1;draw()});draw();
"""
