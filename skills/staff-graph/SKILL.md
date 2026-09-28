---
name: staff-graph
description: Render the current executable staff graph locally when explicitly invoked as $staff-graph, with a compact horizontal diagram and clickable browser URL.
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
   and renders a compact left-to-right PNG, SVG, and standalone HTML view into a
   new temporary directory. It starts a local viewer bound to `127.0.0.1`, which
   stops after an hour without requests. Use the URL and paths printed by the
   script; regenerate on every invocation.
2. Open the resulting `workflow.png` with Codex's `view_image` tool. If calling
   through `functions.exec`, forward the returned image with
   `image(result.image_url)`. This supplies the image to the model; visible image
   output depends on the client.
3. Return `[Open staff graph](http://127.0.0.1:PORT/workflow.html)` using the exact
   URL printed by the renderer. Always use the HTTP URL for the browser view,
   rather than a filesystem path or a `file://` URL. In clients supporting local
   image display, also return `![Staff graph](<absolute PNG path>)`. In Codex CLI,
   use a PNG file link. Do not mistake a successful `view_image` call for proof
   that the user can see the image. Do not open another application unless the
   user requests it. The HTML view contains only the diagram and its controls.

The image shows the graph definition, not the progress of a particular run.
Rendering requires `uv`, Mermaid CLI (`mmdc`, verified with version 11.16.0), and
Chrome or Puppeteer's installed browser. The renderer uses local Chrome on macOS
when available. Report a missing dependency or rendering failure; do not present
an older diagram as current.
