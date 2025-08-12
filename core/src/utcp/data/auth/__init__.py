from utcp.data.auth.auth import Auth, AuthSerializer
from utcp.data.auth.api_key_auth import ApiKeyAuth, ApiKeyAuthSerializer
from utcp.data.auth.basic_auth import BasicAuth, BasicAuthSerializer
from utcp.data.auth.oauth2_auth import OAuth2Auth, OAuth2AuthSerializer
from utcp.discovery import register_auth

register_auth("oauth2", OAuth2AuthSerializer())
register_auth("basic", BasicAuthSerializer())
register_auth("api_key", ApiKeyAuthSerializer())

__all__ = [
    "Auth",
    "ApiKeyAuth",
    "BasicAuth",
    "OAuth2Auth",
    "AuthSerializer",
    "ApiKeyAuthSerializer",
    "BasicAuthSerializer",
    "OAuth2AuthSerializer"
]
