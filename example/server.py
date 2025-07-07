from fastapi import FastAPI, Body
from pydantic import BaseModel, Field, TypeAdapter
from typing import List, Dict, Any, Optional, Union, Literal
from utcp.shared.provider import HttpProvider
from utcp.shared.tool import Tool, utcp_tool
from utcp.shared.utcp_manual import UtcpManual

app = FastAPI()

__version__ = "1.0.0"

# === Endpoints ===

@app.get("/utcp", response_model=UtcpManual)
def get_utcp():
    return UtcpManual(
        version=__version__,
        tools=[test_tool]
    )

class TestRequest(BaseModel):
    value: str

@utcp_tool(title="Test Endpoint", description="A sample endpoint for testing purposes")
@app.post("/test")
def test_endpoint(data: TestRequest):
    return {"received": data.value}

# === Tools ===

test_tool = Tool(
    name="test_endpoint",
    description="A sample tool using HttpProvider",
    tags=["test", "http"],
    inputs=test_endpoint.input(),
    outputs=test_endpoint.output(),
    provider=HttpProvider(
        name="test_tool_provider",
        url="http://localhost:8080/test",
        http_method="POST",
        body_field="body",
        content_type="application/json"
    )
)

