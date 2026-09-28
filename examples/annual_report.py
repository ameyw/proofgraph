"""Illustrative annual-report provenance; figures are fabricated, in INR crore.

Run after installing the package: python examples/annual_report.py
"""

from proofgraph import Evidence, from_json, source


def main() -> None:
    revenue = source(
        1_000,
        name="Revenue (INR crore)",
        evidence=Evidence(document="annual_report.pdf", page=71),
    )
    cost = source(
        813,
        name="Operating cost (INR crore)",
        evidence=Evidence(document="annual_report.pdf", page=73),
    )

    profit = (revenue - cost).named("Operating profit (INR crore)")
    margin = ((profit / revenue) * 100).named("Operating margin (%)")

    print("Illustrative annual-report figures; not extracted from a real report.")
    print(f"Operating profit: INR {profit.value:,} crore")
    print(f"Operating margin: {margin.value:.1f}%")
    print()
    print(margin.explain())

    # Revenue is reused by both subtraction and division. The graph stores a
    # single source node for it, even when multiple paths lead to that source.
    document = margin.to_dict()
    occurrences = sum(node["id"] == revenue.id for node in document["nodes"])
    assert occurrences == 1

    encoded = margin.to_json(indent=2)
    restored = from_json(encoded)
    assert restored.id == margin.id
    assert restored.value == margin.value
    print()
    print(f"JSON round-trip preserved the root ID: {restored.id}")
    print(f"Serialized graph: {len(document['nodes'])} unique nodes")


if __name__ == "__main__":
    main()
