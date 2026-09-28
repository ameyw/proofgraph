"""Versioned DAG interchange preserves identities and rejects corrupt input."""

from copy import deepcopy
import hashlib
import json
import math

import pytest

from proofgraph import Evidence, from_dict, from_json, source, to_dict, to_json


@pytest.fixture
def graph():
    revenue = source(1_000, name="Revenue", evidence=Evidence(document="report.pdf", page=71, bbox=(1, 2, 3, 4)))
    cost = source(813, name="Cost", document="report.pdf", page=73)
    return ((revenue - cost) / revenue * 100).named("Margin")


def test_round_trip_preserves_graph_and_public_method_equivalence(graph):
    document = to_dict(graph)
    assert document == graph.to_dict()
    assert set(document) == {"schema_version", "root", "nodes"}
    assert document["schema_version"] == 1
    assert document["root"] == graph.id
    restored = from_dict(document)
    assert restored.id == graph.id
    assert restored.value == graph.value
    assert restored.explain() == graph.explain()
    assert to_dict(restored) == document
    assert to_json(graph) == graph.to_json()
    assert from_json(graph.to_json()).id == graph.id
    assert from_json(to_json(graph, indent=2)).id == graph.id


def test_records_are_deduplicated_and_in_parent_first_order(graph):
    document = graph.to_dict()
    seen = set()
    for record in document["nodes"]:
        assert set(record) == {"id", "kind", "value", "name", "evidence", "operation", "parents"}
        assert record["id"] not in seen
        assert all(parent_id in seen for parent_id in record["parents"])
        seen.add(record["id"])
    assert document["nodes"][-1]["id"] == graph.id
    assert sum(record["name"] == "Revenue" for record in document["nodes"]) == 1
    evidence = next(record["evidence"] for record in document["nodes"] if record["name"] == "Revenue")
    assert evidence == {"document": "report.pdf", "page": 71, "bbox": [1, 2, 3, 4]}


def test_load_accepts_arbitrary_record_order_and_canonicalizes(graph):
    canonical = graph.to_dict()
    reordered = deepcopy(canonical)
    reordered["nodes"].reverse()
    assert from_dict(reordered).to_dict() == canonical


def test_shared_diamond_restores_shared_node_identity():
    shared = source(5, name="Shared")
    graph = (shared + 1) * (shared - 2)
    restored = from_json(graph.to_json())
    assert restored.parents[0].parents[0] is restored.parents[1].parents[0]
    assert len(restored.to_dict()["nodes"]) == 6


def test_independent_identical_nodes_are_deduplicated():
    graph = source(5, name="Same") + source(5, name="Same")
    assert len(graph.to_dict()["nodes"]) == 2
    restored = from_dict(graph.to_dict())
    assert restored.parents[0] is restored.parents[1]


def test_serialized_output_is_detached_from_graph(graph):
    document = graph.to_dict()
    source_record = next(record for record in document["nodes"] if record["name"] == "Revenue")
    source_record["evidence"]["bbox"][0] = -100
    document["nodes"][-1]["parents"].clear()
    pristine = graph.to_dict()
    assert next(record for record in pristine["nodes"] if record["name"] == "Revenue")["evidence"]["bbox"][0] == 1
    assert len(pristine["nodes"][-1]["parents"]) == 2


@pytest.mark.parametrize("value", [0, 1, -1, 1.0, 0.0, -0.0, 1e-20, 2**100])
def test_numeric_types_and_float_sign_survive_json(value):
    original = source(value)
    restored = from_json(original.to_json())
    assert restored.id == original.id
    assert type(restored.value) is type(value)
    if isinstance(value, float):
        assert math.copysign(1, restored.value) == math.copysign(1, value)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [("value", 999), ("name", "Tampered"), ("operation", "add"), ("id", "sha256:" + "0" * 64)],
)
def test_rejects_tampered_derived_nodes(graph, field, replacement):
    document = graph.to_dict()
    document["nodes"][-1][field] = replacement
    with pytest.raises((TypeError, ValueError)):
        from_dict(document)


