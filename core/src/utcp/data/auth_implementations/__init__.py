from utcp.data.auth_implementations.api_key_auth import ApiKeyAuth, ApiKeyAuthSerializer
from utcp.data.auth_implementations.basic_auth import BasicAuth, BasicAuthSerializer
from utcp.data.auth_implementations.oauth2_auth import OAuth2Auth, OAuth2AuthSerializer
from utcp.discovery import register_auth

register_auth("oauth2", OAuth2AuthSerializer())
register_auth("basic", BasicAuthSerializer())
register_auth("api_key", ApiKeyAuthSerializer())

__all__ = [
    "ApiKeyAuth",
    "BasicAuth",
    "OAuth2Auth",
    "ApiKeyAuthSerializer",
    "BasicAuthSerializer",
    "OAuth2AuthSerializer"
]
