from typing import Optional

from pydantic import BaseModel, Field


class InventoryCreate(BaseModel):
    sku: str
    name: str
    quantity: int = 0
    threshold: int = 10
    unit: str = "pcs"


class InventoryUpdate(BaseModel):
    name: Optional[str] = None
    quantity: Optional[int] = None
    threshold: Optional[int] = None
    unit: Optional[str] = None


class InventoryAdjust(BaseModel):
    delta: int = Field(..., description="Add (+) or subtract (-) from current quantity")


class LoginRequest(BaseModel):
    email: str
    password: str


class AttendanceSessionCreate(BaseModel):
    school_id: int
    present: int
    total: int
    batch_name: str = "Main"
    notes: str = ""
    trainer_id: Optional[int] = None


class AlertRuleToggle(BaseModel):
    enabled: bool


class SnoozeRequest(BaseModel):
    hours: int = 24
