"""Print a portable provenance graph and reconstruct it without external files."""

from proofgraph import from_json, source


def main() -> None:
    quantity = source(3, name="Quantity", document="invoice.pdf", page=1)
    unit_price = source(125, name="Unit price (INR)", document="invoice.pdf", page=1)
    total = (quantity * unit_price).named("Total (INR)")

    encoded = total.to_json(indent=2)
    print(encoded)

    restored = from_json(encoded)
    assert restored.id == total.id
    assert restored.value == 375
    print()
    print(restored.explain())


if __name__ == "__main__":
    main()
