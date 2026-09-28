"""Public API behavior for immutable, content-addressed provenance."""

from dataclasses import FrozenInstanceError
import math
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

from proofgraph import Evidence, Node, explain, source


def test_annual_report_arithmetic_tracks_ordered_inputs():
    revenue = source(1_000, name="Revenue", document="annual_report.pdf", page=71)
    cost = source(813, name="Operating cost", document="annual_report.pdf", page=73)
    profit = (revenue - cost).named("Operating profit")
    margin = (profit / revenue * 100).named("Operating margin (%)")

    assert isinstance(profit, Node)
    assert profit.value == 187
    assert profit.kind == "derived"
    assert profit.operation == "subtract"
    assert profit.parents == (revenue, cost)
    assert margin.value == pytest.approx(18.7)
    assert margin.parents[0].parents == (profit, revenue)
    assert margin.parents[1].kind == "literal"
    assert margin.parents[1].value == 100


@pytest.mark.parametrize(
    ("operation", "expected", "operation_name"),
    [
        (lambda node: node + 2, 10, "add"),
        (lambda node: node - 2, 6, "subtract"),
        (lambda node: node * 2, 16, "multiply"),
        (lambda node: node / 2, 4.0, "divide"),
        (lambda node: 2 + node, 10, "add"),
        (lambda node: 2 - node, -6, "subtract"),
        (lambda node: 2 * node, 16, "multiply"),
        (lambda node: 2 / node, 0.25, "divide"),
    ],
)
def test_arithmetic_and_reflected_arithmetic(operation, expected, operation_name):
    node = source(8)
    result = operation(node)
    assert result.value == expected
    assert result.operation == operation_name
    assert node in result.parents
    assert len(result.parents) == 2
    assert {parent.kind for parent in result.parents} == {"source", "literal"}


def test_noncommutative_operand_order_is_preserved():
    node = source(8)
    left = node - 2
    right = 2 - node
    assert left.parents[0] is node
    assert right.parents[1] is node
    assert left.id != right.id
    assert (node / 2).parents[0] is node
    assert (2 / node).parents[1] is node


def test_source_and_literal_have_different_identity():
    original = source(2)
    literal = (original + 2).parents[1]
    assert literal.kind == "literal"
    assert literal.id != original.id


def test_named_returns_new_node_without_mutating_provenance():
    revenue = source(100, name="Revenue")
    derived = revenue * 2
    renamed = derived.named("Doubled revenue")
    assert renamed is not derived
    assert renamed.value == derived.value
    assert renamed.parents == derived.parents
    assert renamed.operation == derived.operation
    assert renamed.kind == derived.kind
    assert derived.name is None
    assert renamed.name == "Doubled revenue"
    assert renamed.id != derived.id
    assert renamed.named(None).id == derived.id
    assert renamed.named("Doubled revenue").id == renamed.id


def test_source_evidence_convenience_api_matches_explicit_evidence():
    evidence = Evidence(document="annual_report.pdf", page=71, bbox=[10, 20, 30, 40])
    explicit = source(1_000, name="Revenue", evidence=evidence)
    convenience = source(
        1_000, name="Revenue", document="annual_report.pdf", page=71, bbox=(10, 20, 30, 40)
    )
    assert explicit.id == convenience.id
    assert explicit.evidence == evidence
    assert explicit.evidence.bbox == (10, 20, 30, 40)


def test_nested_evidence_is_copied_and_frozen():
    bounds = [1, 2, 3, 4]
    evidence = Evidence(document="report.pdf", page=1, bbox=bounds)
    node = source(10, evidence=evidence)
    bounds[0] = -100
    assert evidence.bbox == (1, 2, 3, 4)
    assert isinstance(evidence.bbox, tuple)
    assert isinstance(node.parents, tuple)
    with pytest.raises(FrozenInstanceError):
        node.value = 20
    with pytest.raises(FrozenInstanceError):
        evidence.page = 2
    with pytest.raises(TypeError):
        evidence.bbox[0] = 8


def test_direct_construction_copies_parent_sequence():
    parents = [source(2), source(3)]
    node = Node(5, kind="derived", operation="add", parents=parents)
    parents.clear()
    assert len(node.parents) == 2
    assert isinstance(node.parents, tuple)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": "unknown"},
        {"kind": "derived", "operation": "add"},
        {"kind": "derived", "operation": "unknown", "parents": (source(1), source(2))},
        {"kind": "derived", "operation": "add", "parents": (source(1), source(2))},
        {"kind": "source", "parents": (source(1),)},
        {"kind": "literal", "evidence": Evidence(page=1)},
        {"evidence": {"page": 1}},
        {"name": 1},
    ],
)
def test_direct_construction_cannot_bypass_node_invariants(kwargs):
    with pytest.raises((TypeError, ValueError)):
        Node(10, **kwargs)


