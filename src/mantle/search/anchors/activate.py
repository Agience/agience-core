"""Activate — the native embedding interaction (canonical plan §7).

Present a vector → reconcile it to the native language (which grounded anchors
it activates) + its density-zoom layer, in one feed-forward shot. This is the
geometry core; the HTTP surface (``POST /artifacts/activate``) and the optional
nearest-neighbour search ("act") wrap it.

Non-authorizing: plaintext geometry only (canonical plan §1).
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from .reconciler import Reconciler
from .store import get_crosswalks, get_density_zoom, get_live_anchorset


def activate_vector(
    vec: Sequence[float] | np.ndarray,
    *,
    model_id: Optional[str] = None,
    top_anchors: int = 8,
) -> dict:
    """Return the native activation of ``vec``:

    ``{model_id, anchors:[{anchor_id,label,weight}], density:{layer,value},
       novel:bool}``. ``novel`` (L0) marks an anchor candidate (RG-flow growth).
    Empty/None when no AnchorSet is live. A foreign ``model_id`` is projected
    via the cross-walk registry (raises if no cross-walk is registered).
    """
    aset = get_live_anchorset()
    if aset is None or len(aset) == 0:
        return {"model_id": None, "anchors": [], "density": None, "novel": False}

    rec = Reconciler(aset, top_m=top_anchors, crosswalks=get_crosswalks())
    code = rec.to_native(vec, model_id=model_id)
    anchors = [
        {
            "anchor_id": aid,
            "label": aset.anchors[int(i)].label,
            "weight": round(float(w), 4),
        }
        for i, w, aid in zip(code.indices, code.weights, code.anchor_ids)
    ]

    density = None
    novel = False
    dz = get_density_zoom()
    if dz is not None:
        # Density is measured in the AnchorSet's space — re-walk if the input was
        # in a foreign model's gauge, to stay consistent with the reconcile.
        v = vec
        if model_id and model_id != aset.model_id:
            v = get_crosswalks().walk(vec, model_id, aset.model_id)
        layer, value = dz.layer(v)
        density = {"layer": layer, "value": round(float(value), 4)}
        novel = layer == "L0"

    return {"model_id": aset.model_id, "anchors": anchors, "density": density, "novel": novel}
