from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class SwitchCreate(BaseModel):
    name: str

class SwitchStateUpdate(BaseModel):
    is_on: bool

class Switch(BaseModel):
    id: str
    name: str
    is_on: bool = False
    total_time_on_seconds: float = 0.0
    last_turned_on_at: Optional[datetime] = None