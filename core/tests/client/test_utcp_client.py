import pytest
import pytest_asyncio
import asyncio
import json
import os
import tempfile
from typing import Dict, Any, List, Optional
from unittest.mock import MagicMock, AsyncMock, patch
from pydantic import Field
from utcp.data.utcp_manual import UtcpManual
from utcp.data.register_manual_response import RegisterManualResult
from utcp.implementations.utcp_client_implementation import UtcpClientImplementation
from utcp.interfaces.communication_protocol import CommunicationProtocol
from utcp.utcp_client import UtcpClient
from utcp.data.utcp_client_config import UtcpClientConfig
from utcp.exceptions import UtcpVariableNotFound, UtcpSerializerValidationError
from utcp.interfaces.concurrent_tool_repository import ConcurrentToolRepository
from utcp.implementations.in_mem_tool_repository import InMemToolRepository
from utcp.interfaces.tool_search_strategy import ToolSearchStrategy
from utcp.implementations.tag_search import TagAndDescriptionWordMatchStrategy
from utcp.interfaces.variable_substitutor import VariableSubstitutor
from utcp.implementations.default_variable_substitutor import DefaultVariableSubstitutor
from utcp.data.tool import Tool, JsonSchema
from utcp.data.call_template import CallTemplate
from utcp_http.http_call_template import HttpCallTemplate
from utcp_cli.cli_call_template import CliCallTemplate
from utcp.data.auth_implementations import ApiKeyAuth


class MockToolRepository(ConcurrentToolRepository):
    """Mock tool repository for testing."""
    
    tool_repository_type: str = "mock"
    manuals: Dict[str, UtcpManual] = Field(default_factory=dict)
    manual_call_templates: Dict[str, CallTemplate] = Field(default_factory=dict)
    tools: Dict[str, Tool] = Field(default_factory=dict)

    async def save_manual(self, manual_call_template: CallTemplate, manual: UtcpManual) -> None:
        self.manual_call_templates[manual_call_template.name] = manual_call_template
        self.manuals[manual_call_template.name] = manual
        for tool in manual.tools:
            self.tools[tool.name] = tool

    async def remove_manual(self, manual_name: str) -> bool:
        if manual_name not in self.manuals:
            return False
        manual = self.manuals[manual_name]
        for tool in manual.tools:
            if tool.name in self.tools:
                del self.tools[tool.name]
        del self.manuals[manual_name]
        del self.manual_call_templates[manual_name]
        return True

    async def get_tool(self, tool_name: str) -> Optional[Tool]:
        return self.tools.get(tool_name)

    async def get_tools(self) -> List[Tool]:
        return list(self.tools.values())

    async def get_manual(self, manual_name: str) -> Optional[UtcpManual]:
        return self.manuals.get(manual_name)

    async def get_manual_call_template(self, manual_name: str) -> Optional[CallTemplate]:
        return self.manual_call_templates.get(manual_name)

    async def get_manual_call_templates(self) -> List[CallTemplate]:
        return list(self.manual_call_templates.values())

    async def remove_tool(self, tool_name: str) -> bool:
        if tool_name in self.tools:
            del self.tools[tool_name]
            return True
        return False

    async def get_tools_by_manual(self, manual_name: str) -> Optional[List[Tool]]:
        if manual_name in self.manuals:
            return self.manuals[manual_name].tools
        return None

    async def get_manuals(self) -> List[UtcpManual]:
        return list(self.manuals.values())


class MockToolSearchStrategy(ToolSearchStrategy):
    """Mock search strategy for testing."""
    
    tool_repository: ConcurrentToolRepository
    tool_search_strategy_type: str = "mock"

    async def search_tools(self, tool_repository: ConcurrentToolRepository, query: str, limit: int = 10, any_of_tags_required: Optional[List[str]] = None) -> List[Tool]:
        tools = await self.tool_repository.get_tools()
        # Simple mock search: return tools that contain the query in name or description
        matched_tools = [
            tool for tool in tools
            if query.lower() in tool.name.lower() or query.lower() in tool.description.lower()
        ]
        return matched_tools[:limit] if limit > 0 else matched_tools


