"""Authentication schemes for UTCP providers.

This module defines the authentication models supported by UTCP providers,
including API key authentication, basic authentication, and OAuth2.
"""

from typing import Literal, Optional, TypeAlias, Union

from pydantic import BaseModel, Field

class ApiKeyAuth(BaseModel):
    """Authentication using an API key.

    The key can be provided directly or sourced from an environment variable.
    Supports placement in headers, query parameters, or cookies.

    Attributes:
        auth_type: The authentication type identifier, always "api_key".
        api_key: The API key for authentication. Values starting with '$' or formatted as '${}' are
            treated as an injected variable from environment or configuration.
        var_name: The name of the header, query parameter, or cookie that
            contains the API key.
        location: Where to include the API key (header, query parameter, or cookie).
    """

    auth_type: Literal["api_key"] = "api_key"
    api_key: str = Field(..., description="The API key for authentication. Values starting with '$' or formatted as '${}' are treated as an injected variable from environment or configuration. This is the recommended way to provide API keys.")
    var_name: str = Field(
        "X-Api-Key", description="The name of the header, query parameter, cookie or other container for the API key."
    )
    location: Literal["header", "query", "cookie"] = Field(
        "header", description="Where to include the API key (header, query parameter, or cookie)."
    )


class BasicAuth(BaseModel):
    """Authentication using HTTP Basic Authentication.

    Uses the standard HTTP Basic Authentication scheme with username and password
    encoded in the Authorization header.

    Attributes:
        auth_type: The authentication type identifier, always "basic".
        username: The username for basic authentication. Recommended to use injected variables.
        password: The password for basic authentication. Recommended to use injected variables.
    """

    auth_type: Literal["basic"] = "basic"
    username: str = Field(..., description="The username for basic authentication.")
    password: str = Field(..., description="The password for basic authentication.")


class OAuth2Auth(BaseModel):
    """Authentication using OAuth2 client credentials flow.

    Implements the OAuth2 client credentials grant type for machine-to-machine
    authentication. The client automatically handles token acquisition and refresh.

    Attributes:
        auth_type: The authentication type identifier, always "oauth2".
        token_url: The URL endpoint to fetch the OAuth2 access token from. Recommended to use injected variables.
        client_id: The OAuth2 client identifier. Recommended to use injected variables.
        client_secret: The OAuth2 client secret. Recommended to use injected variables.
        scope: Optional scope parameter to limit the access token's permissions.
    """

    auth_type: Literal["oauth2"] = "oauth2"
    token_url: str = Field(..., description="The URL to fetch the OAuth2 token from.")
    client_id: str = Field(..., description="The OAuth2 client ID.")
    client_secret: str = Field(..., description="The OAuth2 client secret.")
    scope: Optional[str] = Field(None, description="The OAuth2 scope.")


Auth: TypeAlias = Union[ApiKeyAuth, BasicAuth, OAuth2Auth]
"""Type alias for all supported authentication schemes.

This union type encompasses all authentication methods supported by UTCP providers.
Use this type for type hints when accepting any authentication scheme.
"""
