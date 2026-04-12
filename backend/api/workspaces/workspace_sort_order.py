from pydantic import BaseModel
class SortOrderRequest(BaseModel):
    ordered_ids: list[str]
    version: int | None = None

class SortOrderResponse(BaseModel):
    ok: bool
    version: int

class MoveRequest(BaseModel):
    id: str
    before_id: str | None = None
    after_id: str | None = None
    version: int | None = None
