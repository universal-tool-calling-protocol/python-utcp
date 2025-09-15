"""
Tests for auth_tools functionality in OpenAPI converter.

Tests the new auth_tools feature that allows manual call templates to provide
authentication configuration for generated tools, with compatibility checking
against OpenAPI security schemes.
"""

import pytest
from utcp_http.openapi_converter import OpenApiConverter
from utcp.data.auth_implementations.api_key_auth import ApiKeyAuth
from utcp.data.auth_implementations.basic_auth import BasicAuth


def test_compatible_api_key_auth():
    """Test auth_tools with compatible API key authentication."""
    openapi_spec = {
        "swagger": "2.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "host": "api.test.com",
        "securityDefinitions": {
            "api_key": {
                "type": "apiKey",
                "name": "Authorization",
                "in": "header"
            }
        },
        "paths": {
            "/protected": {
                "get": {
                    "operationId": "getProtected",
                    "security": [{"api_key": []}],
                    "responses": {"200": {"description": "success"}}
                }
            }
        }
    }
    
    # Compatible auth_tools (same header name and location)
    auth_tools = ApiKeyAuth(
        api_key="Bearer token-123",
        var_name="Authorization",
        location="header"
    )
    
    converter = OpenApiConverter(openapi_spec, auth_tools=auth_tools)
    manual = converter.convert()
    
    assert len(manual.tools) == 1
    tool = manual.tools[0]
    
    # Should use auth_tools values since they're compatible
    assert tool.tool_call_template.auth is not None
    assert isinstance(tool.tool_call_template.auth, ApiKeyAuth)
    assert tool.tool_call_template.auth.api_key == "Bearer token-123"
    assert tool.tool_call_template.auth.var_name == "Authorization"
    assert tool.tool_call_template.auth.location == "header"


def test_incompatible_api_key_auth():
    """Test auth_tools with incompatible API key authentication."""
    openapi_spec = {
        "swagger": "2.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "host": "api.test.com",
        "securityDefinitions": {
            "custom_key": {
                "type": "apiKey",
                "name": "X-API-Key",  # Different header name
                "in": "header"
            }
        },
        "paths": {
            "/protected": {
                "get": {
                    "operationId": "getProtected",
                    "security": [{"custom_key": []}],
                    "responses": {"200": {"description": "success"}}
                }
            }
        }
    }
    
    # Incompatible auth_tools (different header name)
    auth_tools = ApiKeyAuth(
        api_key="Bearer token-123",
        var_name="Authorization",  # Different from OpenAPI
        location="header"
    )
    
    converter = OpenApiConverter(openapi_spec, auth_tools=auth_tools)
    manual = converter.convert()
    
    assert len(manual.tools) == 1
    tool = manual.tools[0]
    
    # Should use OpenAPI scheme with placeholder since incompatible
    assert tool.tool_call_template.auth is not None
    assert isinstance(tool.tool_call_template.auth, ApiKeyAuth)
    assert tool.tool_call_template.auth.api_key.startswith("${")  # Placeholder
    assert tool.tool_call_template.auth.var_name == "X-API-Key"  # From OpenAPI
    assert tool.tool_call_template.auth.location == "header"


def test_case_insensitive_header_matching():
    """Test that header name matching is case-insensitive."""
    openapi_spec = {
        "swagger": "2.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "host": "api.test.com",
        "securityDefinitions": {
            "api_key": {
                "type": "apiKey",
                "name": "authorization",  # lowercase
                "in": "header"
            }
        },
        "paths": {
            "/protected": {
                "get": {
                    "operationId": "getProtected",
                    "security": [{"api_key": []}],
                    "responses": {"200": {"description": "success"}}
                }
            }
        }
    }
    
    # auth_tools with different case
    auth_tools = ApiKeyAuth(
        api_key="Bearer token-123",
        var_name="Authorization",  # uppercase
        location="header"
    )
    
    converter = OpenApiConverter(openapi_spec, auth_tools=auth_tools)
    manual = converter.convert()
    
    tool = manual.tools[0]
    
    # Should be compatible despite case difference
    assert tool.tool_call_template.auth.api_key == "Bearer token-123"


def test_different_auth_types_incompatible():
    """Test that different auth types are incompatible."""
    openapi_spec = {
        "swagger": "2.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "host": "api.test.com",
        "securityDefinitions": {
            "basic_auth": {
                "type": "basic"
            }
        },
        "paths": {
            "/protected": {
                "get": {
                    "operationId": "getProtected",
                    "security": [{"basic_auth": []}],
                    "responses": {"200": {"description": "success"}}
                }
            }
        }
    }
    
    # Different auth type (API key vs Basic)
    auth_tools = ApiKeyAuth(
        api_key="Bearer token-123",
        var_name="Authorization",
        location="header"
    )
    
    converter = OpenApiConverter(openapi_spec, auth_tools=auth_tools)
    manual = converter.convert()
    
    tool = manual.tools[0]
    
    # Should use OpenAPI scheme since types don't match
    assert isinstance(tool.tool_call_template.auth, BasicAuth)
    assert tool.tool_call_template.auth.username.startswith("${")  # Placeholder


def test_public_endpoint_no_auth():
    """Test that public endpoints remain public regardless of auth_tools."""
    openapi_spec = {
        "swagger": "2.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "host": "api.test.com",
        "paths": {
            "/public": {
                "get": {
                    "operationId": "getPublic",
                    # No security field - public endpoint
                    "responses": {"200": {"description": "success"}}
                }
            }
        }
    }
    
    auth_tools = ApiKeyAuth(
        api_key="Bearer token-123",
        var_name="Authorization",
        location="header"
    )
    
    converter = OpenApiConverter(openapi_spec, auth_tools=auth_tools)
    manual = converter.convert()
    
    tool = manual.tools[0]
    
    # Should have no auth since endpoint is public
    assert tool.tool_call_template.auth is None


def test_no_auth_tools_uses_openapi_scheme():
    """Test fallback to OpenAPI scheme when no auth_tools provided."""
    openapi_spec = {
        "swagger": "2.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "host": "api.test.com",
        "securityDefinitions": {
            "api_key": {
                "type": "apiKey",
                "name": "X-API-Key",
                "in": "header"
            }
        },
        "paths": {
            "/protected": {
                "get": {
                    "operationId": "getProtected",
                    "security": [{"api_key": []}],
                    "responses": {"200": {"description": "success"}}
                }
            }
        }
    }
    
    # No auth_tools provided
    converter = OpenApiConverter(openapi_spec, auth_tools=None)
    manual = converter.convert()
    
    tool = manual.tools[0]
    
    # Should use OpenAPI scheme with placeholder
    assert tool.tool_call_template.auth is not None
    assert isinstance(tool.tool_call_template.auth, ApiKeyAuth)
    assert tool.tool_call_template.auth.api_key.startswith("${")
    assert tool.tool_call_template.auth.var_name == "X-API-Key"