def test_rejects_wrong_result_even_when_content_hash_is_recomputed(graph):
    document = graph.to_dict()
    record = document["nodes"][-1]
    record["value"] = 999
    payload = {key: value for key, value in record.items() if key != "id"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    record["id"] = "sha256:" + hashlib.sha256(("proofgraph:node:v1\n" + canonical).encode()).hexdigest()
    document["root"] = record["id"]
    with pytest.raises((TypeError, ValueError)):
        from_dict(document)


def test_rejects_tampered_source_evidence(graph):
    document = graph.to_dict()
    document["nodes"][0]["evidence"]["page"] = 99
    with pytest.raises((TypeError, ValueError)):
        from_dict(document)


def test_rejects_missing_references(graph):
    document = graph.to_dict()
    document["nodes"][-1]["parents"][0] = "sha256:" + "0" * 64
    with pytest.raises((TypeError, ValueError)):
        from_dict(document)


def test_rejects_cycles(graph):
    document = graph.to_dict()
    document["nodes"][-1]["parents"][0] = document["root"]
    with pytest.raises((TypeError, ValueError)):
        from_dict(document)


def test_rejects_duplicate_records(graph):
    document = graph.to_dict()
    document["nodes"].append(deepcopy(document["nodes"][0]))
    with pytest.raises((TypeError, ValueError)):
        from_dict(document)


def test_rejects_unreachable_records(graph):
    document = graph.to_dict()
    document["nodes"].append(source(42, name="Unreachable").to_dict()["nodes"][0])
    with pytest.raises((TypeError, ValueError)):
        from_dict(document)


@pytest.mark.parametrize("where", ["envelope", "node", "evidence"])
def test_rejects_unknown_fields(graph, where):
    document = graph.to_dict()
    if where == "envelope":
        document["unexpected"] = True
    elif where == "node":
        document["nodes"][-1]["unexpected"] = True
    else:
        document["nodes"][0]["evidence"]["unexpected"] = True
    with pytest.raises((TypeError, ValueError)):
        from_dict(document)


@pytest.mark.parametrize("field", ["schema_version", "root", "nodes"])
def test_rejects_missing_envelope_fields(graph, field):
    document = graph.to_dict()
    del document[field]
    with pytest.raises((TypeError, ValueError)):
        from_dict(document)


@pytest.mark.parametrize("version", [0, 2, "1", True, None])
def test_rejects_unknown_or_invalid_schema_versions(graph, version):
    document = graph.to_dict()
    document["schema_version"] = version
    with pytest.raises((TypeError, ValueError)):
        from_dict(document)


@pytest.mark.parametrize("document", [None, [], {}, {"schema_version": 1, "root": "missing", "nodes": []}])
def test_rejects_invalid_document_shape(document):
    with pytest.raises((TypeError, ValueError)):
        from_dict(document)


@pytest.mark.parametrize("text", ["not json", "null", "[]", '{"schema_version": 1, "root": "missing", "nodes": []}'])
def test_rejects_invalid_json_or_document(text):
    with pytest.raises((TypeError, ValueError)):
        from_json(text)


def test_rejects_nonfinite_json_number(graph):
    document = graph.to_dict()
    document["nodes"][0]["value"] = math.nan
    with pytest.raises((TypeError, ValueError)):
        from_json(json.dumps(document))


def test_rejects_duplicate_json_keys(graph):
    encoded = graph.to_json()
    encoded = encoded.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1')
    with pytest.raises(ValueError, match="duplicate JSON key"):
        from_json(encoded)


def test_deep_graph_round_trip_does_not_recurse():
    node = source(0)
    for _ in range(1_200):
        node = node + 1
    restored = from_json(node.to_json())
    assert restored.id == node.id
    assert restored.value == 1_200
    assert len(restored.to_dict()["nodes"]) == 1_202
