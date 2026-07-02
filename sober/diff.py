"""Graph diff engine for SOBER — PURE module (no cognee import).

Compares two snapshot dicts (``{"nodes": [...], "edges": [...]}``, as produced
by :func:`sober.snapshot.load_snapshot`) and renders the result as a
GitHub-PR-comment-ready markdown block. This is what powers ``brain diff`` and
the PR bot's "here's what changed in the brain" comment.

Identity rules (frozen by CONTRACT.md, matching real cognee exports):
  * **Node** identity: the stable ``id`` (a UUID5 derived from content) when
    present, else the ``(name, type)`` pair (Entity/EntityType nodes).
  * **Edge** identity: the triple ``(source, target, relationship_name)``.

Changes are tracked on three fields that carry semantic weight in Cognee:
``text``, ``feedback_weight``, and ``importance_weight``.
"""

from __future__ import annotations

from typing import Any, Hashable

__all__ = ["diff_graphs", "render_markdown"]

# Fields whose per-node changes we surface in the diff.
TRACKED_FIELDS: tuple[str, ...] = ("text", "feedback_weight", "importance_weight")


# --------------------------------------------------------------------------- #
# Identity helpers
# --------------------------------------------------------------------------- #
def _node_key(node: dict) -> Hashable:
    """Identity key for a node: ``id`` if present, else ``(name, type)``."""
    node_id = node.get("id")
    if node_id:
        return ("id", node_id)
    return ("nt", node.get("name"), node.get("type"))


def _edge_key(edge: dict) -> Hashable:
    """Identity key for an edge: ``(source, target, relationship_name)``."""
    return (
        edge.get("source"),
        edge.get("target"),
        edge.get("relationship_name"),
    )


def _index(items: list[dict], key_fn) -> dict[Hashable, dict]:
    """Index a list of dicts by ``key_fn``.

    On duplicate keys the last occurrence wins — matching cognee's own "latest
    write" semantics for a re-ingested node/edge.
    """
    out: dict[Hashable, dict] = {}
    for item in items:
        if isinstance(item, dict):
            out[key_fn(item)] = item
    return out


def _node_label(node: dict) -> str:
    """Short human label for a node in rendered output."""
    name = (node.get("name") or "").strip()
    ntype = node.get("type") or "?"
    if name:
        return f"{name} ({ntype})"
    # Nameless nodes (chunks/summaries): fall back to a text/ id preview.
    text = (node.get("text") or "").strip().replace("\n", " ")
    if text:
        preview = text[:60] + ("…" if len(text) > 60 else "")
        return f"{ntype}: {preview}"
    node_id = node.get("id")
    return f"{ntype} [{str(node_id)[:8]}]" if node_id else ntype


def _edge_label(edge: dict) -> str:
    """Short human label for an edge in rendered output."""
    src = str(edge.get("source", "?"))[:8]
    tgt = str(edge.get("target", "?"))[:8]
    rel = edge.get("relationship_name", "?")
    return f"{src} --[{rel}]--> {tgt}"


# --------------------------------------------------------------------------- #
# Core diff
# --------------------------------------------------------------------------- #
def diff_graphs(a: dict, b: dict) -> dict:
    """Diff snapshot ``a`` (before) against snapshot ``b`` (after).

    Args:
        a: the *previous* snapshot dict (``{"nodes":[...],"edges":[...]}``).
        b: the *new* snapshot dict.

    Returns a dict::

        {
          "nodes_added":   [<node>, ...],   # in b, not in a
          "nodes_removed": [<node>, ...],   # in a, not in b
          "nodes_changed": [
              {"id": <key-repr>, "label": str, "field": str,
               "from": <old>, "to": <new>}, ...
          ],
          "edges_added":   [<edge>, ...],
          "edges_removed": [<edge>, ...],
          "summary": {"nodes_added": n, "nodes_removed": n, "nodes_changed": n,
                      "edges_added": n, "edges_removed": n},
        }

    A node present in both snapshots contributes one ``nodes_changed`` entry per
    tracked field (:data:`TRACKED_FIELDS`) whose value differs.
    """
    a = a or {}
    b = b or {}

    a_nodes = _index(a.get("nodes", []) or [], _node_key)
    b_nodes = _index(b.get("nodes", []) or [], _node_key)
    a_edges = _index(a.get("edges", []) or [], _edge_key)
    b_edges = _index(b.get("edges", []) or [], _edge_key)

    nodes_added = [b_nodes[k] for k in b_nodes.keys() - a_nodes.keys()]
    nodes_removed = [a_nodes[k] for k in a_nodes.keys() - b_nodes.keys()]
    edges_added = [b_edges[k] for k in b_edges.keys() - a_edges.keys()]
    edges_removed = [a_edges[k] for k in a_edges.keys() - b_edges.keys()]

    nodes_changed: list[dict] = []
    for key in a_nodes.keys() & b_nodes.keys():
        before, after = a_nodes[key], b_nodes[key]
        label = _node_label(after)
        for field in TRACKED_FIELDS:
            old: Any = before.get(field)
            new: Any = after.get(field)
            if old != new:
                nodes_changed.append(
                    {
                        "id": _key_repr(key),
                        "label": label,
                        "field": field,
                        "from": old,
                        "to": new,
                    }
                )

    summary = {
        "nodes_added": len(nodes_added),
        "nodes_removed": len(nodes_removed),
        "nodes_changed": len(nodes_changed),
        "edges_added": len(edges_added),
        "edges_removed": len(edges_removed),
    }

    return {
        "nodes_added": nodes_added,
        "nodes_removed": nodes_removed,
        "nodes_changed": nodes_changed,
        "edges_added": edges_added,
        "edges_removed": edges_removed,
        "summary": summary,
    }


