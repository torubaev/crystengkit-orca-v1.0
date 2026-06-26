from __future__ import annotations

import html
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "README.md"
OUTPUT = ROOT / "docs" / "wiki.html"
WIKI_IMAGE_DIR = ROOT / "images" / "wiki"
COPYRIGHT_NOTE = "(C) Yury Torubaev. 2026"


def slugify(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\[[^\]]+\]\([^)]+\)", lambda m: m.group(0).split("](")[0][1:], text)
    text = re.sub(r"[^a-zA-Z0-9\s-]", "", text).strip().lower()
    text = re.sub(r"\s+", "-", text)
    return text or "section"


def inline_markdown(text: str) -> str:
    def render_link(match: re.Match[str]) -> str:
        label = match.group(1)
        href = html.escape(match.group(2), quote=True)
        attrs = ' target="_blank" rel="noopener noreferrer"' if href.startswith(("http://", "https://")) else ""
        return f'<a href="{href}"{attrs}>{label}</a>'

    escaped = html.escape(text)
    escaped = re.sub(
        r"`([^`]+)`",
        lambda m: f"<code>{m.group(1)}</code>",
        escaped,
    )
    escaped = re.sub(
        r"\*\*([^*]+)\*\*",
        lambda m: f"<strong>{m.group(1)}</strong>",
        escaped,
    )
    escaped = re.sub(
        r"\*([^*]+)\*",
        lambda m: f"<em>{m.group(1)}</em>",
        escaped,
    )
    escaped = re.sub(
        r"\[([^\]]+)\]\(((?:[^()]|\([^)]*\))+)\)",
        render_link,
        escaped,
    )
    escaped = re.sub(
        r"\[\^([^\]]+)\]",
        lambda m: f'<sup><a href="#ref-{slugify(m.group(1))}">{html.escape(m.group(1))}</a></sup>',
        escaped,
    )
    return escaped


def image_src(src: str) -> str:
    normalized = src.strip().replace("\\", "/")
    root_posix = ROOT.as_posix()
    if normalized.startswith(root_posix + "/"):
        normalized = normalized[len(root_posix) + 1 :]
    if re.match(r"^[A-Za-z]:/", normalized):
        raise ValueError(f"Local absolute image paths are not allowed in wiki source: {src}")
    if re.match(r"^(?:https?:|mailto:|#|/)", normalized):
        return normalized
    image_name = Path(normalized).name
    if image_name and (WIKI_IMAGE_DIR / image_name).is_file():
        normalized = f"images/wiki/{image_name}"
    return "../" + normalized


def render_html_image_row(line: str) -> str | None:
    tag_pattern = re.compile(r"<img\b([^>]*)>", re.IGNORECASE)
    tags = list(tag_pattern.finditer(line))
    if not tags or tag_pattern.sub("", line).strip():
        return None

    rendered: list[str] = []
    for tag in tags:
        attrs = dict(re.findall(r'([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*=\s*"([^"]*)"', tag.group(1)))
        src = attrs.get("src")
        if not src:
            continue
        parts = [f'src="{html.escape(image_src(src), quote=True)}"']
        alt = attrs.get("alt")
        if alt is not None:
            parts.append(f'alt="{html.escape(alt, quote=True)}"')
        title = attrs.get("title")
        if title is not None:
            parts.append(f'title="{html.escape(title, quote=True)}"')
        width = attrs.get("width")
        if width and re.match(r"^\d+(?:\.\d+)?%?$", width):
            parts.append(f'width="{html.escape(width, quote=True)}"')
        rendered.append(f"<img {' '.join(parts)}>")

    if not rendered:
        return None
    return '<figure class="image-row">' + " ".join(rendered) + "</figure>"


def collect_footnotes(lines: list[str]) -> tuple[list[str], dict[str, str]]:
    body: list[str] = []
    footnotes: dict[str, str] = {}
    current_key: str | None = None
    current_parts: list[str] = []

    def flush() -> None:
        nonlocal current_key, current_parts
        if current_key:
            footnotes[current_key] = " ".join(part.strip() for part in current_parts).strip()
        current_key = None
        current_parts = []

    for line in lines:
        match = re.match(r"^\[\^([^\]]+)\]:\s*(.*)$", line)
        if match:
            flush()
            current_key = match.group(1)
            current_parts = [match.group(2)]
            continue
        if current_key and (line.startswith("    ") or line.strip() == ""):
            if line.strip():
                current_parts.append(line.strip())
            continue
        flush()
        body.append(line)

    flush()
    return body, footnotes


def remove_source_toc(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    skipping = False

    for line in lines:
        if re.match(r"^##\s+Table of Contents\s*$", line.strip(), re.IGNORECASE):
            skipping = True
            continue
        if skipping and re.match(r"^##\s+", line.strip()):
            skipping = False
        if not skipping:
            cleaned.append(line)

    return cleaned


def markdown_to_html(lines: list[str]) -> tuple[str, list[tuple[int, str, str]]]:
    html_parts: list[str] = []
    headings: list[tuple[int, str, str]] = []
    paragraph: list[str] = []
    list_stack: list[str] = []
    ordered_counter = 0
    resume_ordered = False
    in_code = False
    code_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            html_parts.append(f"<p>{inline_markdown(' '.join(paragraph))}</p>")
            paragraph = []

    def close_lists() -> None:
        while list_stack:
            html_parts.append(f"</{list_stack.pop()}>")

    def open_list(kind: str) -> None:
        if not list_stack or list_stack[-1] != kind:
            close_lists()
            list_stack.append(kind)
            attrs = ""
            if kind == "ol" and resume_ordered and ordered_counter:
                attrs = f' start="{ordered_counter + 1}"'
            html_parts.append(f"<{kind}{attrs}>")

    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                html_parts.append(
                    '<div class="code-block"><button class="copy-code" type="button" '
                    'aria-label="Copy code" title="Copy code">Copy</button><pre><code>'
                    + html.escape("\n".join(code_lines))
                    + "</code></pre></div>"
                )
                code_lines = []
                in_code = False
            else:
                flush_paragraph()
                close_lists()
                in_code = True
            continue

        if in_code:
            code_lines.append(line)
            continue

        if not stripped:
            flush_paragraph()
            close_lists()
            continue

        image_row = render_html_image_row(stripped)
        if image_row:
            flush_paragraph()
            close_lists()
            html_parts.append(image_row)
            continue

        image = re.match(r"^!\[([^\]]*)\]\((.+?)\)(.*)$", stripped)
        if image:
            flush_paragraph()
            if not list_stack:
                close_lists()
            alt = html.escape(image.group(1), quote=True)
            src = html.escape(image_src(image.group(2)), quote=True)
            html_parts.append(f'<figure><img src="{src}" alt="{alt}"></figure>')
            tail = image.group(3).strip()
            if tail:
                paragraph.append(tail)
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            ordered_counter = 0
            resume_ordered = False
            flush_paragraph()
            close_lists()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            anchor = slugify(title)
            seen = {item[2] for item in headings}
            if anchor in seen:
                suffix = 2
                while f"{anchor}-{suffix}" in seen:
                    suffix += 1
                anchor = f"{anchor}-{suffix}"
            headings.append((level, title, anchor))
            html_parts.append(f'<h{level} id="{anchor}">{inline_markdown(title)}</h{level}>')
            continue

        ordered = re.match(r"^\d+\.\s+(.+)$", stripped)
        if ordered:
            flush_paragraph()
            open_list("ol")
            html_parts.append(f"<li>{inline_markdown(ordered.group(1))}</li>")
            ordered_counter += 1
            resume_ordered = True
            continue

        unordered = re.match(r"^[-*]\s+(.+)$", stripped)
        if unordered:
            ordered_counter = 0
            resume_ordered = False
            flush_paragraph()
            open_list("ul")
            html_parts.append(f"<li>{inline_markdown(unordered.group(1))}</li>")
            continue

        ordered_counter = 0
        resume_ordered = False
        close_lists()
        paragraph.append(stripped)

    flush_paragraph()
    close_lists()
    return "\n".join(html_parts), headings


def render_nav(headings: list[tuple[int, str, str]]) -> str:
    blocks: list[str] = []
    current: dict[str, object] | None = None

    def flush_current() -> None:
        nonlocal current
        if not current:
            return
        children = current["children"]
        child_html = "\n".join(
            f'<a class="nav-link level-3" href="#{anchor}">{inline_markdown(title)}</a>'
            for title, anchor in children
        )
        if child_html:
            open_attr = " open" if str(current["title"]).lower() == "tools" else ""
            blocks.append(
                f'<details class="nav-group"{open_attr}>'
                f'<summary><a href="#{current["anchor"]}">{inline_markdown(str(current["title"]))}</a></summary>'
                f'<div class="nav-children">{child_html}</div>'
                '</details>'
            )
        else:
            blocks.append(
                f'<a class="nav-link level-2" href="#{current["anchor"]}">'
                f'{inline_markdown(str(current["title"]))}</a>'
            )
        current = None

    for level, title, anchor in headings:
        if level == 1:
            flush_current()
        elif level == 2:
            flush_current()
            current = {"title": title, "anchor": anchor, "children": []}
        elif level == 3 and current:
            current["children"].append((title, anchor))

    flush_current()
    return "\n".join(blocks)


def render_footnotes(footnotes: dict[str, str]) -> str:
    if not footnotes:
        return ""
    items = []
    for key, text in footnotes.items():
        items.append(
            f'<li id="ref-{slugify(key)}"><span class="ref-key">[{html.escape(key)}]</span> '
            f"{inline_markdown(text)}</li>"
        )
    return '<section class="references"><h2 id="references">References</h2><ol>' + "\n".join(items) + "</ol></section>"


def build_page(article: str, nav: str, refs: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>CrystEngKit Documentation</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f7fa;
      --paper: #ffffff;
      --ink: #1e2933;
      --muted: #607080;
      --line: #d9e1ea;
      --accent: #116466;
      --accent-soft: #d9f0ee;
      --code: #eef2f6;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: "Segoe UI", Arial, sans-serif;
      line-height: 1.6;
    }}
    .layout {{
      display: grid;
      grid-template-columns: 280px minmax(0, 1fr);
      min-height: 100vh;
    }}
    aside {{
      position: sticky;
      top: 0;
      height: 100vh;
      overflow: auto;
      padding: 24px 18px;
      background: #102a43;
      color: #f6fbff;
      border-right: 1px solid #0b1f33;
    }}
    aside h1 {{
      margin: 0 0 6px;
      font-size: 22px;
      line-height: 1.2;
      color: #d9f0ee;
    }}
    aside p {{
      margin: 0 0 18px;
      color: #bdd4e7;
      font-size: 14px;
    }}
    .nav-link {{
      display: block;
      color: #e7f2fb;
      text-decoration: none;
      padding: 7px 8px;
      border-radius: 6px;
      font-size: 14px;
    }}
    .nav-link:hover {{
      background: rgba(255, 255, 255, 0.12);
    }}
    .level-1 {{ font-weight: 700; }}
    .level-2 {{ margin-left: 8px; }}
    .level-3 {{ margin-left: 22px; font-size: 13px; color: #cfe0ee; }}
    .nav-group {{
      margin: 2px 0;
      border-radius: 6px;
    }}
    .nav-group summary {{
      list-style: none;
      cursor: pointer;
      border-radius: 6px;
      padding: 7px 8px;
      color: #e7f2fb;
      font-size: 14px;
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .nav-group summary::-webkit-details-marker {{
      display: none;
    }}
    .nav-group summary::before {{
      content: ">";
      color: #9fc1da;
      font-size: 12px;
      transition: transform 0.15s ease;
    }}
    .nav-group[open] summary::before {{
      transform: rotate(90deg);
    }}
    .nav-group summary:hover {{
      background: rgba(255, 255, 255, 0.12);
    }}
    .nav-group summary a {{
      color: #e7f2fb;
      text-decoration: none;
      flex: 1;
    }}
    .nav-children {{
      padding: 2px 0 6px;
    }}
    main {{
      max-width: 1020px;
      width: 100%;
      margin: 0 auto;
      padding: 34px 34px 70px;
    }}
    article, .references {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 34px;
      box-shadow: 0 10px 28px rgba(16, 42, 67, 0.08);
    }}
    .references {{ margin-top: 22px; }}
    h1, h2, h3, h4 {{
      line-height: 1.25;
      color: #102a43;
    }}
    article > h1:first-child {{
      margin-top: 0;
      font-size: 34px;
    }}
    h2 {{
      margin-top: 34px;
      padding-top: 18px;
      border-top: 1px solid var(--line);
    }}
    h3 {{ margin-top: 24px; color: var(--accent); }}
    a {{ color: #0f6f74; }}
    code {{
      background: var(--code);
      border-radius: 4px;
      padding: 2px 5px;
      font-family: Consolas, "Courier New", monospace;
      font-size: 0.94em;
    }}
    .code-block {{
      position: relative;
      margin: 16px 0;
    }}
    .copy-code {{
      position: absolute;
      top: 9px;
      right: 9px;
      border: 1px solid #c7d2df;
      border-radius: 5px;
      background: #ffffff;
      color: #243447;
      font-size: 12px;
      font-weight: 600;
      padding: 4px 8px;
      cursor: pointer;
    }}
    .copy-code:hover {{
      background: #e3edf7;
    }}
    pre {{
      background: #eef2f6;
      color: #243447;
      border: 1px solid #d5dde6;
      padding: 16px;
      padding-right: 78px;
      border-radius: 8px;
      overflow: auto;
    }}
    pre code {{
      background: transparent;
      padding: 0;
      color: inherit;
    }}
    ul, ol {{ padding-left: 24px; }}
    li {{ margin: 5px 0; }}
    figure {{
      margin: 18px 0 22px;
    }}
    .image-row {{
      display: flex;
      flex-wrap: wrap;
      align-items: flex-start;
      gap: 12px;
    }}
    figure img {{
      display: block;
      max-width: 100%;
      height: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #ffffff;
    }}
    sup a {{ text-decoration: none; }}
    .references ol {{ padding-left: 24px; }}
    .ref-key {{
      font-weight: 700;
      color: var(--accent);
    }}
    .toolbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 16px;
      color: var(--muted);
      font-size: 14px;
    }}
    .badge {{
      display: inline-block;
      padding: 5px 9px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: #0d4d50;
      font-weight: 600;
    }}
    .copyright {{
      margin-top: 18px;
      color: var(--muted);
      font-size: 13px;
    }}
    @media (max-width: 860px) {{
      .layout {{ display: block; }}
      aside {{
        position: relative;
        height: auto;
        max-height: 330px;
      }}
      main {{ padding: 18px; }}
      article, .references {{ padding: 22px; }}
      article > h1:first-child {{ font-size: 27px; }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    <aside>
      <h1>CrystEngKit Documentation</h1>
      <nav>
        {nav}
        <a class="nav-link level-2" href="#references">References</a>
      </nav>
    </aside>
    <main>
      <article>
        {article}
      </article>
      {refs}
      <footer class="copyright">{html.escape(COPYRIGHT_NOTE)}</footer>
    </main>
  </div>
  <script>
    function revealHashTarget() {{
      const params = new URLSearchParams(location.search);
      const rawId = location.hash
        ? decodeURIComponent(location.hash.slice(1))
        : params.get("section");
      if (!rawId) return;
      const target = document.getElementById(rawId);
      if (!target) return;
      const navLinks = Array.from(document.querySelectorAll("nav a"));
      const navLink = navLinks.find((link) => link.getAttribute("href") === `#${{rawId}}`);
      if (navLink) {{
        const group = navLink.closest("details");
        if (group) group.open = true;
      }}
      const y = target.getBoundingClientRect().top + window.pageYOffset - 8;
      window.scrollTo({{ top: Math.max(0, y), behavior: "auto" }});
    }}

    function settleHashTarget() {{
      revealHashTarget();
      [50, 150, 350, 800].forEach((delay) => setTimeout(revealHashTarget, delay));
    }}

    document.querySelectorAll(".copy-code").forEach((button) => {{
      button.addEventListener("click", async () => {{
        const code = button.parentElement.querySelector("code").innerText;
        try {{
          await navigator.clipboard.writeText(code);
          button.textContent = "Copied";
          setTimeout(() => button.textContent = "Copy", 1200);
        }} catch (error) {{
          const area = document.createElement("textarea");
          area.value = code;
          document.body.appendChild(area);
          area.select();
          document.execCommand("copy");
          area.remove();
          button.textContent = "Copied";
          setTimeout(() => button.textContent = "Copy", 1200);
        }}
      }});
    }});
    window.addEventListener("hashchange", settleHashTarget);
    window.addEventListener("DOMContentLoaded", settleHashTarget);
    window.addEventListener("load", settleHashTarget);
  </script>
</body>
</html>
"""


def main() -> None:
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    body, footnotes = collect_footnotes(lines)
    body = remove_source_toc(body)
    if footnotes:
        body = [line for line in body if not re.match(r"^##\s+References\s*$", line.strip(), re.IGNORECASE)]
    article, headings = markdown_to_html(body)
    page = build_page(article, render_nav(headings), render_footnotes(footnotes))
    OUTPUT.write_text(page, encoding="utf-8")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
