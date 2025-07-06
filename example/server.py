from fastapi import FastAPI, Body
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union, Literal
from utcp.shared.provider import HttpProvider
from utcp.shared.tool import Tool
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

@app.post("/test")
def test_endpoint(data: TestRequest):
    return {"received": data.value}

# === Tools ===

test_tool = Tool(
    name="test_endpoint",
    description="A sample tool using HttpProvider",
    tags=["test", "http"],
    provider=HttpProvider(
        name="test_tool_provider",
        url="http://localhost:8080/test",
        http_method="POST",
        content_type="application/json"
    )
)
