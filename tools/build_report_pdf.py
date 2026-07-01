from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT / "submission_package" / "technical_report.md"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "submission_bundle" / "reports"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build technical report PDF when local tools are available.")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="Markdown source file.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for PDF/HTML outputs.")
    args = parser.parse_args()

    source = _resolve_path(args.source)
    output_dir = _resolve_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_stem = source.stem
    pdf_path = output_dir / f"{output_stem}.pdf"
    html_path = output_dir / f"{output_stem}.html"
    status_path = output_dir / "technical_report_build_status.json"

    status: dict[str, Any] = {
        "source": str(source),
        "pdf_path": str(pdf_path),
        "html_path": str(html_path),
        "pdf_built": False,
        "pdf_generated": False,
        "html_built": False,
        "html_fallback_path": str(html_path),
        "manual_export_required": False,
        "manual_export_steps": [],
        "method": None,
        "warnings": [],
    }
    try:
        if not source.exists():
            raise BuildError(f"Missing report source: {source}")
        markdown = source.read_text(encoding="utf-8")
        html_text = _markdown_to_html(markdown)
        html_path.write_text(html_text, encoding="utf-8")
        status["html_built"] = True

        if _try_pandoc(source, pdf_path, status):
            status["pdf_built"] = True
            status["method"] = "pandoc"
        elif _try_weasyprint(html_path, pdf_path, status):
            status["pdf_built"] = True
            status["method"] = "weasyprint"
        elif _try_wkhtmltopdf(html_path, pdf_path, status):
            status["pdf_built"] = True
            status["method"] = "wkhtmltopdf"
        elif _try_playwright(html_path, pdf_path, status):
            status["pdf_built"] = True
            status["method"] = "playwright"
        elif _try_builtin_pdf(markdown, pdf_path, status):
            status["pdf_built"] = True
            status["method"] = "builtin_simple_pdf"
        else:
            status["manual_export_required"] = True
            status["manual_export_steps"] = [
                f"Open {html_path} in a browser.",
                "Use Print.",
                "Choose Save as PDF.",
                f"Save the file as {pdf_path}.",
                "Re-run python tools/build_report_pdf.py if a local PDF backend is later installed.",
            ]
            status["warnings"].append(
                "No local PDF backend was available. Generated HTML instead. "
                "Install pandoc, WeasyPrint, wkhtmltopdf, or Playwright Chromium to build PDF automatically."
            )

        if status["pdf_built"]:
            status["pdf_generated"] = True
            print(f"Technical report PDF written to {pdf_path}")
        else:
            print(f"Technical report HTML written to {html_path}")
            print("PDF not built: no available local PDF backend.")
        _refresh_bundle_checksums(output_dir)
        return 0
    except BuildError as exc:
        status["error"] = str(exc)
        print(f"Report build failed: {exc}")
        return 1
    finally:
        status_path.parent.mkdir(parents=True, exist_ok=True)
        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Report build status written to {status_path}")


class BuildError(Exception):
    pass


def _resolve_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _try_pandoc(source: Path, pdf_path: Path, status: dict[str, Any]) -> bool:
    if not shutil.which("pandoc"):
        status["warnings"].append("pandoc not found.")
        return False
    command = ["pandoc", str(source), "-o", str(pdf_path)]
    return _run_pdf_command(command, status)


def _try_weasyprint(html_path: Path, pdf_path: Path, status: dict[str, Any]) -> bool:
    try:
        from weasyprint import HTML  # type: ignore
    except Exception:
        status["warnings"].append("WeasyPrint not available.")
        return False
    try:
        HTML(filename=str(html_path)).write_pdf(str(pdf_path))
        return pdf_path.exists() and pdf_path.stat().st_size > 0
    except Exception as exc:
        status["warnings"].append(f"WeasyPrint failed: {exc}")
        return False


def _try_wkhtmltopdf(html_path: Path, pdf_path: Path, status: dict[str, Any]) -> bool:
    executable = shutil.which("wkhtmltopdf")
    if not executable:
        status["warnings"].append("wkhtmltopdf not found.")
        return False
    command = [executable, str(html_path), str(pdf_path)]
    return _run_pdf_command(command, status)


def _try_playwright(html_path: Path, pdf_path: Path, status: dict[str, Any]) -> bool:
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception:
        status["warnings"].append("Playwright not available.")
        return False
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            page.goto(html_path.as_uri(), wait_until="networkidle")
            page.pdf(path=str(pdf_path), format="A4", print_background=True)
            browser.close()
        return pdf_path.exists() and pdf_path.stat().st_size > 0
    except Exception as exc:
        message = str(exc)
        if "Executable doesn't exist" in message or "playwright install" in message:
            status["warnings"].append("Playwright is installed, but Chromium is missing. Run playwright install to enable automatic PDF export.")
        else:
            status["warnings"].append(f"Playwright PDF export failed: {_tail(message, 500)}")
        return False


def _run_pdf_command(command: list[str], status: dict[str, Any]) -> bool:
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    status.setdefault("commands", []).append(
        {
            "command": command,
            "returncode": completed.returncode,
            "stdout_tail": _tail(completed.stdout),
            "stderr_tail": _tail(completed.stderr),
        }
    )
    return completed.returncode == 0


