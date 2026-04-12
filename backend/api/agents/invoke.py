from pydantic import BaseModel
from typing import Any, Dict, List, Optional


class InvokeRequest(BaseModel):
    """Unified invocation request.

    The four concerns map to four field groups:

    - **Identity**: always from auth (JWT/API key) -- never in the body.
    - **Operator**: *what* to run -- a Transform artifact (``transform_id``)
      or a named operator (``operator``).
    - **Knowledge**: scoping context -- the active workspace and any artifact IDs
      whose content should be injected as context for the operator.
    - **Input**: the actual data -- raw text (``input``) and/or structured
      arguments (``params``).
    """

    # -- Operator --------------------------------------------------------
    transform_id: Optional[str] = None      # artifact ID of a Transform artifact
    operator: Optional[str] = None          # named operator

    # -- Knowledge -------------------------------------------------------
    workspace_id: Optional[str] = None      # active workspace for scoping
    artifacts: Optional[List[str]] = None   # artifact IDs to inject as knowledge context

    # -- Input -----------------------------------------------------------
    input: Optional[str] = None             # raw text input
    params: Optional[Dict[str, Any]] = None # structured args
    operator_params: Optional[Dict[str, Any]] = None  # structured args for operators


class InvokeResponse(BaseModel):
    output: str


class InvokeResult:
    def __init__(self, output: str):
        self.output = output