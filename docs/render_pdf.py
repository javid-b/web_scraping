"""Render docs/SETUP_GUIDE.md into a clean A4 PDF.

Usage:
    python docs/render_pdf.py [INPUT.md] [OUTPUT.pdf]

Defaults to docs/SETUP_GUIDE.md → docs/SETUP_GUIDE.pdf.
"""

from __future__ import annotations

import sys
from pathlib import Path

import markdown2
from weasyprint import HTML, CSS


CSS_STYLES = """
@page {
    size: A4;
    margin: 18mm 16mm 18mm 16mm;
    @bottom-right { content: counter(page) " / " counter(pages); font-size: 9pt; color: #888; }
}
* { box-sizing: border-box; }
body {
    font-family: -apple-system, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.45;
    color: #1a1a1a;
}
h1 {
    font-size: 22pt;
    margin: 0 0 0.5em 0;
    color: #1a1a1a;
    border-bottom: 2px solid #1a1a1a;
    padding-bottom: 0.2em;
}
h2 {
    font-size: 14pt;
    margin: 1.4em 0 0.3em 0;
    color: #1a1a1a;
    border-bottom: 1px solid #ccc;
    padding-bottom: 0.15em;
    page-break-after: avoid;
}
h3 {
    font-size: 11.5pt;
    margin: 1.1em 0 0.3em 0;
    color: #444;
    page-break-after: avoid;
}
p, ul, ol, table { margin: 0.4em 0 0.6em 0; }
ul, ol { padding-left: 1.4em; }
li { margin: 0.15em 0; }

code {
    font-family: "SF Mono", "Consolas", "Menlo", monospace;
    font-size: 9.5pt;
    background: #f3f3f3;
    padding: 1px 4px;
    border-radius: 3px;
}
pre {
    background: #f6f8fa;
    border: 1px solid #e1e4e8;
    border-radius: 4px;
    padding: 8px 10px;
    margin: 0.6em 0;
    font-size: 9.5pt;
    overflow-x: auto;
    page-break-inside: avoid;
}
pre code {
    background: none;
    padding: 0;
    font-size: 9.5pt;
}

table {
    border-collapse: collapse;
    width: 100%;
    margin: 0.6em 0 0.9em 0;
    font-size: 9.5pt;
    page-break-inside: avoid;
}
th, td {
    border: 1px solid #d0d0d0;
    padding: 5px 8px;
    text-align: left;
    vertical-align: top;
}
th {
    background: #f3f3f3;
    font-weight: 600;
}
tr:nth-child(even) td { background: #fafafa; }

hr {
    border: none;
    border-top: 1px solid #d0d0d0;
    margin: 1.2em 0;
}

strong { color: #1a1a1a; }
em { color: #444; }

a { color: #0366d6; text-decoration: none; }
"""


def render(input_md: Path, output_pdf: Path) -> None:
    md_text = input_md.read_text(encoding="utf-8")
    html_body = markdown2.markdown(
        md_text,
        extras=["tables", "fenced-code-blocks", "code-friendly", "break-on-newline"],
    )
    html_doc = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{input_md.stem}</title></head>
<body>{html_body}</body></html>"""
    HTML(string=html_doc).write_pdf(
        output_pdf, stylesheets=[CSS(string=CSS_STYLES)]
    )
    size_kb = output_pdf.stat().st_size / 1024
    print(f"wrote {output_pdf} ({size_kb:.1f} KB)")


def main() -> int:
    here = Path(__file__).parent
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else here / "SETUP_GUIDE.md"
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else here / "SETUP_GUIDE.pdf"
    if not src.exists():
        print(f"input not found: {src}", file=sys.stderr)
        return 2
    render(src, dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
