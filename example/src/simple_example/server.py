from fastapi import FastAPI
from pydantic import BaseModel
from utcp.shared.provider import HttpProvider
from utcp.shared.tool import utcp_tool
from utcp.shared.utcp_manual import UtcpManual


class TestRequest(BaseModel):
    value: str

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
def test_endpoint(data: TestRequest):
    return {"received": data.value}
