"""Immutable provenance DAGs for derived values."""

from .model import Evidence, Node, source
from .render import explain
from .serialization import from_dict, from_json, to_dict, to_json

__version__ = "0.1.0"
__all__ = [
    "Evidence", "Node", "source", "explain",
    "to_dict", "from_dict", "to_json", "from_json", "__version__",
]
