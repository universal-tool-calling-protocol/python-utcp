class SSEProvider(CallTemplate):
    """Provider configuration for Server-Sent Events (SSE) tools.

    Enables real-time streaming of events from server to client using the
    Server-Sent Events protocol. Supports automatic reconnection and
    event type filtering. All tool arguments not mapped to URL body, headers
    or query pattern parameters are passed as query parameters using '?arg_name={arg_value}'.

    Attributes:
        type: Always "sse" for SSE providers.
        url: The SSE endpoint URL to connect to.
        event_type: Optional filter for specific event types. If None, all events are received.
        reconnect: Whether to automatically reconnect on connection loss.
        retry_timeout: Timeout in milliseconds before attempting reconnection.
        auth: Optional authentication configuration.
        headers: Optional static headers for the initial connection.
        body_field: Optional tool argument name to map to request body during connection.
        header_fields: List of tool argument names to map to HTTP headers during connection.
    """

    type: Literal["sse"] = "sse"
    url: str
    event_type: Optional[str] = None
    reconnect: bool = True
    retry_timeout: int = 30000  # Retry timeout in milliseconds if disconnected
    auth: Optional[Auth] = None
    headers: Optional[Dict[str, str]] = None
    body_field: Optional[str] = Field(default=None, description="The name of the single input field to be sent as the request body.")
    header_fields: Optional[List[str]] = Field(default=None, description="List of input fields to be sent as request headers for the initial connection.")
