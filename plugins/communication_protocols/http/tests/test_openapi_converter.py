import pytest
import aiohttp
import sys
from utcp_http.openapi_converter import OpenApiConverter
from utcp.data.utcp_manual import UtcpManual
from utcp.data.auth_implementations.api_key_auth import ApiKeyAuth


@pytest.mark.asyncio
async def test_openai_spec_conversion():
    """Tests that the OpenAI OpenAPI spec can be successfully converted into a UTCPManual."""
    url = "https://api.apis.guru/v2/specs/openai.com/1.2.0/openapi.json"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            openapi_spec = await response.json()

    converter = OpenApiConverter(openapi_spec, spec_url=url)
    utcp_manual = converter.convert()

    assert isinstance(utcp_manual, UtcpManual)
    assert len(utcp_manual.tools) > 0

    # Check a few things on a sample tool to ensure parsing is reasonable
    sample_tool = next((tool for tool in utcp_manual.tools if tool.name == "createChatCompletion"), None)
    assert sample_tool is not None
    assert sample_tool.tool_call_template.call_template_type == "http"
    assert sample_tool.tool_call_template.http_method == "POST"
    body_schema = sample_tool.inputs.properties.get('body')
    assert body_schema is not None


@pytest.mark.asyncio
async def test_openapi_converter_with_auth_tools():
    """Test OpenAPI converter with auth_tools parameter."""
    url = "https://api.apis.guru/v2/specs/openai.com/1.2.0/openapi.json"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            openapi_spec = await response.json()

    # Test with auth_tools parameter
    auth_tools = ApiKeyAuth(
        api_key="Bearer test-token",
        var_name="Authorization", 
        location="header"
    )
    
    converter = OpenApiConverter(openapi_spec, spec_url=url, auth_tools=auth_tools)
    utcp_manual = converter.convert()

    assert isinstance(utcp_manual, UtcpManual)
    assert len(utcp_manual.tools) > 0
    
    # Verify auth_tools is stored
    assert converter.auth_tools == auth_tools


