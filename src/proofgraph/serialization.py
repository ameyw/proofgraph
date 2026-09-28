"""Versioned JSON interchange with content and arithmetic verification."""

from __future__ import annotations

import json

from .model import Evidence, Node

SCHEMA_VERSION = 1
_ENVELOPE_KEYS = {"schema_version", "root", "nodes"}
_NODE_KEYS = {"id", "kind", "value", "name", "evidence", "operation", "parents"}
_EVIDENCE_KEYS = {"document", "page", "bbox"}


def to_dict(node: Node) -> dict:
    """Return a detached JSON-compatible graph, dependencies before consumers."""
    if not isinstance(node, Node):
        raise TypeError("to_dict expects a Node")
    records: list[dict] = []
    seen: set[str] = set()
    stack = [(node, False)]
    while stack:
        current, expanded = stack.pop()
        if current.id in seen:
            continue
        if expanded:
            records.append({"id": current.id, **current._record()})
            seen.add(current.id)
        else:
            stack.append((current, True))
            stack.extend((parent, False) for parent in reversed(current.parents))
    return {"schema_version": SCHEMA_VERSION, "root": node.id, "nodes": records}


def to_json(node: Node, *, indent: int | None = 2) -> str:
    """Serialize one root and all reachable nodes without duplicating shared nodes."""
    return json.dumps(to_dict(node), sort_keys=True, ensure_ascii=True,
                      allow_nan=False, indent=indent)


def _keys(value: object, expected: set[str], description: str) -> None:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{description} must have exactly these fields: {', '.join(sorted(expected))}")


def from_dict(data: dict) -> Node:
    """Load a v1 graph, validating IDs, references, cycles, and arithmetic.

    Node order is insignificant. Shared IDs become shared Python objects.
    Validation establishes internal consistency, not source authenticity.
    """
    _keys(data, _ENVELOPE_KEYS, "graph")
    if type(data["schema_version"]) is not int or data["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported schema_version")
    root = data["root"]
    if not isinstance(root, str):
        raise ValueError("root must be a node ID string")
    if not isinstance(data["nodes"], list) or not data["nodes"]:
        raise ValueError("nodes must be a nonempty array")
    records: dict[str, dict] = {}
    for record in data["nodes"]:
        _keys(record, _NODE_KEYS, "node")
        node_id = record["id"]
        if not isinstance(node_id, str):
            raise ValueError("node id must be a string")
        if node_id in records:
            raise ValueError(f"duplicate node id: {node_id}")
        if not isinstance(record["parents"], list) or any(
            not isinstance(parent, str) for parent in record["parents"]
        ):
            raise ValueError("parents must be an array of node ID strings")
        records[node_id] = record
    if root not in records:
        raise ValueError("root references a missing node")
    for record in records.values():
        if any(parent not in records for parent in record["parents"]):
            raise ValueError("dangling parent reference")

    # Explicit stacks keep graph depth independent of Python's recursion limit.
    built: dict[str, Node] = {}
    visiting: set[str] = set()
    stack = [(root, False)]
    while stack:
        node_id, expanded = stack.pop()
        if node_id in built:
            continue
        record = records[node_id]
        if not expanded:
            if node_id in visiting:
                raise ValueError("cycle detected in graph")
            visiting.add(node_id)
            stack.append((node_id, True))
            stack.extend((parent, False) for parent in reversed(record["parents"]))
            continue
        raw_evidence = record["evidence"]
        evidence = None
        try:
            if raw_evidence is not None:
                _keys(raw_evidence, _EVIDENCE_KEYS, "evidence")
                if raw_evidence["bbox"] is not None and not isinstance(raw_evidence["bbox"], list):
                    raise ValueError("serialized bbox must be an array or null")
                evidence = Evidence(**raw_evidence)
            node = Node(
                value=record["value"], kind=record["kind"], name=record["name"],
                evidence=evidence, operation=record["operation"],
                parents=tuple(built[parent] for parent in record["parents"]),
            )
        except (TypeError, ValueError, ArithmeticError) as error:
            raise ValueError(f"invalid node {node_id}: {error}") from error
        if node.id != node_id:
            raise ValueError(f"content ID mismatch for node {node_id}")
        built[node_id] = node
        visiting.remove(node_id)
    if len(built) != len(records):
        raise ValueError("graph contains unreachable nodes")
    return built[root]


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError(f"nonfinite JSON number: {value}")


def from_json(data: str) -> Node:
    """Load JSON without accepting duplicate keys or nonstandard NaN/Infinity."""
    return from_dict(json.loads(data, object_pairs_hook=_unique_object,
                                parse_constant=_invalid_constant))
