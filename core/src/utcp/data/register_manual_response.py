from utcp.data.call_template import CallTemplate
from utcp.data.utcp_manual import UtcpManual
from pydantic import BaseModel
from typing import List

class RegisterManualResult(BaseModel):
    manual_call_template: CallTemplate
    manual: UtcpManual
    success: bool
    errors: List[str]