def test_openapi_converter_parameter_examples():
    """Test that parameter examples are correctly extracted from OpenAPI spec."""
    # Create a minimal OpenAPI spec with parameter examples
    openapi_spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "Test API",
            "version": "1.0.0"
        },
        "paths": {
            "/users/{userId}": {
                "get": {
                    "operationId": "getUser",
                    "parameters": [
                        {
                            "name": "userId",
                            "in": "path",
                            "description": "ID of the user",
                            "required": True,
                            "schema": {
                                "type": "string"
                            },
                            "example": "user123"
                        },
                        {
                            "name": "includeDetails",
                            "in": "query",
                            "description": "Include detailed information",
                            "required": False,
                            "schema": {
                                "type": "boolean"
                            },
                            "examples": {
                                "trueExample": {
                                    "summary": "Include details",
                                    "value": True
                                },
                                "falseExample": {
                                    "summary": "Exclude details",
                                    "value": False
                                }
                            }
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Successful response",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "id": {"type": "string"},
                                            "name": {"type": "string"}
                                        }
                                    },
                                    "examples": {
                                        "userExample": {
                                            "summary": "Example user",
                                            "value": {
                                                "id": "user123",
                                                "name": "John Doe"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "/users": {
                "post": {
                    "operationId": "createUser",
                    "requestBody": {
                        "description": "User to create",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "email": {"type": "string"}
                                    },
                                    "required": ["name", "email"]
                                },
                                "examples": {
                                    "newUser": {
                                        "summary": "New user example",
                                        "value": {
                                            "name": "Jane Smith",
                                            "email": "jane@example.com"
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "description": "User created",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "id": {"type": "string"},
                                            "name": {"type": "string"},
                                            "email": {"type": "string"}
                                        }
                                    }
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
    
    # Test getUser tool - path and query parameter examples
    get_user_tool = next((tool for tool in manual.tools if tool.name == "getUser"), None)
    assert get_user_tool is not None
    
    # Check path parameter example
    user_id_param = get_user_tool.inputs.properties.get("userId")
    assert user_id_param is not None
    assert user_id_param.examples is not None
    assert "user123" in user_id_param.examples
    
    # Check query parameter examples
    include_details_param = get_user_tool.inputs.properties.get("includeDetails")
    assert include_details_param is not None
    assert include_details_param.examples is not None
    assert True in include_details_param.examples
    assert False in include_details_param.examples
    
    # Check response examples
    assert get_user_tool.outputs.examples is not None
    assert len(get_user_tool.outputs.examples) > 0
    example_value = get_user_tool.outputs.examples[0]
    assert example_value["id"] == "user123"
    assert example_value["name"] == "John Doe"
    
    # Test createUser tool - request body examples
    create_user_tool = next((tool for tool in manual.tools if tool.name == "createUser"), None)
    assert create_user_tool is not None
    
    body_param = create_user_tool.inputs.properties.get("body")
    assert body_param is not None
    assert body_param.examples is not None
    assert len(body_param.examples) > 0
    example_value = body_param.examples[0]
    assert example_value["name"] == "Jane Smith"
    assert example_value["email"] == "jane@example.com"


def test_openapi_converter_skips_unsupported_methods(capsys):
    """Operations with HTTP methods HttpCallTemplate cannot represent are skipped, not crashed on."""
    openapi_spec = {
        "openapi": "3.0.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/things": {
                "get": {
                    "operationId": "listThings",
                    "responses": {"200": {"description": "ok"}},
                },
                # OPTIONS/HEAD/TRACE are valid OpenAPI but not in the call template Literal
                "options": {
                    "operationId": "optionsThings",
                    "responses": {"200": {"description": "ok"}},
                },
                "head": {
                    "operationId": "headThings",
                    "responses": {"200": {"description": "ok"}},
                },
                "trace": {
                    "operationId": "traceThings",
                    "responses": {"200": {"description": "ok"}},
                },
            }
        },
    }

    converter = OpenApiConverter(openapi_spec)
    manual = converter.convert()

    tool_names = {tool.name for tool in manual.tools}
    assert tool_names == {"listThings"}

    # Unsupported operations must reach _create_tool and emit a skip warning,
    # not be silently dropped by the loop filter.
    stderr = capsys.readouterr().err
    assert "optionsThings" in stderr
    assert "headThings" in stderr
    assert "traceThings" in stderr


def test_openapi_converter_schema_level_examples_normalized():
    """Examples declared at the schema level (not the media type) are normalized into 'examples'."""
    openapi_spec = {
        "openapi": "3.0.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/widgets": {
                "post": {
                    "operationId": "createWidget",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"name": {"type": "string"}},
                                    # schema-level example, not a media-type 'examples' map
                                    "example": {"name": "Widget A"},
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"id": {"type": "string"}},
                                        "example": {"id": "w_1"},
                                    }
                                }
                            },
                        }
                    },
                }
            }
        },
    }

    converter = OpenApiConverter(openapi_spec)
    manual = converter.convert()

    tool = next((t for t in manual.tools if t.name == "createWidget"), None)
    assert tool is not None

    body_param = tool.inputs.properties.get("body")
    assert body_param is not None
    # schema-level example surfaces in the normalized 'examples' keyword
    assert body_param.examples == [{"name": "Widget A"}]
    # raw 'example' key must not leak through as an extra field
    assert "example" not in body_param.model_dump(by_alias=True)

    assert tool.outputs.examples == [{"id": "w_1"}]


def test_openapi_converter_array_form_schema_examples():
    """Array-form (JSON Schema / OpenAPI 3.1) schema 'examples' are preserved, not dropped."""
    openapi_spec = {
        "openapi": "3.1.0",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {
            "/gadgets": {
                "post": {
                    "operationId": "createGadget",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {"name": {"type": "string"}},
                                    # JSON Schema 'examples' keyword: a list of values
                                    "examples": [{"name": "Gadget A"}, {"name": "Gadget B"}],
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "string",
                                        "examples": ["ok", "done"],
                                    }
                                }
                            },
                        }
                    },
                }
            }
        },
    }

    converter = OpenApiConverter(openapi_spec)
    manual = converter.convert()

    tool = next((t for t in manual.tools if t.name == "createGadget"), None)
    assert tool is not None

    body_param = tool.inputs.properties.get("body")
    assert body_param is not None
    assert body_param.examples == [{"name": "Gadget A"}, {"name": "Gadget B"}]
    # examples surface in the normalized field on serialization
    assert body_param.model_dump(by_alias=True).get("examples") == [{"name": "Gadget A"}, {"name": "Gadget B"}]

    assert tool.outputs.examples == ["ok", "done"]
