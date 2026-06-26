from __future__ import annotations

import html
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: coverage_badge.py COVERAGE_XML OUTPUT_SVG", file=sys.stderr)
        return 2

    coverage_xml = Path(sys.argv[1])
    output_svg = Path(sys.argv[2])
    label, color = _coverage_label_and_color(coverage_xml)
    output_svg.parent.mkdir(parents=True, exist_ok=True)
    output_svg.write_text(_badge_svg("coverage", label, color), encoding="utf-8")
    return 0


def _coverage_label_and_color(coverage_xml: Path) -> tuple[str, str]:
    if not coverage_xml.is_file():
        return "unknown", "#9f9f9f"

    try:
        root = ET.parse(coverage_xml).getroot()
        percentage = round(float(root.attrib["line-rate"]) * 100)
    except (ET.ParseError, KeyError, TypeError, ValueError):
        return "unknown", "#9f9f9f"

    if percentage >= 90:
        color = "#4c1"
    elif percentage >= 80:
        color = "#97ca00"
    elif percentage >= 70:
        color = "#dfb317"
    elif percentage >= 60:
        color = "#fe7d37"
    else:
        color = "#e05d44"
    return f"{percentage}%", color


def _badge_svg(left: str, right: str, color: str) -> str:
    left_width = _text_width(left)
    right_width = _text_width(right)
    width = left_width + right_width
    escaped_left = html.escape(left)
    escaped_right = html.escape(right)
    escaped_color = html.escape(color)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="20" role="img" aria-label="{escaped_left}: {escaped_right}">
  <title>{escaped_left}: {escaped_right}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r">
    <rect width="{width}" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#r)">
    <rect width="{left_width}" height="20" fill="#555"/>
    <rect x="{left_width}" width="{right_width}" height="20" fill="{escaped_color}"/>
    <rect width="{width}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">
    <text x="{left_width / 2:.1f}" y="15" fill="#010101" fill-opacity=".3">{escaped_left}</text>
    <text x="{left_width / 2:.1f}" y="14">{escaped_left}</text>
    <text x="{left_width + right_width / 2:.1f}" y="15" fill="#010101" fill-opacity=".3">{escaped_right}</text>
    <text x="{left_width + right_width / 2:.1f}" y="14">{escaped_right}</text>
  </g>
</svg>
"""


def _text_width(text: str) -> int:
    return max(40, 10 + len(text) * 7)


if __name__ == "__main__":
    raise SystemExit(main())
