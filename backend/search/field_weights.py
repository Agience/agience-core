"""
Search Field Weights Loader

Loads field boost configurations from JSON preset files.
Supports multiple presets for A/B testing and per-collection customization.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Directory containing weight preset files
WEIGHTS_DIR = Path(__file__).parent / "weights"

# Cache loaded presets to avoid repeated file I/O
_preset_cache: Dict[str, Dict[str, float]] = {}


def load_field_weights(preset_name: str = "description-first") -> Dict[str, float]:
    """
    Load field boost weights from a preset file.
    
    Args:
        preset_name: Name of preset file (without .json extension)
        
    Returns:
        Dictionary mapping field names to boost weights
        
    Raises:
        FileNotFoundError: If preset file doesn't exist
        ValueError: If preset file is invalid
        
    Example:
        >>> weights = load_field_weights("balanced")
        >>> weights
        {'description': 5.0, 'title': 3.0, 'tags_canonical': 2.0, 'content': 1.0}
    """
    # Check cache first
    if preset_name in _preset_cache:
        return _preset_cache[preset_name]
    
    # Load from file
    preset_path = WEIGHTS_DIR / f"{preset_name}.json"
    
    if not preset_path.exists():
        raise FileNotFoundError(
            f"Field weights preset not found: {preset_name}\n"
            f"Available presets: {list_available_presets()}\n"
            f"Expected path: {preset_path}"
        )
    
    try:
        with open(preset_path, "r") as f:
            preset_data = json.load(f)
        
        if "field_boosts" not in preset_data:
            raise ValueError(f"Preset {preset_name} missing 'field_boosts' key")
        
        field_boosts = preset_data["field_boosts"]
        
        # Validate required fields
        required_fields = ["description", "title", "tags_canonical", "content"]
        missing = [f for f in required_fields if f not in field_boosts]
        if missing:
            raise ValueError(
                f"Preset {preset_name} missing required fields: {missing}"
            )
        
        # Convert to float and validate
        weights = {
            field: float(weight)
            for field, weight in field_boosts.items()
        }
        
        # Validate all weights are positive
        invalid = {f: w for f, w in weights.items() if w <= 0}
        if invalid:
            raise ValueError(
                f"Preset {preset_name} has invalid weights (must be > 0): {invalid}"
            )
        
        # Cache and return
        _preset_cache[preset_name] = weights
        
        logger.info(
            f"Loaded field weights preset '{preset_name}': "
            f"description={weights['description']}, "
            f"title={weights['title']}, "
            f"tags={weights['tags_canonical']}, "
            f"content={weights['content']}"
        )
        
        return weights
        
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in preset {preset_name}: {e}")
    except Exception as e:
        raise ValueError(f"Error loading preset {preset_name}: {e}")


def list_available_presets() -> list[str]:
    """
    List all available field weight presets.
    
    Returns:
        List of preset names (without .json extension)
    """
    if not WEIGHTS_DIR.exists():
        return []
    
    return [
        p.stem
        for p in WEIGHTS_DIR.glob("*.json")
        if p.is_file()
    ]


def get_preset_info(preset_name: str) -> Optional[Dict]:
    """
    Get full metadata for a preset (name, description, notes).
    
    Args:
        preset_name: Name of preset file (without .json extension)
        
    Returns:
        Full preset data dict, or None if not found
    """
    preset_path = WEIGHTS_DIR / f"{preset_name}.json"
    
    if not preset_path.exists():
        return None
    
    try:
        with open(preset_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error reading preset info for {preset_name}: {e}")
        return None


def clear_cache():
    """Clear the preset cache. Useful for testing or hot-reloading."""
    _preset_cache.clear()
