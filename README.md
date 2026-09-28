# ProofGraph

**Follow a derived number back to its sources.**

ProofGraph is a small Python package for immutable provenance graphs. Wrap a source value, calculate with ordinary arithmetic, and inspect the evidence and operations behind the result.

Version 0.1 targets Python 3.11+ and has no runtime dependencies.

## Install

From the repository directory:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

For runtime use without the test tools, use `python -m pip install .`. These are local installation instructions; this project has not been published to PyPI.

## A 20-second demo

```python
from proofgraph import Evidence, from_json, source

# Illustrative figures, all in INR crore.
revenue = source(
    1_000,
    name="Revenue",
    evidence=Evidence(document="annual_report.pdf", page=71),
)
cost = source(
    813,
    name="Operating cost",
    evidence=Evidence(document="annual_report.pdf", page=73),
)

profit = (revenue - cost).named("Operating profit")
margin = ((profit / revenue) * 100).named("Operating margin (%)")

print(profit.value)       # 187
print(margin.value)       # 18.7
print(margin.explain())   # A text tree of the calculation and its sources

restored = from_json(margin.to_json(indent=2))
assert restored.id == margin.id
```

Revenue participates in both profit and margin. The graph retains that shared source; JSON stores each node once.

Run the full example with:

```sh
python examples/annual_report.py
```

## Small API

| API | Purpose |
| --- | --- |
| `source(value, name=..., evidence=...)` | Create an immutable source node. |
| `Evidence(document=..., page=..., bbox=...)` | Attach an optional document locator to a source. |
| `node + other`, `node - other`, `node * other`, `node / other` | Calculate a value while retaining ordered input nodes. Plain numbers work on either side. |
| `node.named("Label")` | Return a new labeled node, retaining its inputs. |
| `node.value`, `node.id`, `node.parents` | Inspect the result, content hash, and input nodes. |
| `node.explain()` or `explain(node)` | Render a readable provenance tree. |
| `node.to_dict()` or `to_dict(node)` | Export a JSON-compatible graph document. |
| `node.to_json(indent=2)` or `to_json(node, indent=2)` | Serialize a graph. |
| `from_dict(document)` or `from_json(text)` | Validate and reconstruct a graph. |

`Node`, `Evidence`, `source`, `explain`, `to_dict`, `from_dict`, `to_json`, and `from_json` are exported from `proofgraph`.

The shorthand `source(1000, document="report.pdf", page=71)` also creates evidence. Use either an `Evidence` object or the evidence keyword arguments. Page numbers are positive and one-based; a bounding box requires a page. A bounding box is a four-number tuple whose coordinate convention and units are supplied by the caller. ProofGraph records it without interpreting the document or its layout.

## Design principles

- **Immutable by construction.** Frozen dataclasses and tuple inputs keep existing nodes unchanged. Arithmetic and labeling produce new nodes.
- **A graph, not a calculation log.** Nodes retain their inputs, including shared ancestors. Literal operands are distinct from declared sources.
- **Content determines identity.** SHA-256 IDs cover the canonical node content, including numeric types, labels, evidence, and ordered parent IDs. There are no timestamps or random identifiers. Identical content has the same ID; relabeling changes the ID.
- **Portable and inspectable.** Versioned JSON uses `schema_version`, a root ID, and a deduplicated node table. Import checks IDs and graph structure, replays arithmetic, and rejects cycles, dangling references, and unreachable nodes.
- **Keep the core small.** The provenance graph and evidence locator do not depend on a PDF parser, model provider, or application framework.

Two source declarations with identical values, labels, and evidence share an identity. Use a distinct label or evidence locator when separate observations must remain distinguishable.

## What v0.1 does—and does not—claim

ProofGraph records **how a number was derived from declared inputs**. A content hash detects inconsistencies in a serialized graph; it does not establish that an external document exists, that a source value is correct, or who supplied it. Someone who changes inputs and recomputes their hashes has created a different valid graph.

Values are Python `int` or finite `float`; booleans are rejected. Division and floating-point rounding follow Python semantics. The package does not support `Decimal`, automatic unit conversion, currency handling, arbitrary user-defined operations, PDF extraction, or proof of factual truth. Keep units consistent in your application and use labels to make them visible.

## Development

```sh
python -m pytest
python examples/annual_report.py
python examples/roundtrip.py
```

The package uses a `src/` layout. Implementation lives in `src/proofgraph/`, tests in `tests/`, and executable examples in `examples/`.

## Roadmap

The next additions should preserve the small, portable core:

- Richer evidence locators for document spans, table cells, and explicitly defined PDF coordinate systems.
- Optional adapters for Pydantic extraction outputs and RAG citations.
- Clear operation extension and schema migration policies before supporting custom transformations.
- Graph comparison to explain which source or calculation changed a result.

These are directions, not v0.1 features. Contributions that improve correctness, examples, and a focused API are especially welcome.

## License

[MIT](LICENSE).