class MockCommunicationProtocol(CommunicationProtocol):
    """Mock transport for testing."""
    
    def __init__(self, manual: UtcpManual = None, call_result: Any = "mock_result"):
        self.manual = manual or UtcpManual(utcp_version="1.0", manual_version="1.0", tools=[])
        self.call_result = call_result
        self.registered_manuals = []
        self.deregistered_manuals = []
        self.tool_calls = []

    async def register_manual(self, caller: 'UtcpClient', manual_call_template: CallTemplate) -> RegisterManualResult:
        self.registered_manuals.append(manual_call_template)
        return RegisterManualResult(manual_call_template=manual_call_template, manual=self.manual, success=True, errors=[])

    async def deregister_manual(self, caller: 'UtcpClient', manual_call_template: CallTemplate) -> None:
        self.deregistered_manuals.append(manual_call_template)

    async def call_tool(self, caller: 'UtcpClient', tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> Any:
        self.tool_calls.append((tool_name, tool_args, tool_call_template))
        return self.call_result

    async def call_tool_streaming(self, caller: 'UtcpClient', tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> Any:
        yield self.call_result


@pytest_asyncio.fixture
async def mock_tool_repository():
    """Create a mock tool repository."""
    return MockToolRepository()


@pytest_asyncio.fixture
async def mock_search_strategy(mock_tool_repository):
    """Create a mock search strategy."""
    return MockToolSearchStrategy(tool_repository=mock_tool_repository)


@pytest_asyncio.fixture
async def sample_tools():
    """Create sample tools for testing."""
    http_call_template = HttpCallTemplate(
        name="test_http_provider",
        url="https://api.example.com/tool",
        http_method="POST",
        call_template_type="http"
    )
    
    cli_call_template = CliCallTemplate(
        name="test_cli_provider",
        commands=[{"command": "echo UTCP_ARG_command_UTCP_END"}],
        call_template_type="cli"
    )
    
    return [
        Tool(
            name="http_tool",
            description="HTTP test tool",
            inputs=JsonSchema(
                type="object",
                properties={"param1": {"type": "string", "description": "Test parameter"}},
                required=["param1"]
            ),
            outputs=JsonSchema(
                type="object",
                properties={"result": {"type": "string", "description": "Test result"}}
            ),
            tags=["http", "test"],
            tool_call_template=http_call_template
        ),
        Tool(
            name="cli_tool",
            description="CLI test tool",
            inputs=JsonSchema(
                type="object",
                properties={"command": {"type": "string", "description": "Command to execute"}},
                required=["command"]
            ),
            outputs=JsonSchema(
                type="object",
                properties={"output": {"type": "string", "description": "Command output"}}
            ),
            tags=["cli", "test"],
            tool_call_template=cli_call_template
        )
    ]


@pytest.fixture
def isolated_communication_protocols(monkeypatch):
    """Isolates the CommunicationProtocol registry for each test."""
    monkeypatch.setattr(CommunicationProtocol, "communication_protocols", {})


@pytest_asyncio.fixture
async def utcp_client():
    """Fixture for UtcpClient."""
    return await UtcpClient.create()


class TestUtcpClient:
    """Test the UtcpClient implementation."""

    @pytest.mark.asyncio
    async def test_init(self, utcp_client):
        """Test UtcpClient initialization."""
        assert isinstance(utcp_client.config.tool_repository, InMemToolRepository)
        assert isinstance(utcp_client.config.tool_search_strategy, TagAndDescriptionWordMatchStrategy)
        assert isinstance(utcp_client.variable_substitutor, DefaultVariableSubstitutor)

    @pytest.mark.asyncio
    async def test_create_with_defaults(self):
        """Test creating UtcpClient with default parameters."""
        client = await UtcpClient.create()
        
        assert isinstance(client.config, UtcpClientConfig)
        assert isinstance(client.config.tool_repository, InMemToolRepository)
        assert isinstance(client.config.tool_search_strategy, TagAndDescriptionWordMatchStrategy)
        assert isinstance(client.variable_substitutor, DefaultVariableSubstitutor)

    @pytest.mark.asyncio
    async def test_create_with_dict_config(self):
        """Test creating UtcpClient with dictionary config."""
        config_dict = {
            "variables": {"TEST_VAR": "test_value"},
            "tool_repository": {
                "tool_repository_type": "in_memory"
            },
            "tool_search_strategy": {
                "tool_search_strategy_type": "tag_and_description_word_match"
            },
            "manual_call_templates": [],
            "post_processing": []
        }
        
        client = await UtcpClient.create(config=config_dict)
        assert client.config.variables == {"TEST_VAR": "test_value"}

    @pytest.mark.asyncio
    async def test_create_with_utcp_config(self):
        """Test creating UtcpClient with UtcpClientConfig object."""
        repo = InMemToolRepository()
        config = UtcpClientConfig(
            variables={"TEST_VAR": "test_value"},
            tool_repository=repo,
            tool_search_strategy=TagAndDescriptionWordMatchStrategy(),
            manual_call_templates=[],
            post_processing=[]
        )
        
        client = await UtcpClient.create(config=config)
        assert client.config is config

    @pytest.mark.asyncio
    async def test_register_manual(self, utcp_client, sample_tools, isolated_communication_protocols):
        """Test registering a manual."""
        http_call_template = HttpCallTemplate(
            name="test_manual",
            url="https://api.example.com/tool",
            http_method="POST",
            call_template_type="http"
        )
        
        # Mock the communication protocol
        manual = UtcpManual(utcp_version="1.0", manual_version="1.0", tools=sample_tools[:1])
        mock_protocol = MockCommunicationProtocol(manual)
        CommunicationProtocol.communication_protocols["http"] = mock_protocol
        
        result = await utcp_client.register_manual(http_call_template)
        
        assert result.success
        assert len(result.manual.tools) == 1
        assert result.manual.tools[0].name == "test_manual.http_tool"  # Should be prefixed
        
        registered_manual_template = mock_protocol.registered_manuals[0]
        assert registered_manual_template.name == "test_manual"
        
        # Verify tool was saved in repository
        saved_tool = await utcp_client.config.tool_repository.get_tool("test_manual.http_tool")
        assert saved_tool is not None

    @pytest.mark.asyncio
    async def test_register_manual_unsupported_type(self, utcp_client):
        """Test registering a manual with unsupported type."""
        
        with pytest.raises(Exception):
            call_template = HttpCallTemplate(
                name="test_manual",
                url="https://example.com",
                http_method="GET",
                call_template_type="unsupported_type"
            )
            await utcp_client.register_manual(call_template)

    @pytest.mark.asyncio
    async def test_register_manual_name_sanitization(self, utcp_client, sample_tools, isolated_communication_protocols):
        """Test that manual names are sanitized."""
        call_template = HttpCallTemplate(
            name="test-manual.with/special@chars",
            url="https://api.example.com/tool",
            http_method="POST",
            call_template_type="http"
        )
        
        manual = UtcpManual(utcp_version="1.0", manual_version="1.0", tools=sample_tools[:1])
        mock_protocol = MockCommunicationProtocol(manual)
        CommunicationProtocol.communication_protocols["http"] = mock_protocol
        
        result = await utcp_client.register_manual(call_template)
        
        # Name should be sanitized
        assert result.manual_call_template.name == "test_manual_with_special_chars"
        assert result.manual.tools[0].name == "test_manual_with_special_chars.http_tool"

    @pytest.mark.asyncio
    async def test_deregister_manual(self, utcp_client, sample_tools, isolated_communication_protocols):
        """Test deregistering a manual."""
        call_template = HttpCallTemplate(
            name="test_manual",
            url="https://api.example.com/tool",
            http_method="POST",
            call_template_type="http"
        )
        
        manual = UtcpManual(utcp_version="1.0", manual_version="1.0", tools=sample_tools[:1])
        mock_protocol = MockCommunicationProtocol(manual)
        CommunicationProtocol.communication_protocols["http"] = mock_protocol
        
        # First register the manual
        await utcp_client.register_manual(call_template)
        
        # Then deregister it
        result = await utcp_client.deregister_manual("test_manual")
        assert result is True
        
        # Verify manual was removed from repository
        saved_manual = await utcp_client.config.tool_repository.get_manual("test_manual")
        assert saved_manual is None
        
        # Verify protocol deregister was called
        assert len(mock_protocol.deregistered_manuals) == 1

    @pytest.mark.asyncio
    async def test_deregister_nonexistent_manual(self, utcp_client):
        """Test deregistering a non-existent manual."""
        client = utcp_client
        result = await client.deregister_manual("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_call_tool(self, utcp_client, sample_tools, isolated_communication_protocols):
        """Test calling a tool."""
        client = utcp_client
        call_template = HttpCallTemplate(
            name="test_manual",
            url="https://api.example.com/tool",
            http_method="POST",
            call_template_type="http"
        )
        
        manual = UtcpManual(utcp_version="1.0", manual_version="1.0", tools=sample_tools[:1])
        mock_protocol = MockCommunicationProtocol(manual, "test_result")
        CommunicationProtocol.communication_protocols["http"] = mock_protocol
        
        # Register the manual first
        await client.register_manual(call_template)
        
        # Call the tool
        result = await client.call_tool("test_manual.http_tool", {"param1": "value1"})
        
        assert result == "test_result"
        assert len(mock_protocol.tool_calls) == 1
        assert mock_protocol.tool_calls[0][0] == "test_manual.http_tool"
        assert mock_protocol.tool_calls[0][1] == {"param1": "value1"}

    @pytest.mark.asyncio
    async def test_call_tool_nonexistent_manual(self, utcp_client):
        """Test calling a tool with nonexistent manual."""
        client = utcp_client
        # This will fail at get_tool, not get_manual
        with pytest.raises(ValueError, match="Tool not found: nonexistent.tool"):
            await client.call_tool("nonexistent.tool", {"param": "value"})

    @pytest.mark.asyncio
    async def test_call_tool_nonexistent_tool(self, utcp_client, sample_tools, isolated_communication_protocols):
        """Test calling a nonexistent tool."""
        client = utcp_client
        call_template = HttpCallTemplate(
            name="test_manual",
            url="https://api.example.com/tool",
            http_method="POST",
            call_template_type="http"
        )
        
        manual = UtcpManual(utcp_version="1.0", manual_version="1.0", tools=sample_tools[:1])
        mock_protocol = MockCommunicationProtocol(manual)
        CommunicationProtocol.communication_protocols["http"] = mock_protocol
        
        # Register the manual first
        await client.register_manual(call_template)
        
        with pytest.raises(ValueError, match="Tool not found: test_manual.nonexistent"):
            await client.call_tool("test_manual.nonexistent", {"param": "value"})

    @pytest.mark.asyncio
    async def test_search_tools(self, utcp_client, sample_tools, isolated_communication_protocols):
        """Test searching for tools."""
        client = utcp_client
        # Clear any existing manuals from other tests to ensure a clean slate
        manual_names = [manual_call_template.name for manual_call_template in await client.config.tool_repository.get_manual_call_templates()]
        for name in manual_names:
            await client.deregister_manual(name)

        # Mock the communication protocols
        mock_http_protocol = MockCommunicationProtocol(UtcpManual(utcp_version="1.0", manual_version="1.0", tools=[sample_tools[0]]))
        mock_cli_protocol = MockCommunicationProtocol(UtcpManual(utcp_version="1.0", manual_version="1.0", tools=[sample_tools[1]]))
        CommunicationProtocol.communication_protocols["http"] = mock_http_protocol
        CommunicationProtocol.communication_protocols["cli"] = mock_cli_protocol

        # Register manuals to add tools to the repository
        await client.register_manual(sample_tools[0].tool_call_template)
        await client.register_manual(sample_tools[1].tool_call_template)

        # Search for tools
        results = await client.search_tools("http", limit=10)
        
        # Should find the HTTP tool
        assert len(results) == 2
        assert "http" in results[0].name.lower() or "http" in results[0].description.lower()

    @pytest.mark.asyncio
    async def test_get_required_variables_for_manual_and_tools(self, utcp_client, isolated_communication_protocols):
        """Test getting required variables for a manual."""
        client = utcp_client
        call_template = HttpCallTemplate(
            name="test_manual",
            url="https://api.example.com/$API_URL",
            http_method="POST",
            auth=ApiKeyAuth(api_key="$API_KEY", var_name="Authorization"),
            call_template_type="http"
        )
        
        # Mock the communication protocol to return an empty manual
        mock_protocol = MockCommunicationProtocol(UtcpManual(utcp_version="1.0", manual_version="1.0", tools=[]))
        CommunicationProtocol.communication_protocols["http"] = mock_protocol

        variables = await client.get_required_variables_for_manual_and_tools(call_template)
        
        # Using set because order doesn't matter
        assert set(variables) == {"test__manual_API_URL", "test__manual_API_KEY"}

    @pytest.mark.asyncio
    async def test_get_required_variables_for_registered_tool(self, utcp_client, sample_tools):
        """Test getting required variables for a registered tool."""
        client = utcp_client
        call_template = HttpCallTemplate(
            name="test_manual",
            url="https://api.example.com/$API_URL",
            http_method="POST",
            call_template_type="http"
        )
        
        tool = sample_tools[0]
        tool.name = "test_manual.http_tool"
        tool.tool_call_template = call_template
        
        # Add tool to repository
        manual = UtcpManual(utcp_version="1.0", manual_version="1.0", tools=[tool])
        await client.config.tool_repository.save_manual(call_template, manual)
        
        variables = await client.get_required_variables_for_registered_tool("test_manual.http_tool")
        
        assert variables == ["test__manual_API_URL"]

    @pytest.mark.asyncio
    async def test_get_required_variables_for_nonexistent_tool(self, utcp_client):
        """Test getting required variables for a nonexistent tool."""
        client = utcp_client
        with pytest.raises(ValueError, match="Tool not found: nonexistent.tool"):
            await client.get_required_variables_for_registered_tool("nonexistent.tool")


class TestUtcpClientManualCallTemplateLoading:
    """Test call template loading functionality."""

    @pytest.mark.asyncio
    async def test_load_manual_call_templates_from_file(self, isolated_communication_protocols):
        """Test loading call templates from a JSON file."""
        config_data = {
            "manual_call_templates": [
                {
                    "name": "http_template",
                    "call_template_type": "http",
                    "url": "https://api.example.com/tools",
                    "http_method": "GET"
                },
                {
                    "name": "cli_template",
                    "call_template_type": "cli",
                    "commands": [{"command": "echo UTCP_ARG_message_UTCP_END"}]
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_file = f.name
        
        try:
            # Mock the communication protocols
            mock_http_protocol = MockCommunicationProtocol()
            mock_cli_protocol = MockCommunicationProtocol()
            CommunicationProtocol.communication_protocols["http"] = mock_http_protocol
            CommunicationProtocol.communication_protocols["cli"] = mock_cli_protocol
            
            # Re-create client with the config file to load templates
            client = await UtcpClient.create(config=temp_file)

            assert len(client.config.manual_call_templates) == 2
            assert len(mock_http_protocol.registered_manuals) == 1
            assert len(mock_cli_protocol.registered_manuals) == 1
            
        finally:
            os.unlink(temp_file)

    @pytest.mark.asyncio
    async def test_load_manual_call_templates_file_not_found(self):
        """Test loading call templates from a non-existent file."""
        with pytest.raises(ValueError, match="Invalid config file"):
            await UtcpClient.create(config="nonexistent_file.json")

    @pytest.mark.asyncio
    async def test_load_manual_call_templates_invalid_json(self):
        """Test loading call templates from invalid JSON file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{\"invalid_json\": }")
            temp_file = f.name
        
        try:
            with pytest.raises(ValueError, match="Invalid config file"):
                await UtcpClient.create(config=temp_file)
        finally:
            os.unlink(temp_file)

    @pytest.mark.asyncio
    async def test_load_manual_call_templates_with_variables(self, isolated_communication_protocols):
        """Test loading call templates with variable substitution."""
        config_data = {
            "variables": {
                "http__template_BASE_URL": "https://api.example.com",
                "http__template_API_KEY": "secret_key"
            },
            "manual_call_templates": [
                {
                    "name": "http_template",
                    "call_template_type": "http",
                    "url": "$BASE_URL/tools",
                    "http_method": "GET",
                    "auth": {
                        "auth_type": "api_key",
                        "api_key": "$API_KEY",
                        "var_name": "Authorization"
                    }
                }
            ],
            "tool_repository": {
                "tool_repository_type": "in_memory"
            },
            "tool_search_strategy": {
                "tool_search_strategy_type": "tag_and_description_word_match"
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_file = f.name
        
        try:
            # Mock the communication protocol
            mock_protocol = MockCommunicationProtocol()
            CommunicationProtocol.communication_protocols["http"] = mock_protocol
            
            # Create client with config file
            client = await UtcpClient.create(config=temp_file)

            # Check that the registered call template has substituted values
            registered_template = mock_protocol.registered_manuals[0]
            assert registered_template.url == "https://api.example.com/tools"
            assert registered_template.auth.api_key == "secret_key"
            
        finally:
            os.unlink(temp_file)

    @pytest.mark.asyncio
    async def test_load_manual_call_templates_missing_variable(self):
        """Test loading call templates with missing variable."""
        config_data = {
            "manual_call_templates": [{
                "name": "http_template",
                "call_template_type": "http",
                "url": "$MISSING_VAR/tools",
                "http_method": "GET"
            }]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_file = f.name

        try:
            with pytest.raises(UtcpVariableNotFound, match="Variable http__template_MISSING_VAR referenced in provider configuration not found"):
                await UtcpClient.create(config=temp_file)
        finally:
            os.unlink(temp_file)


class TestUtcpClientCommunicationProtocols:
    """Test communication protocol-related functionality."""

    @pytest.mark.asyncio
    async def test_variable_substitution(self, utcp_client):
        """Test variable substitution in call templates."""
        client = utcp_client
        call_template = HttpCallTemplate(
            name="test_template",
            url="$BASE_URL/api",
            http_method="POST",
            auth=ApiKeyAuth(api_key="$API_KEY", var_name="Authorization")
        )
        
        # Set up variables with call template prefix
        client.config.variables = {
            "test__template_BASE_URL": "https://api.example.com",
            "test__template_API_KEY": "secret_key"
        }
        
        substituted_template = client._substitute_call_template_variables(call_template, "test_template")
        
        assert substituted_template.url == "https://api.example.com/api"
        assert substituted_template.auth.api_key == "secret_key"

    @pytest.mark.asyncio
    async def test_variable_substitution_missing_variable(self, utcp_client):
        """Test variable substitution with missing variable."""
        client = utcp_client
        call_template = HttpCallTemplate(
            name="test_template",
            url="$MISSING_VAR/api",
            http_method="POST"
        )
        
        with pytest.raises(UtcpVariableNotFound, match="Variable test__template_MISSING_VAR referenced in provider configuration not found"):
            client._substitute_call_template_variables(call_template, "test_template")


class TestUtcpClientEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_empty_call_template_file(self):
        """Test loading an empty call template file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"manual_call_templates": []}, f)  # Empty array
            temp_file = f.name

        try:
            client = await UtcpClient.create(config=temp_file)
            assert client.config.manual_call_templates == []
        finally:
            os.unlink(temp_file)

    @pytest.mark.asyncio
    async def test_register_manual_with_existing_name(self, utcp_client, isolated_communication_protocols):
        """Test registering a manual with an existing name should raise an error."""
        client = utcp_client
        template1 = HttpCallTemplate(
            name="duplicate_name",
            url="https://api.example1.com/tool",
            http_method="POST",
            call_template_type="http"
        )
        template2 = HttpCallTemplate(
            name="duplicate_name",
            url="https://api.example2.com/tool",
            http_method="GET",
            call_template_type="http"
        )
        
        mock_protocol = MockCommunicationProtocol()
        CommunicationProtocol.communication_protocols["http"] = mock_protocol
        
        # Register first manual
        await client.register_manual(template1)
        
        # Attempting to register second manual with same name should raise an error
        with pytest.raises(ValueError, match="Manual duplicate_name already registered"):
            await client.register_manual(template2)
        
        # Should still have the first manual
        saved_template = await client.config.tool_repository.get_manual_call_template("duplicate_name")
        assert saved_template.url == "https://api.example1.com/tool"
        assert saved_template.http_method == "POST"

    @pytest.mark.asyncio
    async def test_load_call_templates_wrong_format(self):
        """Test loading call templates with wrong JSON format (object instead of array)."""
        # This is not a valid config, `manual_call_templates` should be a list
        config_data = {
            "manual_call_templates": {
                "http_template": {
                    "call_template_type": "http",
                    "url": "https://api.example.com/tools",
                    "http_method": "GET"
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_file = f.name

        try:
            with pytest.raises(UtcpSerializerValidationError):
                await UtcpClient.create(config=temp_file)
        finally:
            os.unlink(temp_file)


class TestAllowedCommunicationProtocols:
    """Test allowed_communication_protocols restriction functionality."""

    @pytest.mark.asyncio
    async def test_call_tool_allowed_protocol(self, utcp_client, sample_tools, isolated_communication_protocols):
        """Test calling a tool when its protocol is in the allowed list."""
        client = utcp_client
        call_template = HttpCallTemplate(
            name="test_manual",
            url="https://api.example.com/tool",
            http_method="POST",
            call_template_type="http",
            allowed_communication_protocols=["http", "cli"]  # Allow both HTTP and CLI
        )
        
        manual = UtcpManual(utcp_version="1.0", manual_version="1.0", tools=sample_tools[:1])
        mock_protocol = MockCommunicationProtocol(manual, "test_result")
        CommunicationProtocol.communication_protocols["http"] = mock_protocol
        
        await client.register_manual(call_template)
        
        # Call should succeed since "http" is in allowed_communication_protocols
        result = await client.call_tool("test_manual.http_tool", {"param1": "value1"})
        assert result == "test_result"

    @pytest.mark.asyncio
    async def test_register_filters_disallowed_protocol_tools(self, utcp_client, sample_tools, isolated_communication_protocols):
        """Test that tools with disallowed protocols are filtered during registration."""
        client = utcp_client
        
        # Register HTTP manual that only allows "http" protocol
        http_call_template = HttpCallTemplate(
            name="http_manual",
            url="https://api.example.com/tool",
            http_method="POST",
            call_template_type="http",
            allowed_communication_protocols=["http"]  # Only allow HTTP
        )
        
        # Create a tool that uses CLI protocol (which is not allowed)
        cli_tool = Tool(
            name="cli_tool",
            description="CLI test tool",
            inputs=JsonSchema(
                type="object",
                properties={"command": {"type": "string", "description": "Command to execute"}},
                required=["command"]
            ),
            outputs=JsonSchema(
                type="object",
                properties={"output": {"type": "string", "description": "Command output"}}
            ),
            tags=["cli", "test"],
            tool_call_template=CliCallTemplate(
                name="cli_provider",
                commands=[{"command": "echo UTCP_ARG_command_UTCP_END"}],
                call_template_type="cli"
            )
        )
        
        manual = UtcpManual(utcp_version="1.0", manual_version="1.0", tools=[cli_tool])
        mock_http_protocol = MockCommunicationProtocol(manual)
        mock_cli_protocol = MockCommunicationProtocol()
        CommunicationProtocol.communication_protocols["http"] = mock_http_protocol
        CommunicationProtocol.communication_protocols["cli"] = mock_cli_protocol
        
        result = await client.register_manual(http_call_template)
        
        # CLI tool should be filtered out during registration
        assert len(result.manual.tools) == 0
        
        # Tool should not exist in repository
        tool = await client.config.tool_repository.get_tool("http_manual.cli_tool")
        assert tool is None

    @pytest.mark.asyncio
    async def test_call_tool_default_protocol_restriction(self, utcp_client, sample_tools, isolated_communication_protocols):
        """Test that when no allowed_communication_protocols is set, only the manual's protocol is allowed."""
        client = utcp_client
        
        # Register HTTP manual without explicit protocol restrictions
        # Default behavior: only HTTP tools should be allowed
        http_call_template = HttpCallTemplate(
            name="http_manual",
            url="https://api.example.com/tool",
            http_method="POST",
            call_template_type="http"
            # No allowed_communication_protocols set - defaults to ["http"]
        )
        
        # Create tools: one HTTP (should be registered), one CLI (should be filtered out)
        http_tool = Tool(
            name="http_tool",
            description="HTTP test tool",
            inputs=JsonSchema(type="object", properties={}),
            outputs=JsonSchema(type="object", properties={}),
            tool_call_template=HttpCallTemplate(
                name="http_provider",
                url="https://api.example.com/call",
                http_method="GET",
                call_template_type="http"
            )
        )
        cli_tool = Tool(
            name="cli_tool",
            description="CLI test tool",
            inputs=JsonSchema(type="object", properties={}),
            outputs=JsonSchema(type="object", properties={}),
            tool_call_template=CliCallTemplate(
                name="cli_provider",
                commands=[{"command": "echo test"}],
                call_template_type="cli"
            )
        )
        
        manual = UtcpManual(utcp_version="1.0", manual_version="1.0", tools=[http_tool, cli_tool])
        mock_http_protocol = MockCommunicationProtocol(manual, call_result="http_result")
        mock_cli_protocol = MockCommunicationProtocol()
        CommunicationProtocol.communication_protocols["http"] = mock_http_protocol
        CommunicationProtocol.communication_protocols["cli"] = mock_cli_protocol
        
        result = await client.register_manual(http_call_template)
        
        # Only HTTP tool should be registered, CLI tool should be filtered out
        assert len(result.manual.tools) == 1
        assert result.manual.tools[0].name == "http_manual.http_tool"
        
        # HTTP tool call should succeed
        call_result = await client.call_tool("http_manual.http_tool", {})
        assert call_result == "http_result"
        
        # CLI tool should not exist in repository
        cli_tool_in_repo = await client.config.tool_repository.get_tool("http_manual.cli_tool")
        assert cli_tool_in_repo is None

    @pytest.mark.asyncio
    async def test_register_with_multiple_allowed_protocols(self, utcp_client, sample_tools, isolated_communication_protocols):
        """Test registration with multiple allowed protocols allows all specified types."""
        client = utcp_client
        
        http_call_template = HttpCallTemplate(
            name="multi_protocol_manual",
            url="https://api.example.com/tool",
            http_method="POST",
            call_template_type="http",
            allowed_communication_protocols=["http", "cli"]  # Allow both
        )
        
        http_tool = Tool(
            name="http_tool",
            description="HTTP test tool",
            inputs=JsonSchema(type="object", properties={}),
            outputs=JsonSchema(type="object", properties={}),
            tool_call_template=HttpCallTemplate(
                name="http_provider",
                url="https://api.example.com/call",
                http_method="GET",
                call_template_type="http"
            )
        )
        cli_tool = Tool(
            name="cli_tool",
            description="CLI test tool",
            inputs=JsonSchema(type="object", properties={}),
            outputs=JsonSchema(type="object", properties={}),
            tool_call_template=CliCallTemplate(
                name="cli_provider",
                commands=[{"command": "echo test"}],
                call_template_type="cli"
            )
        )
        
        manual = UtcpManual(utcp_version="1.0", manual_version="1.0", tools=[http_tool, cli_tool])
        mock_http_protocol = MockCommunicationProtocol(manual, call_result="http_result")
        mock_cli_protocol = MockCommunicationProtocol(call_result="cli_result")
        CommunicationProtocol.communication_protocols["http"] = mock_http_protocol
        CommunicationProtocol.communication_protocols["cli"] = mock_cli_protocol
        
        result = await client.register_manual(http_call_template)
        
        # Both tools should be registered
        assert len(result.manual.tools) == 2
        tool_names = [t.name for t in result.manual.tools]
        assert "multi_protocol_manual.http_tool" in tool_names
        assert "multi_protocol_manual.cli_tool" in tool_names
        
        # Both tools should be callable
        http_result = await client.call_tool("multi_protocol_manual.http_tool", {})
        assert http_result == "http_result"
        
        cli_result = await client.call_tool("multi_protocol_manual.cli_tool", {})
        assert cli_result == "cli_result"

    @pytest.mark.asyncio
    async def test_call_tool_empty_allowed_protocols_defaults_to_manual_type(self, utcp_client, sample_tools, isolated_communication_protocols):
        """Test that empty allowed_communication_protocols defaults to manual's protocol type."""
        client = utcp_client
        
        http_call_template = HttpCallTemplate(
            name="http_manual",
            url="https://api.example.com/tool",
            http_method="POST",
            call_template_type="http",
            allowed_communication_protocols=[]  # Empty list defaults to ["http"]
        )
        
        cli_tool = Tool(
            name="cli_tool",
            description="CLI test tool",
            inputs=JsonSchema(type="object", properties={}),
            outputs=JsonSchema(type="object", properties={}),
            tool_call_template=CliCallTemplate(
                name="cli_provider",
                commands=[{"command": "echo test"}],
                call_template_type="cli"
            )
        )
        
        manual = UtcpManual(utcp_version="1.0", manual_version="1.0", tools=[cli_tool])
        mock_http_protocol = MockCommunicationProtocol(manual)
        mock_cli_protocol = MockCommunicationProtocol(call_result="cli_result")
        CommunicationProtocol.communication_protocols["http"] = mock_http_protocol
        CommunicationProtocol.communication_protocols["cli"] = mock_cli_protocol
        
        result = await client.register_manual(http_call_template)
        
        # CLI tool should be filtered out during registration
        assert len(result.manual.tools) == 0


class TestToolSerialization:
    """Test Tool and JsonSchema serialization."""

    def test_json_schema_serialization_by_alias(self):
        """Test that JsonSchema serializes using field aliases."""
        schema = JsonSchema(
            schema_="http://json-schema.org/draft-07/schema#",
            id_="test_schema",
            type="object",
            properties={
                "param": JsonSchema(type="string")
            }
        )

        serialized_schema = schema.model_dump()

        assert "$schema" in serialized_schema
        assert "$id" in serialized_schema
        assert serialized_schema["$schema"] == "http://json-schema.org/draft-07/schema#"
        assert serialized_schema["$id"] == "test_schema"

    def test_tool_serialization_by_alias(self, sample_tools):
        """Test that Tool serializes its JsonSchema fields by alias."""
        tool = sample_tools[0]
        tool.inputs.schema_ = "http://json-schema.org/draft-07/schema#"
        
        serialized_tool = tool.model_dump()
        
        assert "inputs" in serialized_tool
        assert "$schema" in serialized_tool["inputs"]
        assert serialized_tool["inputs"]["$schema"] == "http://json-schema.org/draft-07/schema#"
