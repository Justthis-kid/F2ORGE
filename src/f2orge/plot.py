"""Portable SVG rendering for sampled equation outputs."""
from __future__ import annotations

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
