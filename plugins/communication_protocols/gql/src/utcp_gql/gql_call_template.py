from utcp.data.call_template import CallTemplate, CallTemplateSerializer
from utcp.data.auth import Auth, AuthSerializer
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
import traceback
from typing import Dict, List, Optional, Literal
from pydantic import Field, field_serializer, field_validator

class GraphQLProvider(CallTemplate):
    """Provider configuration for GraphQL-based tools.

    Enables communication with GraphQL endpoints supporting queries, mutations,
    and subscriptions. Provides flexible query execution with custom headers
    and authentication.

    Attributes:
        call_template_type: Always "graphql" for GraphQL providers.
        url: The GraphQL endpoint URL.
        operation_type: The type of GraphQL operation (query, mutation, subscription).
        operation_name: Optional name for the GraphQL operation.
        auth: Optional authentication configuration.
        headers: Optional static headers to include in requests.
        header_fields: List of tool argument names to map to HTTP request headers.
    """

    call_template_type: Literal["graphql"] = "graphql"
    url: str
    operation_type: Literal["query", "mutation", "subscription"] = "query"
    operation_name: Optional[str] = None
    auth: Optional[Auth] = None
    headers: Optional[Dict[str, str]] = None
    header_fields: Optional[List[str]] = Field(default=None, description="List of input fields to be sent as request headers for the initial connection.")

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


class GraphQLProviderSerializer(Serializer[GraphQLProvider]):
    def to_dict(self, obj: GraphQLProvider) -> dict:
        return obj.model_dump()

    def validate_dict(self, data: dict) -> GraphQLProvider:
        try:
            return GraphQLProvider.model_validate(data)
        except Exception as e:
            raise UtcpSerializerValidationError(
                f"Invalid GraphQLProvider: {e}\n{traceback.format_exc()}"
            )
