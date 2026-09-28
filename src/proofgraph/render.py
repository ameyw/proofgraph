"""Readable tree views of a DAG; shared subgraphs are expanded only once."""

from __future__ import annotations

from .model import Node


def _single_line(text: str) -> str:
    return text.replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")


def _label(node: Node) -> str:
    name = f"{_single_line(node.name)} = " if node.name is not None else ""
    label = f"{name}{node.value!r} [{node.operation or node.kind}]"
    if node.evidence is not None:
        evidence = node.evidence
        location = _single_line(evidence.document) if evidence.document else ""
        if evidence.page is not None:
            location += f":p{evidence.page}"
        if evidence.bbox is not None:
            location += f" bbox={evidence.bbox}"
        if location:
            label += f" — {location}"
    return label


def explain(node: Node) -> str:
    """Render ordered operands. A ref marker denotes an already shown node."""
    if not isinstance(node, Node):
        raise TypeError("explain expects a Node")
    lines: list[str] = []
    seen: set[str] = set()
    stack = [(node, "", "", "")]
    while stack:
        current, prefix, connector, child_prefix = stack.pop()
        label = _label(current)
        if current.id in seen:
            lines.append(f"{prefix}{connector}{label} [ref {current.id[:19]}]")
            continue
        lines.append(prefix + connector + label)
        seen.add(current.id)
        for index in range(len(current.parents) - 1, -1, -1):
            last = index == len(current.parents) - 1
            stack.append((current.parents[index], child_prefix,
                          "└── " if last else "├── ",
                          child_prefix + ("    " if last else "│   ")))
    return "\n".join(lines)