def _key_repr(key: Hashable) -> str:
    """Render an identity key tuple back to a compact string for the report."""
    if isinstance(key, tuple):
        if key and key[0] == "id":
            return str(key[1])
        if key and key[0] == "nt":
            name, ntype = key[1], key[2]
            return f"{name}/{ntype}"
    return str(key)


# --------------------------------------------------------------------------- #
# Markdown rendering
# --------------------------------------------------------------------------- #
def _fmt_value(value: Any, limit: int = 80) -> str:
    """Format a field value for a markdown table cell (trim + escape pipes)."""
    if value is None:
        return "_none_"
    text = str(value).replace("\n", " ").replace("|", "\\|").strip()
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return f"`{text}`" if text else "_empty_"


def _details_block(summary: str, lines: list[str], emoji: str) -> str:
    """Render a collapsible ``<details>`` section (empty -> a one-liner)."""
    count = len(lines)
    header = f"{emoji} {summary} ({count})"
    if count == 0:
        return f"- {header}"
    body = "\n".join(f"- {line}" for line in lines)
    return (
        f"<details>\n<summary>{header}</summary>\n\n{body}\n\n</details>"
    )


def render_markdown(diff: dict, title: str = "Brain diff") -> str:
    """Render a diff dict as a GitHub-PR-comment-ready markdown string.

    Produces: a title, a summary table of the five change counts, a one-line
    verdict banner, and collapsible ``<details>`` lists for each change class.
    Uses tasteful emoji: 🟢 added / 🔴 removed / ✏️ changed.
    """
    s = diff.get("summary", {}) if isinstance(diff, dict) else {}
    na = s.get("nodes_added", 0)
    nr = s.get("nodes_removed", 0)
    nc = s.get("nodes_changed", 0)
    ea = s.get("edges_added", 0)
    er = s.get("edges_removed", 0)
    total = na + nr + nc + ea + er

    out: list[str] = []
    out.append(f"## 🧠 {title}")
    out.append("")

    if total == 0:
        out.append("✅ **No changes** — the brain is identical between snapshots.")
        out.append("")
        return "\n".join(out)

    out.append(f"**{total}** change(s) detected between snapshots.")
    out.append("")

    # Summary table.
    out.append("| Change | 🟢 Added | 🔴 Removed | ✏️ Changed |")
    out.append("| --- | ---: | ---: | ---: |")
    out.append(f"| **Nodes** | {na} | {nr} | {nc} |")
    out.append(f"| **Edges** | {ea} | {er} | — |")
    out.append("")

    # Node details.
    added_node_lines = [_node_label(n) for n in diff.get("nodes_added", [])]
    removed_node_lines = [_node_label(n) for n in diff.get("nodes_removed", [])]
    changed_lines = [
        f"**{c.get('label', c.get('id'))}** · `{c['field']}`: "
        f"{_fmt_value(c['from'])} → {_fmt_value(c['to'])}"
        for c in diff.get("nodes_changed", [])
    ]

    out.append("### Nodes")
    out.append(_details_block("Added nodes", added_node_lines, "🟢"))
    out.append(_details_block("Removed nodes", removed_node_lines, "🔴"))
    out.append(_details_block("Changed nodes", changed_lines, "✏️"))
    out.append("")

    # Edge details.
    added_edge_lines = [_edge_label(e) for e in diff.get("edges_added", [])]
    removed_edge_lines = [_edge_label(e) for e in diff.get("edges_removed", [])]

    out.append("### Edges")
    out.append(_details_block("Added edges", added_edge_lines, "🟢"))
    out.append(_details_block("Removed edges", removed_edge_lines, "🔴"))
    out.append("")

    return "\n".join(out)