@pytest.mark.parametrize("page", [0, -1, 1.5, True, "1"])
def test_evidence_rejects_invalid_page(page):
    with pytest.raises((TypeError, ValueError)):
        Evidence(page=page)


@pytest.mark.parametrize(
    "bbox",
    [(1, 2, 3), (1, 2, 3, 4, 5), (3, 2, 1, 4), (1, 4, 3, 2), (0, 0, math.inf, 1), (0, 0, math.nan, 1), (False, 0, 1, 1)],
)
def test_evidence_rejects_invalid_bounding_boxes(bbox):
    with pytest.raises((TypeError, ValueError)):
        Evidence(page=1, bbox=bbox)


def test_bbox_requires_page_but_page_does_not_require_document():
    with pytest.raises((TypeError, ValueError)):
        Evidence(bbox=(0, 0, 1, 1))
    assert Evidence(page=1).page == 1


@pytest.mark.parametrize("kwargs", [{"document": "other.pdf"}, {"page": 2}, {"page": 2, "bbox": (0, 0, 1, 1)}])
def test_explicit_and_convenience_evidence_cannot_be_mixed(kwargs):
    with pytest.raises((TypeError, ValueError)):
        source(1, evidence=Evidence(document="report.pdf", page=1), **kwargs)


@pytest.mark.parametrize("value", [True, False, None, "5", [], {}, complex(1, 2), math.nan, math.inf, -math.inf])
def test_source_rejects_unsupported_or_nonfinite_values(value):
    with pytest.raises((TypeError, ValueError)):
        source(value)


@pytest.mark.parametrize("value", [True, False, "1", None, math.nan, math.inf])
def test_arithmetic_rejects_unsupported_or_nonfinite_values(value):
    node = source(3)
    with pytest.raises((TypeError, ValueError)):
        node + value
    with pytest.raises((TypeError, ValueError)):
        value + node


def test_arithmetic_rejects_nonfinite_results():
    with pytest.raises((ValueError, OverflowError)):
        source(1e308) * 10.0


def test_zero_division_uses_python_error():
    with pytest.raises(ZeroDivisionError):
        source(1) / 0
    with pytest.raises(ZeroDivisionError):
        1 / source(0)


def test_stable_ids_include_types_names_evidence_and_input_order():
    first = source(100, name="Revenue", document="report.pdf", page=1)
    second = source(100, name="Revenue", document="report.pdf", page=1)
    assert first.id == second.id
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", first.id)
    assert source(1).id != source(1.0).id
    assert source(0.0).id != source(-0.0).id
    assert source(100, name="Revenue").id != source(100, name="Cost").id
    assert first.id != source(100, name="Revenue", document="report.pdf", page=2).id
    assert (first + 1).id == (second + 1).id
    assert (first + 1).id != (1 + first).id


def test_stable_ids_do_not_depend_on_process_hash_seed():
    project_root = Path(__file__).resolve().parents[1]
    script = (
        "from proofgraph import source; "
        "r=source(1000,name='Revenue',document='annual_report.pdf',page=71); "
        "c=source(813,name='Cost',document='annual_report.pdf',page=73); "
        "print(((r-c)/r*100).named('Margin').id)"
    )
    ids = []
    for seed in ("1", "12345", "random"):
        environment = os.environ.copy()
        environment["PYTHONHASHSEED"] = seed
        environment["PYTHONPATH"] = str(project_root / "src")
        ids.append(subprocess.check_output([sys.executable, "-c", script], env=environment, text=True).strip())
    assert len(set(ids)) == 1


def test_v1_identity_format_is_stable():
    assert source(1).id == (
        "sha256:f787f986e07304b65b0915dc6c2dbe32d9a9fff96919efe6173d589cea8d4b4a"
    )
    assert (source(1) + 2).id == (
        "sha256:449880b3f18f7e7b56795121ffadab1bea2e8603e1f1c8b492bfe5f128f9771a"
    )


def test_explanation_contains_named_sources_and_evidence():
    revenue = source(1_000, name="Revenue", document="annual_report.pdf", page=71)
    cost = source(813, name="Cost", document="annual_report.pdf", page=73)
    profit = (revenue - cost).named("Profit")
    text = explain(profit)
    assert text == profit.explain()
    for expected in ("Revenue", "Cost", "Profit", "187", "annual_report.pdf", "71", "73"):
        assert expected in text


def test_deep_graph_explanation_does_not_recurse():
    node = source(0, name="Start")
    for _ in range(1_200):
        node = node + 1
    rendered = node.explain()
    assert "Start" in rendered
    assert "1200" in rendered


def test_shared_subgraph_is_expanded_only_once():
    node = source(1, name="Shared source")
    for _ in range(30):
        node = node + node
    lines = node.explain().splitlines()
    assert len(lines) == 61
    assert sum("[ref " in line for line in lines) == 30
