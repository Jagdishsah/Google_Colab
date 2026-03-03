from pydantic import BaseModel, Field, field_validator
from datetime import date
from typing import Optional, List

class LedgerEntry(BaseModel):
    Date: date
    Type: str
    Category: str
    Amount: float
    Status: str = "Cleared"
    Due_Date: Optional[date] = None
    Ref_ID: str = ""
    Description: str = ""
    Is_Non_Cash: bool = False
    Dispute_Note: str = ""
    Fiscal_Year: str

    @field_validator('Fiscal_Year')
    @classmethod
    def validate_fiscal(cls, v):
        if "/" not in str(v): return "2025/2026" # Default if broken
        return v

class HoldingEntry(BaseModel):
    Symbol: str
    Total_Qty: float = Field(ge=0)
    Pledged_Qty: float = Field(default=0, ge=0)
    LTP: float = Field(default=0, ge=0)
    Haircut: float = Field(default=0, ge=0)

    @field_validator('Symbol')
    @classmethod
    def upper_sym(cls, v): return v.upper()

class TransactionEntry(BaseModel):
    Date: date
    Stock: str
    Type: str
    Medium: str
    Amount: float
    Charge: float = 0.0
    Remark: str = ""
    Reference: str = ""

class ActivityLogEntry(BaseModel):
    Timestamp: str
    Category: str
    Symbol: str
    Action: str
    Details: str
    Amount: float