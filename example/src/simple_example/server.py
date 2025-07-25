from typing import List, Optional
from fastapi import FastAPI
from pydantic import BaseModel
from utcp.shared.provider import HttpProvider
from utcp.shared.tool import utcp_tool
from utcp.shared.utcp_manual import UtcpManual

class TestInput(BaseModel):
    value: str

class TestRequest(BaseModel):
    value: str
    arr: List[TestInput]

class TestResponse(BaseModel):
    received: str

__version__ = "1.0.0"
BASE_PATH = "http://localhost:8080"

app = FastAPI()

@app.get("/utcp", response_model=UtcpManual)
def get_utcp():
    return UtcpManual.create(version=__version__) 

@utcp_tool(tool_provider=HttpProvider(
    name="test_provider",
    url=f"{BASE_PATH}/test",
    http_method="POST"
))
@app.post("/test")
def test_endpoint(data: TestRequest) -> Optional[TestResponse]:
    """Test endpoint to receive a string value.
    
    Args:
        data (TestRequest): The input data containing a string value.
    Returns:
        TestResponse: A dictionary with the received value.
    """
    return TestResponse(received=data.value)
