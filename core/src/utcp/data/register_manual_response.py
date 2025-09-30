from utcp.data.call_template import CallTemplate
from utcp.data.utcp_manual import UtcpManual
from pydantic import BaseModel, Field
from typing import List

class RegisterManualResult(BaseModel):
    """REQUIRED
    Result of a manual registration.

    Attributes:
        manual_call_template: The call template of the registered manual.
        manual: The registered manual.
        success: Whether the registration was successful.
        errors: List of error messages if registration failed.
    """
    manual_call_template: CallTemplate
    manual: UtcpManual
    success: bool
    errors: List[str] = Field(default_factory=list)
