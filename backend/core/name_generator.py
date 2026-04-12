"""Human-memorable client_id generator for MCP Client artifacts.

Produces three-word identifiers in the pattern ``{adjective}-{color}-{animal}``.
Example: ``funky-blue-monkey``, ``calm-red-fox``, ``swift-green-falcon``.
"""
from __future__ import annotations

import random

_ADJECTIVES = [
    "bold", "brave", "bright", "calm", "clever", "cool", "daring", "eager",
    "fair", "fast", "fierce", "free", "funky", "gentle", "glad", "grand",
    "happy", "keen", "kind", "lively", "lucky", "merry", "noble", "proud",
    "quick", "quiet", "sharp", "smart", "steady", "strong", "sure", "swift",
    "true", "vivid", "warm", "wild", "wise", "witty", "zesty",
]

_COLORS = [
    "amber", "azure", "blue", "bronze", "coral", "crimson", "cyan", "emerald",
    "gold", "gray", "green", "indigo", "ivory", "jade", "lavender", "lime",
    "magenta", "navy", "olive", "orange", "peach", "pink", "plum", "purple",
    "red", "rose", "ruby", "sage", "scarlet", "silver", "slate", "teal",
    "turquoise", "violet", "white", "yellow",
]

_ANIMALS = [
    "badger", "bear", "bison", "crane", "crow", "deer", "dolphin", "eagle",
    "elk", "falcon", "finch", "fox", "gecko", "hawk", "heron", "horse",
    "jaguar", "jay", "kite", "koala", "lark", "lemur", "lion", "lynx",
    "moose", "newt", "orca", "osprey", "otter", "owl", "panda", "parrot",
    "pike", "puma", "quail", "raven", "robin", "seal", "shark", "shrike",
    "snake", "sparrow", "stork", "swift", "tiger", "toucan", "viper", "whale",
    "wolf", "wren",
]


def generate_client_id() -> str:
    """Generate a random ``adjective-color-animal`` client_id."""
    return f"{random.choice(_ADJECTIVES)}-{random.choice(_COLORS)}-{random.choice(_ANIMALS)}"
