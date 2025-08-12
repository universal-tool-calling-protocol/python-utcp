class GraphQLProvider(CallTemplate):
    """Provider configuration for GraphQL-based tools.

    Enables communication with GraphQL endpoints supporting queries, mutations,
    and subscriptions. Provides flexible query execution with custom headers
    and authentication.

    Attributes:
        type: Always "graphql" for GraphQL providers.
        url: The GraphQL endpoint URL.
        operation_type: The type of GraphQL operation (query, mutation, subscription).
        operation_name: Optional name for the GraphQL operation.
        auth: Optional authentication configuration.
        headers: Optional static headers to include in requests.
        header_fields: List of tool argument names to map to HTTP request headers.
    """

    type: Literal["graphql"] = "graphql"
    url: str
    operation_type: Literal["query", "mutation", "subscription"] = "query"
    operation_name: Optional[str] = None
    auth: Optional[Auth] = None
    headers: Optional[Dict[str, str]] = None
    header_fields: Optional[List[str]] = Field(default=None, description="List of input fields to be sent as request headers for the initial connection.")
