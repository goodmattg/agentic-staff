"""Render the executable staff graph to Mermaid, PNG, SVG, and a browser view."""

import argparse
import os
import shutil
import subprocess
import tempfile
import webbrowser
from pathlib import Path

from staff_graph import GRAPH

ROOT = Path(__file__).resolve().parent
PAGE = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Staff workflow</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; background: #fafafa; color: #161616; font: 16px 'Times New Roman', serif; }
  header { position: sticky; top: 0; z-index: 1; background: #fff; padding: 16px 24px;
    border-bottom: 1px solid #ddd; }
  h1 { font-size: 16px; margin: 0 0 8px; }
  p { margin: 8px 0; max-width: 80ch; line-height: 1.4; }
  nav { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  button, a { font: inherit; }
  button { padding: 6px 12px; background: white; border: 1px solid #aaa; border-radius: 4px; }
  button:hover { background: #eee; }
  a { color: #3333cc; margin-left: 8px; }
  #canvas { padding: 24px; overflow: auto; }
  #canvas svg { display: block; max-width: none !important; margin: 0 auto; }
  output { min-width: 4em; text-align: center; }
</style>
<header>
  <h1>Staff workflow</h1>
  <nav aria-label="Diagram controls">
    <button id="out" aria-label="Zoom out">−</button>
    <output id="zoom" aria-live="polite">100%</output>
    <button id="in" aria-label="Zoom in">+</button>
    <button id="fit">Fit width</button>
    <button id="reset">100%</button>
    <a href="workflow.svg" download>Download SVG</a>
  </nav>
  <p>Generated from the executable Python graph. <b>AwaitHost</b> pauses for a native agent
  action; <b>Resume</b> continues its saved phase. <b>Answer</b> and <b>Done</b> finish the
  invocation. Ordinary messages bypass the graph.</p>
</header>
<main id="canvas" aria-label="Staff workflow diagram">{{SVG}}</main>
<script>
  const svg = document.querySelector('#canvas svg');
  const bounds = svg.viewBox.baseVal;
  const width = bounds.width, height = bounds.height;
  let scale = 1;
  function setScale(value) {
    scale = Math.min(3, Math.max(.3, value));
    svg.style.width = `${width * scale}px`;
    svg.style.height = `${height * scale}px`;
    document.getElementById('zoom').textContent = `${Math.round(scale * 100)}%`;
  }
  document.getElementById('in').onclick = () => setScale(scale * 1.2);
  document.getElementById('out').onclick = () => setScale(scale / 1.2);
  document.getElementById('reset').onclick = () => setScale(1);
  document.getElementById('fit').onclick = () => setScale((window.innerWidth - 48) / width);
  setScale(Math.min(1, (window.innerWidth - 48) / width));
</script>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--open", action="store_true", help="Open the generated browser view")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs")
    args = parser.parse_args()
    renderer = shutil.which("mmdc")
    if not renderer:
        parser.error("Install Mermaid CLI: npm install -g @mermaid-js/mermaid-cli@11.16.0")
    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    diagram = GRAPH.render(title="Staff workflow")
    (output / "workflow.mmd").write_text(diagram)
    env = os.environ.copy()
    chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if chrome.exists():
        env.setdefault("PUPPETEER_EXECUTABLE_PATH", str(chrome))
    with tempfile.TemporaryDirectory(prefix="staff-diagram-") as temporary:
        config = Path(temporary) / "mermaid.json"
        config.write_text('{"themeVariables":{"fontFamily":"Times New Roman","fontSize":"16px"}}')
        for extension in ("svg", "png"):
            subprocess.run(
                [
                    renderer,
                    "-i",
                    str(output / "workflow.mmd"),
                    "-o",
                    str(output / f"workflow.{extension}"),
                    "-t",
                    "neutral",
                    "-w",
                    "1800",
                    "-s",
                    "2",
                    "-b",
                    "white",
                    "-c",
                    str(config),
                ],
                env=env,
                check=True,
                stdout=subprocess.DEVNULL,
            )
    page = output / "workflow.html"
    page.write_text(PAGE.replace("{{SVG}}", (output / "workflow.svg").read_text()))
    print(page)
    print(output / "workflow.png")
    if args.open:
        webbrowser.open(page.as_uri())


if __name__ == "__main__":
    main()
