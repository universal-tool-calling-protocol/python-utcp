from typing import Dict, Any, Optional, List, Literal, Union
from pydantic import BaseModel, Field
from utcp.shared.provider import (
    HttpProvider,
    CliProvider,
    WebSocketProvider,
    GRPCProvider,
    GraphQLProvider,
    TCPProvider,
    UDPProvider,
    StreamableHttpProvider,
    SSEProvider,
    WebRTCProvider,
    MCPProvider,
)

class ToolInputOutputSchema(BaseModel):
    type: str = Field(default="object")
    properties: Dict[str, Any] = Field(default_factory=dict)
    required: Optional[List[str]] = None
    description: Optional[str] = None
    title: Optional[str] = None

class Tool(BaseModel):
    name: str
    description: str = ""
    inputs: ToolInputOutputSchema = Field(default_factory=ToolInputOutputSchema)
    outputs: ToolInputOutputSchema = Field(default_factory=ToolInputOutputSchema)
    tags: List[str] = []
    provider: Optional[Union[
        HttpProvider,
        CliProvider,
        WebSocketProvider,
        GRPCProvider,
        GraphQLProvider,
        TCPProvider,
        UDPProvider,
        StreamableHttpProvider,
        SSEProvider,
        WebRTCProvider,
        MCPProvider,
    ]] = None
