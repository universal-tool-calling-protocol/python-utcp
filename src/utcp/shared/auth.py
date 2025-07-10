from typing import Literal, Optional, TypeAlias, Union

from pydantic import BaseModel, Field

class ApiKeyAuth(BaseModel):
    """Authentication using an API key.

    The key can be provided directly or sourced from an environment variable.
    """

    auth_type: Literal["api_key"] = "api_key"
    api_key: str = Field(..., description="The API key for authentication. If it starts with '$', it is treated as an injected variable. This is the recommended way to provide API keys.")
    var_name: str = Field(
        "X-Api-Key", description="The name of the header, query parameter, cookie or other container for the API key."
    )
    location: Literal["header", "query", "cookie"] = Field(
        "header", description="Where to include the API key (header, query parameter, or cookie)."
    )


class BasicAuth(BaseModel):
    """Authentication using a username and password."""

    auth_type: Literal["basic"] = "basic"
    username: str = Field(..., description="The username for basic authentication.")
    password: str = Field(..., description="The password for basic authentication.")


class OAuth2Auth(BaseModel):
    """Authentication using OAuth2."""

    auth_type: Literal["oauth2"] = "oauth2"
    token_url: str = Field(..., description="The URL to fetch the OAuth2 token from.")
    client_id: str = Field(..., description="The OAuth2 client ID.")
    client_secret: str = Field(..., description="The OAuth2 client secret.")
    scope: Optional[str] = Field(None, description="The OAuth2 scope.")


Auth: TypeAlias = Union[ApiKeyAuth, BasicAuth, OAuth2Auth]
