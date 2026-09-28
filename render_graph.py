"""Render the executable staff graph to Mermaid, PNG, SVG, and a browser view."""

import argparse
import json
import os
import shutil
import subprocess
import sys
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
  body { margin: 0; background: #fafafa; color: #161616; font: 16px 'Times New Roman', serif;
    height: 100dvh; display: flex; flex-direction: column; }
  header { position: sticky; top: 0; z-index: 1; background: #fff; padding: 8px 12px;
    border-bottom: 1px solid #ddd; flex: none; }
  nav { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  button, a { font: inherit; }
  button { padding: 6px 12px; background: white; border: 1px solid #aaa; border-radius: 4px; }
  button:hover { background: #eee; }
  a { color: #3333cc; margin-left: 8px; }
  #canvas { padding: 12px; overflow: auto; flex: 1; min-height: 0; }
  #canvas svg { display: block; max-width: none !important; margin: 0 auto; }
  output { min-width: 4em; text-align: center; }
</style>
<header>
  <nav aria-label="Diagram controls">
    <button id="out" aria-label="Zoom out">−</button>
    <output id="zoom" aria-live="polite">100%</output>
    <button id="in" aria-label="Zoom in">+</button>
    <button id="fit">Fit</button>
    <button id="reset">100%</button>
    <a href="workflow.svg" download>Download SVG</a>
  </nav>
</header>
<main id="canvas" aria-label="Staff workflow diagram">{{SVG}}</main>
<script>
  const svg = document.querySelector('#canvas svg');
  const bounds = svg.viewBox.baseVal;
  const width = bounds.width, height = bounds.height;
  let scale = 1;
  function setScale(value) {
    scale = Math.min(3, Math.max(.1, value));
    svg.style.width = `${width * scale}px`;
    svg.style.height = `${height * scale}px`;
    document.getElementById('zoom').textContent = `${Math.round(scale * 100)}%`;
  }
  document.getElementById('in').onclick = () => setScale(scale * 1.2);
  document.getElementById('out').onclick = () => setScale(scale / 1.2);
  document.getElementById('reset').onclick = () => setScale(1);
  function fit() {
    const canvas = document.getElementById('canvas');
    setScale(Math.min(1, (canvas.clientWidth - 24) / width, (canvas.clientHeight - 24) / height));
  }
  document.getElementById('fit').onclick = fit;
  window.addEventListener('resize', fit);
  fit();
</script>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--open", action="store_true", help="Open the generated browser view")
    parser.add_argument("--serve", action="store_true", help="Print a clickable localhost URL")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    renderer = shutil.which("mmdc")
    if not renderer:
        parser.error("Install Mermaid CLI: npm install -g @mermaid-js/mermaid-cli@11.16.0")
    output = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else Path(tempfile.mkdtemp(prefix="staff-graph-"))
    )
    output.mkdir(parents=True, exist_ok=True)
    diagram = GRAPH.render(direction="LR")
    (output / "workflow.mmd").write_text(diagram)
    env = os.environ.copy()
    chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if chrome.exists():
        env.setdefault("PUPPETEER_EXECUTABLE_PATH", str(chrome))
    with tempfile.TemporaryDirectory(prefix="staff-diagram-") as temporary:
        config = Path(temporary) / "mermaid.json"
        config.write_text(
            json.dumps(
                {
                    "themeVariables": {"fontFamily": "Times New Roman", "fontSize": "16px"},
                    "state": {"nodeSpacing": 16, "rankSpacing": 20, "padding": 8},
                }
            )
        )
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
    url = page.as_uri()
    if args.serve or args.open:
        with (output / "viewer.log").open("a") as log:
            viewer = subprocess.Popen(
                [sys.executable, str(ROOT / "serve_graph.py"), str(output)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=log,
                text=True,
                start_new_session=True,
            )
        url = viewer.stdout.readline().strip()
        viewer.stdout.close()
        if not url:
            parser.error(f"Viewer failed to start; see {output / 'viewer.log'}")
        print(url)
    print(page)
    print(output / "workflow.png")
    if args.open:
        webbrowser.open(url)


if __name__ == "__main__":
    main()
