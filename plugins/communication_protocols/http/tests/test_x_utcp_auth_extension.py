"""Tests for x-utcp-auth OpenAPI extension support.

This module tests the custom x-utcp-auth extension that allows OpenAPI specifications
to include UTCP-specific authentication configuration directly in operations.
"""

import pytest
from utcp_http.openapi_converter import OpenApiConverter
from utcp_http.http_call_template import HttpCallTemplate
from utcp.data.auth_implementations.api_key_auth import ApiKeyAuth
from utcp.data.auth_implementations.basic_auth import BasicAuth
from utcp.data.auth_implementations.oauth2_auth import OAuth2Auth


def test_x_utcp_auth_api_key_extension():
    """Test that x-utcp-auth extension with API key auth is processed correctly."""
    openapi_spec = {
        "openapi": "3.0.1",
        "info": {"title": "Test API", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/protected": {
                "get": {
                    "operationId": "get_protected_data",
                    "summary": "Get Protected Data",
                    "x-utcp-auth": {
                        "auth_type": "api_key",
                        "var_name": "Authorization",
                        "location": "header"
                    },
                    "responses": {
                        "200": {
                            "description": "Success",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "string"}
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    
    converter = OpenApiConverter(openapi_spec)
    manual = converter.convert()
    
    assert len(manual.tools) == 1
    tool = manual.tools[0]
    
    # Check that auth was extracted from x-utcp-auth extension
    assert tool.tool_call_template.auth is not None
    assert isinstance(tool.tool_call_template.auth, ApiKeyAuth)
    assert tool.tool_call_template.auth.var_name == "Authorization"
    assert tool.tool_call_template.auth.location == "header"
    assert tool.tool_call_template.auth.api_key.startswith("${API_KEY_")


def test_x_utcp_auth_takes_precedence_over_standard_security():
    """Test that x-utcp-auth extension takes precedence over standard OpenAPI security."""
    openapi_spec = {
        "openapi": "3.0.1",
        "info": {"title": "Test API", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer"
                }
            }
        },
        "paths": {
            "/protected": {
                "get": {
                    "operationId": "get_protected_data",
                    "summary": "Get Protected Data",
                    "security": [{"bearerAuth": []}],
                    "x-utcp-auth": {
                        "auth_type": "api_key",
                        "var_name": "X-API-Key",
                        "location": "header"
                    },
                    "responses": {
                        "200": {
                            "description": "Success",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "string"}
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    
    converter = OpenApiConverter(openapi_spec)
    manual = converter.convert()
    
    assert len(manual.tools) == 1
    tool = manual.tools[0]
    
    # Should use x-utcp-auth, not the standard security scheme
    assert tool.tool_call_template.auth is not None
    assert isinstance(tool.tool_call_template.auth, ApiKeyAuth)
    assert tool.tool_call_template.auth.var_name == "X-API-Key"
    assert tool.tool_call_template.auth.location == "header"


def test_fallback_to_standard_security_when_no_x_utcp_auth():
    """Test that standard OpenAPI security is used when x-utcp-auth is not present."""
    openapi_spec = {
        "openapi": "3.0.1",
        "info": {"title": "Test API", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer"
                }
            }
        },
        "paths": {
            "/protected": {
                "get": {
                    "operationId": "get_protected_data",
                    "summary": "Get Protected Data",
                    "security": [{"bearerAuth": []}],
                    "responses": {
                        "200": {
                            "description": "Success",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "string"}
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    
    converter = OpenApiConverter(openapi_spec)
    manual = converter.convert()
    
    assert len(manual.tools) == 1
    tool = manual.tools[0]
    
    # Should use standard security scheme
    assert tool.tool_call_template.auth is not None
    assert isinstance(tool.tool_call_template.auth, ApiKeyAuth)
    assert tool.tool_call_template.auth.var_name == "Authorization"
    assert tool.tool_call_template.auth.location == "header"
    assert tool.tool_call_template.auth.api_key.startswith("Bearer ${API_KEY_")


def test_mixed_operations_with_and_without_x_utcp_auth():
    """Test OpenAPI spec with mixed operations - some with x-utcp-auth, some without."""
    openapi_spec = {
        "openapi": "3.0.1",
        "info": {"title": "Test API", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/public": {
                "get": {
                    "operationId": "get_public_data",
                    "summary": "Get Public Data",
                    "responses": {
                        "200": {
                            "description": "Success",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "string"}
                                }
                            }
                        }
                    }
                }
            },
            "/protected": {
                "get": {
                    "operationId": "get_protected_data",
                    "summary": "Get Protected Data",
                    "x-utcp-auth": {
                        "auth_type": "api_key",
                        "var_name": "Authorization",
                        "location": "header"
                    },
                    "responses": {
                        "200": {
                            "description": "Success",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "string"}
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    
    converter = OpenApiConverter(openapi_spec)
    manual = converter.convert()
    
    assert len(manual.tools) == 2
    
    # Find tools by name
    public_tool = next(t for t in manual.tools if t.name == "get_public_data")
    protected_tool = next(t for t in manual.tools if t.name == "get_protected_data")
    
    # Public tool should have no auth
    assert public_tool.tool_call_template.auth is None
    
    # Protected tool should have auth from x-utcp-auth
    assert protected_tool.tool_call_template.auth is not None
    assert isinstance(protected_tool.tool_call_template.auth, ApiKeyAuth)
    assert protected_tool.tool_call_template.auth.var_name == "Authorization"
    assert protected_tool.tool_call_template.auth.location == "header"


def test_auth_inheritance_from_manual_call_template():
    """Test that tools inherit authentication from manual call template."""
    openapi_spec = {
        "openapi": "3.0.1",
        "info": {"title": "Test API", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/data": {
                "get": {
                    "operationId": "get_data",
                    "summary": "Get Data",
                    "responses": {
                        "200": {
                            "description": "Success",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "string"}
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    
    # Manual call template with auth
    manual_auth = ApiKeyAuth(
        api_key="Bearer token-123",
        var_name="Authorization",
        location="header"
    )
    
    converter = OpenApiConverter(openapi_spec, inherited_auth=manual_auth)
    manual = converter.convert()
    
    assert len(manual.tools) == 1
    tool = manual.tools[0]
    
    # Tool should inherit auth from manual call template
    assert tool.tool_call_template.auth is not None
    assert isinstance(tool.tool_call_template.auth, ApiKeyAuth)
    assert tool.tool_call_template.auth.api_key == "Bearer token-123"
    assert tool.tool_call_template.auth.var_name == "Authorization"
    assert tool.tool_call_template.auth.location == "header"


def test_x_utcp_auth_overrides_inherited_auth():
    """Test that x-utcp-auth extension overrides inherited auth from manual call template."""
    openapi_spec = {
        "openapi": "3.0.1",
        "info": {"title": "Test API", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/data": {
                "get": {
                    "operationId": "get_data",
                    "summary": "Get Data",
                    "x-utcp-auth": {
                        "auth_type": "api_key",
                        "var_name": "X-Custom-Key",
                        "location": "header"
                    },
                    "responses": {
                        "200": {
                            "description": "Success",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "string"}
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    
    # Manual call template with different auth
    manual_auth = ApiKeyAuth(
        api_key="Bearer token-123",
        var_name="Authorization", 
        location="header"
    )
    
    converter = OpenApiConverter(openapi_spec, inherited_auth=manual_auth)
    manual = converter.convert()
    
    assert len(manual.tools) == 1
    tool = manual.tools[0]
    
    # Tool should use x-utcp-auth, not inherited auth
    assert tool.tool_call_template.auth is not None
    assert isinstance(tool.tool_call_template.auth, ApiKeyAuth)
    assert tool.tool_call_template.auth.var_name == "X-Custom-Key"
    assert tool.tool_call_template.auth.location == "header"
    # Should generate placeholder, not use inherited value
    assert tool.tool_call_template.auth.api_key.startswith("${API_KEY_")


def test_no_auth_inheritance_when_manual_has_no_auth():
    """Test that no auth is applied when manual call template has no auth."""
    openapi_spec = {
        "openapi": "3.0.1",
        "info": {"title": "Test API", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "paths": {
            "/data": {
                "get": {
                    "operationId": "get_data",
                    "summary": "Get Data",
                    "responses": {
                        "200": {
                            "description": "Success",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "string"}
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    
    converter = OpenApiConverter(openapi_spec, inherited_auth=None)
    manual = converter.convert()
    
    assert len(manual.tools) == 1
    tool = manual.tools[0]
    
    # Tool should have no auth
    assert tool.tool_call_template.auth is None
