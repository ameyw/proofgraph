"""Small immutable value and evidence models, independent of integrations."""

from __future__ import annotations

import hashlib
import json
import math
import operator
from dataclasses import dataclass, field, replace
from typing import Literal, TypeAlias

Number: TypeAlias = int | float
Kind: TypeAlias = Literal["source", "literal", "derived"]
Operation: TypeAlias = Literal["add", "subtract", "multiply", "divide"]
BBox: TypeAlias = tuple[Number, Number, Number, Number]

_OPERATIONS = {
    "add": operator.add,
    "subtract": operator.sub,
    "multiply": operator.mul,
    "divide": operator.truediv,
}


def _number(value: object) -> None:
    if type(value) not in (int, float):
        raise TypeError("values must be int or float (bool is not supported)")
    if type(value) is float and not math.isfinite(value):
        raise ValueError("values must be finite")


def _canonical(value: object) -> str:
    # Explicit settings form part of the v1 identity format. In particular,
    # Python's JSON encoding distinguishes 1, 1.0, 0.0 and -0.0.
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


@dataclass(frozen=True, slots=True)
class Evidence:
    """A reference to evidence; coordinates are supplied, never interpreted.

    Pages are one-based. A bbox is (x0, y0, x1, y1) and requires a page.
    This class does not read a document or attest to its contents.
    """

    document: str | None = None
    page: int | None = None
    bbox: BBox | None = None

    def __post_init__(self) -> None:
        if self.document is not None:
            if not isinstance(self.document, str):
                raise TypeError("document must be a string or None")
            if not self.document.strip():
                raise ValueError("document must not be empty")
        if self.page is not None:
            if type(self.page) is not int:
                raise TypeError("page must be an integer or None")
            if self.page < 1:
                raise ValueError("page must be positive (one-based)")
        if self.bbox is not None:
            bbox = tuple(self.bbox)
            if len(bbox) != 4:
                raise ValueError("bbox must have four coordinates")
            for coordinate in bbox:
                _number(coordinate)
            if self.page is None:
                raise ValueError("bbox requires a page")
            if bbox[0] > bbox[2] or bbox[1] > bbox[3]:
                raise ValueError("bbox must satisfy x0 <= x1 and y0 <= y1")
            object.__setattr__(self, "bbox", bbox)

    def to_dict(self) -> dict:
        return {"document": self.document, "page": self.page,
                "bbox": list(self.bbox) if self.bbox is not None else None}


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class Node:
    """A numeric fact, literal constant, or arithmetic result.

    Prefer :func:`source` and arithmetic to direct construction. Parents are
    ordered operands. All node content, including the name, contributes to id.
    """

    value: Number
    kind: Kind = "source"
    name: str | None = None
    evidence: Evidence | None = None
    operation: Operation | None = None
    parents: tuple[Node, ...] = ()
    id: str = field(init=False)

    def __post_init__(self) -> None:
        _number(self.value)
        if self.name is not None:
            if not isinstance(self.name, str):
                raise TypeError("name must be a string or None")
            if not self.name.strip():
                raise ValueError("name must not be empty")
        if self.kind not in ("source", "literal", "derived"):
            raise ValueError("kind must be source, literal, or derived")
        if self.evidence is not None and not isinstance(self.evidence, Evidence):
            raise TypeError("evidence must be an Evidence instance or None")
        parents = tuple(self.parents)
        if any(not isinstance(parent, Node) for parent in parents):
            raise TypeError("parents must contain only Node instances")
        object.__setattr__(self, "parents", parents)
        if self.kind == "derived":
            if not isinstance(self.operation, str) or self.operation not in _OPERATIONS:
                raise ValueError("derived nodes require a supported operation")
            if len(parents) != 2:
                raise ValueError("arithmetic requires exactly two ordered parents")
            if self.evidence is not None:
                raise ValueError("derived nodes inherit evidence through parents")
            expected = _OPERATIONS[self.operation](parents[0].value, parents[1].value)
            _number(expected)
            if _canonical(self.value) != _canonical(expected):
                raise ValueError("derived value does not match its operation and parents")
        else:
            if parents or self.operation is not None:
                raise ValueError("source and literal nodes cannot have parents or operations")
            if self.kind == "literal" and self.evidence is not None:
                raise ValueError("literal constants cannot have evidence")
        payload = "proofgraph:node:v1\n" + _canonical(self._record())
        object.__setattr__(self, "id", "sha256:" + hashlib.sha256(payload.encode()).hexdigest())

    def _record(self) -> dict:
        return {
            "kind": self.kind, "value": self.value, "name": self.name,
            "evidence": self.evidence.to_dict() if self.evidence is not None else None,
            "operation": self.operation, "parents": [parent.id for parent in self.parents],
        }

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Node):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def __repr__(self) -> str:
        return f"Node(value={self.value!r}, kind={self.kind!r}, name={self.name!r}, id={self.id!r})"

    def named(self, name: str | None) -> Node:
        """Return a new node with a display name (and a new content ID)."""
        return replace(self, name=name)

    def _binary(self, other: Node | Number, operation: Operation, reverse: bool = False):
        if not isinstance(other, Node):
            if type(other) not in (int, float):
                return NotImplemented
            other = Node(other, kind="literal")
        left, right = (other, self) if reverse else (self, other)
        value = _OPERATIONS[operation](left.value, right.value)
        return Node(value, kind="derived", operation=operation, parents=(left, right))

    def __add__(self, other: Node | Number) -> Node:
        return self._binary(other, "add")

    def __radd__(self, other: Node | Number) -> Node:
        return self._binary(other, "add", reverse=True)

    def __sub__(self, other: Node | Number) -> Node:
        return self._binary(other, "subtract")

    def __rsub__(self, other: Node | Number) -> Node:
        return self._binary(other, "subtract", reverse=True)

    def __mul__(self, other: Node | Number) -> Node:
        return self._binary(other, "multiply")

    def __rmul__(self, other: Node | Number) -> Node:
        return self._binary(other, "multiply", reverse=True)

    def __truediv__(self, other: Node | Number) -> Node:
        return self._binary(other, "divide")

    def __rtruediv__(self, other: Node | Number) -> Node:
        return self._binary(other, "divide", reverse=True)

    def explain(self) -> str:
        from .render import explain
        return explain(self)

    def to_dict(self) -> dict:
        from .serialization import to_dict
        return to_dict(self)

    def to_json(self, *, indent: int | None = 2) -> str:
        from .serialization import to_json
        return to_json(self, indent=indent)


def source(
    value: Number, *, name: str | None = None, evidence: Evidence | None = None,
    document: str | None = None, page: int | None = None, bbox: BBox | None = None,
) -> Node:
    """Record a numeric source, optionally with a document location.

    Supply either an Evidence object or the document/page/bbox shortcuts.
    """
    has_location = any(part is not None for part in (document, page, bbox))
    if evidence is not None and has_location:
        raise ValueError("use evidence or document/page/bbox, not both")
    if has_location:
        evidence = Evidence(document=document, page=page, bbox=bbox)
    return Node(value, name=name, evidence=evidence)