def _try_builtin_pdf(markdown: str, pdf_path: Path, status: dict[str, Any]) -> bool:
    try:
        _write_simple_pdf(markdown, pdf_path)
        status["warnings"].append(
            "Used built-in simple PDF fallback because no full PDF backend was available. "
            "HTML remains the layout-fidelity report artifact."
        )
        return pdf_path.exists() and pdf_path.stat().st_size > 0
    except Exception as exc:
        status["warnings"].append(f"Built-in simple PDF fallback failed: {exc}")
        return False


def _write_simple_pdf(markdown: str, pdf_path: Path) -> None:
    pages = _paginate_pdf_lines(_markdown_to_plain_lines(markdown))
    objects: list[bytes] = []

    def add_object(payload: bytes) -> int:
        objects.append(payload)
        return len(objects)

    catalog_id = add_object(b"<< /Type /Catalog /Pages 2 0 R >>")
    pages_id = add_object(b"")
    font_id = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids: list[int] = []
    for page_lines in pages:
        stream = _pdf_text_stream(page_lines)
        content_id = add_object(
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream"
        )
        page_id = add_object(
            (
                f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 595 842] "
                f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
            ).encode("ascii")
        )
        page_ids.append(page_id)
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[pages_id - 1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii")
    _write_pdf_objects(pdf_path, objects, catalog_id)


def _markdown_to_plain_lines(markdown: str) -> list[str]:
    lines: list[str] = []
    in_code = False
    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if not in_code:
            line = line.lstrip("#").strip() if line.startswith("#") else line
            if line.startswith("- "):
                line = "* " + line[2:]
        lines.extend(_wrap_pdf_line(line, width=92))
    return lines


def _wrap_pdf_line(line: str, *, width: int) -> list[str]:
    if not line:
        return [""]
    chunks: list[str] = []
    current = ""
    for word in line.split():
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= width:
            current += " " + word
        else:
            chunks.append(current)
            current = word
    if current:
        chunks.append(current)
    return chunks or [""]


def _paginate_pdf_lines(lines: list[str]) -> list[list[str]]:
    pages: list[list[str]] = []
    page: list[str] = []
    max_lines = 48
    for line in lines:
        if len(page) >= max_lines:
            pages.append(page)
            page = []
        page.append(line)
    if page:
        pages.append(page)
    return pages or [["Technical Report"]]


def _pdf_text_stream(lines: list[str]) -> bytes:
    stream_lines = ["BT", "/F1 10 Tf", "50 790 Td", "14 TL"]
    for index, line in enumerate(lines):
        if index:
            stream_lines.append("T*")
        stream_lines.append(f"({_pdf_escape_text(line)}) Tj")
    stream_lines.append("ET")
    return "\n".join(stream_lines).encode("ascii", errors="replace")


def _pdf_escape_text(value: str) -> str:
    safe = value.encode("latin-1", errors="replace").decode("latin-1")
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _write_pdf_objects(pdf_path: Path, objects: list[bytes], catalog_id: int) -> None:
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, payload in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(payload)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    pdf_path.write_bytes(bytes(output))


def _markdown_to_html(markdown: str) -> str:
    body = "\n".join(_markdown_lines_to_html(markdown.splitlines()))
    title = _html_title(markdown)
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; line-height: 1.55; margin: 48px; max-width: 920px; }}
    h1, h2, h3 {{ color: #1f2937; }}
    code {{ background: #f3f4f6; padding: 2px 4px; border-radius: 4px; }}
    pre {{ background: #f3f4f6; padding: 12px; overflow-x: auto; }}
    li {{ margin: 4px 0; }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""


def _html_title(markdown: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip() or "Technical Report"
    return "Technical Report"


def _markdown_lines_to_html(lines: list[str]) -> list[str]:
    html_lines: list[str] = []
    in_list = False
    in_code = False
    code_lines: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            html_lines.append(f"<p>{html.escape(' '.join(paragraph))}</p>")
            paragraph = []

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            html_lines.append("</ul>")
            in_list = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_paragraph()
            close_list()
            if in_code:
                html_lines.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
                code_lines = []
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not stripped:
            flush_paragraph()
            close_list()
            continue
        if stripped.startswith("# "):
            flush_paragraph()
            close_list()
            html_lines.append(f"<h1>{html.escape(stripped[2:])}</h1>")
            continue
        if stripped.startswith("## "):
            flush_paragraph()
            close_list()
            html_lines.append(f"<h2>{html.escape(stripped[3:])}</h2>")
            continue
        if stripped.startswith("### "):
            flush_paragraph()
            close_list()
            html_lines.append(f"<h3>{html.escape(stripped[4:])}</h3>")
            continue
        if stripped.startswith("- "):
            flush_paragraph()
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{html.escape(stripped[2:])}</li>")
            continue
        paragraph.append(stripped)

    flush_paragraph()
    close_list()
    if in_code:
        html_lines.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
    return html_lines


def _tail(text: str, max_chars: int = 2000) -> str:
    return text[-max_chars:]


def _refresh_bundle_checksums(output_dir: Path) -> None:
    bundle_root = output_dir.parent
    if bundle_root.name != "submission_bundle":
        return
    checksums_dir = bundle_root / "checksums"
    if not checksums_dir.exists():
        return
    entries = []
    for path in sorted(bundle_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(bundle_root).as_posix()
        if rel == "checksums/SHA256SUMS.txt":
            continue
        entries.append(f"{_sha256(path)}  {rel}")
    (checksums_dir / "SHA256SUMS.txt").write_text("\n".join(entries) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
