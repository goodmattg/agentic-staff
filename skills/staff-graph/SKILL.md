---
name: staff-graph
description: Render the current executable staff graph locally when explicitly invoked as $staff-graph, with an inline image in supported clients and file links in Codex CLI.
---

# Staff graph

Render the current graph structure without starting a staff run or invoking agents.

## Output

Run silently: omit skill announcements, preambles, progress updates, and success
summaries unless higher-priority host instructions require them. Return only the
finished visual or links. If rendering fails, give one concise error.
Host-controlled tool activity may still appear; this skill cannot hide that UI.

## Render

1. Run `scripts/render` relative to this skill directory. It imports `GRAPH` from
   the installed repository, generates Mermaid from its actual nodes and edges,
   and renders a PNG, SVG, and standalone HTML view into a new temporary directory.
   Use the paths printed by the script; regenerate on every invocation.
2. Open the resulting `workflow.png` with Codex's `view_image` tool. If calling
   through `functions.exec`, forward the returned image with
   `image(result.image_url)`. This supplies the image to the model; visible image
   output depends on the client.
3. In clients supporting local image display, return
   `![Staff graph](<absolute PNG path>)` and a short link to the generated HTML
   view for zooming. In Codex CLI, return concise PNG and HTML file links instead
   of promising an inline preview. Do not mistake a successful `view_image` call
   for proof that the user can see the image. Do not open another application
   unless the user requests it.

The image shows the graph definition, not the progress of a particular run.
Rendering requires `uv`, Mermaid CLI (`mmdc`, verified with version 11.16.0), and
Chrome or Puppeteer's installed browser. The renderer uses local Chrome on macOS
when available. Report a missing dependency or rendering failure; do not present
an older diagram as current.
