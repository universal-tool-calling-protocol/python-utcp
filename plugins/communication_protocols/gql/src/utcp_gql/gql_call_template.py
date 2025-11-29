from utcp.data.call_template import CallTemplate
from utcp.data.auth import Auth, AuthSerializer
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
import traceback
from typing import Dict, List, Optional, Literal
from pydantic import Field, field_serializer, field_validator

class GraphQLCallTemplate(CallTemplate):
    """Provider configuration for GraphQL-based tools.

    Enables communication with GraphQL endpoints supporting queries, mutations,
    and subscriptions. Provides flexible query execution with custom headers
    and authentication.

    For maximum flexibility, use the `query` field to provide a complete GraphQL
    query string with proper selection sets and variable types. This allows agents
    to call any existing GraphQL endpoint without limitations.

    Attributes:
        call_template_type: Always "graphql" for GraphQL providers.
        url: The GraphQL endpoint URL.
        operation_type: The type of GraphQL operation (query, mutation, subscription).
        operation_name: Optional name for the GraphQL operation.
        auth: Optional authentication configuration.
        headers: Optional static headers to include in requests.
        header_fields: List of tool argument names to map to HTTP request headers.
        query: Custom GraphQL query string with full control over selection sets
            and variable types. Example: 'query GetUser($id: ID!) { user(id: $id) { id name } }'
        variable_types: Map of variable names to GraphQL types for auto-generated queries.
            Example: {'id': 'ID!', 'limit': 'Int'}. Defaults to 'String' if not specified.

    Example:
        # Full flexibility with custom query
        template = GraphQLCallTemplate(
            url="https://api.example.com/graphql",
            query="query GetUser($id: ID!) { user(id: $id) { id name email } }",
        )

        # Auto-generation with proper types
        template = GraphQLCallTemplate(
            url="https://api.example.com/graphql",
            variable_types={"limit": "Int", "active": "Boolean"},
        )
    """

    call_template_type: Literal["graphql"] = "graphql"
    url: str
    operation_type: Literal["query", "mutation", "subscription"] = "query"
    operation_name: Optional[str] = None
    auth: Optional[Auth] = None
    headers: Optional[Dict[str, str]] = None
    header_fields: Optional[List[str]] = Field(default=None, description="List of input fields to be sent as request headers for the initial connection.")
    query: Optional[str] = Field(
        default=None,
        description="Custom GraphQL query/mutation string. Use $varName syntax for variables. "
                    "If provided, this takes precedence over auto-generation. "
                    "Example: 'query GetUser($id: ID!) { user(id: $id) { id name email } }'"
    )
    variable_types: Optional[Dict[str, str]] = Field(
        default=None,
        description="Map of variable names to GraphQL types for auto-generated queries. "
                    "Example: {'id': 'ID!', 'limit': 'Int', 'active': 'Boolean'}. "
                    "Defaults to 'String' if not specified."
    )

    @field_serializer("auth")
    def serialize_auth(self, auth: Optional[Auth]):
        if auth is None:
            return None
        return AuthSerializer().to_dict(auth)

    @field_validator("auth", mode="before")
    @classmethod
    def validate_auth(cls, v: Optional[Auth | dict]):
        if v is None:
            return None
        if isinstance(v, Auth):
            return v
        return AuthSerializer().validate_dict(v)


class GraphQLCallTemplateSerializer(Serializer[GraphQLCallTemplate]):
    def to_dict(self, obj: GraphQLCallTemplate) -> dict:
        return obj.model_dump()

    def validate_dict(self, data: dict) -> GraphQLCallTemplate:
        try:
            return GraphQLCallTemplate.model_validate(data)
        except Exception as e:
            raise UtcpSerializerValidationError(
                f"Invalid GraphQLCallTemplate: {e}\n{traceback.format_exc()}"
            )