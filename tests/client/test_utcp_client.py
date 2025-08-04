import pytest
import pytest_asyncio
import asyncio
import json
import os
import tempfile
from typing import Dict, Any, List, Optional
from unittest.mock import MagicMock, AsyncMock, patch

from utcp.client.utcp_client import UtcpClient, UtcpClientInterface
from utcp.client.utcp_client_config import UtcpClientConfig, UtcpVariableNotFound
from utcp.client.tool_repository import ToolRepository
from utcp.client.tool_repositories.in_mem_tool_repository import InMemToolRepository
from utcp.client.tool_search_strategy import ToolSearchStrategy
from utcp.client.tool_search_strategies.tag_search import TagSearchStrategy
from utcp.client.variable_substitutor import VariableSubstitutor, DefaultVariableSubstitutor
from utcp.shared.tool import Tool, ToolInputOutputSchema
from utcp.shared.provider import (
    Provider, HttpProvider, CliProvider, MCPProvider, TextProvider,
    McpConfig, McpStdioServer, McpHttpServer
)
from utcp.shared.auth import ApiKeyAuth, BasicAuth, OAuth2Auth


class MockToolRepository(ToolRepository):
    """Mock tool repository for testing."""
    
    def __init__(self):
        self.providers: Dict[str, Provider] = {}
        self.tools: Dict[str, Tool] = {}
        self.provider_tools: Dict[str, List[Tool]] = {}

    async def save_provider_with_tools(self, provider: Provider, tools: List[Tool]) -> None:
        self.providers[provider.name] = provider
        self.provider_tools[provider.name] = tools
        for tool in tools:
            self.tools[tool.name] = tool

    async def remove_provider(self, provider_name: str) -> None:
        if provider_name not in self.providers:
            raise ValueError(f"Provider not found: {provider_name}")
        # Remove tools associated with provider
        if provider_name in self.provider_tools:
            for tool in self.provider_tools[provider_name]:
                if tool.name in self.tools:
                    del self.tools[tool.name]
            del self.provider_tools[provider_name]
        del self.providers[provider_name]

    async def remove_tool(self, tool_name: str) -> None:
        if tool_name not in self.tools:
            raise ValueError(f"Tool not found: {tool_name}")
        del self.tools[tool_name]
        # Remove from provider_tools
        for provider_name, tools in self.provider_tools.items():
            self.provider_tools[provider_name] = [t for t in tools if t.name != tool_name]

    async def get_tool(self, tool_name: str) -> Optional[Tool]:
        return self.tools.get(tool_name)

    async def get_tools(self) -> List[Tool]:
        return list(self.tools.values())

    async def get_tools_by_provider(self, provider_name: str) -> Optional[List[Tool]]:
        return self.provider_tools.get(provider_name)

    async def get_provider(self, provider_name: str) -> Optional[Provider]:
        return self.providers.get(provider_name)

    async def get_providers(self) -> List[Provider]:
        return list(self.providers.values())


class MockToolSearchStrategy(ToolSearchStrategy):
    """Mock search strategy for testing."""
    
    def __init__(self, tool_repository: ToolRepository):
        self.tool_repository = tool_repository

    async def search_tools(self, query: str, limit: int = 10) -> List[Tool]:
        tools = await self.tool_repository.get_tools()
        # Simple mock search: return tools that contain the query in name or description
        matched_tools = [
            tool for tool in tools
            if query.lower() in tool.name.lower() or query.lower() in tool.description.lower()
        ]
        return matched_tools[:limit] if limit > 0 else matched_tools


class MockTransport:
    """Mock transport for testing."""
    
    def __init__(self, tools: List[Tool] = None, call_result: Any = "mock_result"):
        self.tools = tools or []
        self.call_result = call_result
        self.registered_providers = []
        self.deregistered_providers = []
        self.tool_calls = []

    async def register_tool_provider(self, provider: Provider) -> List[Tool]:
        self.registered_providers.append(provider)
        return self.tools

    async def deregister_tool_provider(self, provider: Provider) -> None:
        self.deregistered_providers.append(provider)

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], tool_provider: Provider) -> Any:
        self.tool_calls.append((tool_name, arguments, tool_provider))
        return self.call_result


@pytest_asyncio.fixture
async def mock_tool_repository():
    """Create a mock tool repository."""
    return MockToolRepository()


@pytest_asyncio.fixture
async def mock_search_strategy(mock_tool_repository):
    """Create a mock search strategy."""
    return MockToolSearchStrategy(mock_tool_repository)


@pytest_asyncio.fixture
async def sample_tools():
    """Create sample tools for testing."""
    http_provider = HttpProvider(
        name="test_http_provider",
        url="https://api.example.com/tool",
        http_method="POST"
    )
    
    cli_provider = CliProvider(
        name="test_cli_provider",
        command_name="echo"
    )
    
    return [
        Tool(
            name="http_tool",
            description="HTTP test tool",
            inputs=ToolInputOutputSchema(
                type="object",
                properties={"param1": {"type": "string", "description": "Test parameter"}},
                required=["param1"]
            ),
            outputs=ToolInputOutputSchema(
                type="object",
                properties={"result": {"type": "string", "description": "Test result"}}
            ),
            tags=["http", "test"],
            tool_provider=http_provider
        ),
        Tool(
            name="cli_tool",
            description="CLI test tool",
            inputs=ToolInputOutputSchema(
                type="object",
                properties={"command": {"type": "string", "description": "Command to execute"}},
                required=["command"]
            ),
            outputs=ToolInputOutputSchema(
                type="object",
                properties={"output": {"type": "string", "description": "Command output"}}
            ),
            tags=["cli", "test"],
            tool_provider=cli_provider
        )
    ]


@pytest_asyncio.fixture
async def utcp_client(mock_tool_repository, mock_search_strategy):
    """Create a UtcpClient instance with mocked dependencies."""
    config = UtcpClientConfig()
    variable_substitutor = DefaultVariableSubstitutor()
    
    client = UtcpClient(config, mock_tool_repository, mock_search_strategy, variable_substitutor)
    
    return client


class TestUtcpClientInterface:
    """Test the UtcpClientInterface abstract methods."""

    def test_interface_is_abstract(self):
        """Test that UtcpClientInterface cannot be instantiated directly."""
        with pytest.raises(TypeError):
            UtcpClientInterface()

    def test_utcp_client_implements_interface(self):
        """Test that UtcpClient properly implements the interface."""
        assert issubclass(UtcpClient, UtcpClientInterface)


class TestUtcpClient:
    """Test the UtcpClient implementation."""

    @pytest.mark.asyncio
    async def test_init(self, mock_tool_repository, mock_search_strategy):
        """Test UtcpClient initialization."""
        config = UtcpClientConfig()
        variable_substitutor = DefaultVariableSubstitutor()
        
        client = UtcpClient(config, mock_tool_repository, mock_search_strategy, variable_substitutor)
        
        assert client.config is config
        assert client.tool_repository is mock_tool_repository
        assert client.search_strategy is mock_search_strategy
        assert client.variable_substitutor is variable_substitutor

    @pytest.mark.asyncio
    async def test_create_with_defaults(self):
        """Test creating UtcpClient with default parameters."""
        with patch.object(UtcpClient, 'load_providers', new_callable=AsyncMock):
            client = await UtcpClient.create()
            
            assert isinstance(client.config, UtcpClientConfig)
            assert isinstance(client.tool_repository, InMemToolRepository)
            assert isinstance(client.search_strategy, TagSearchStrategy)
            assert isinstance(client.variable_substitutor, DefaultVariableSubstitutor)

    @pytest.mark.asyncio
    async def test_create_with_dict_config(self):
        """Test creating UtcpClient with dictionary config."""
        config_dict = {
            "variables": {"TEST_VAR": "test_value"},
            "providers_file_path": "test_providers.json"
        }
        
        with patch.object(UtcpClient, 'load_providers', new_callable=AsyncMock):
            client = await UtcpClient.create(config=config_dict)
            
            assert client.config.variables == {"TEST_VAR": "test_value"}
            assert client.config.providers_file_path == "test_providers.json"

    @pytest.mark.asyncio
    async def test_create_with_utcp_config(self):
        """Test creating UtcpClient with UtcpClientConfig object."""
        config = UtcpClientConfig(
            variables={"TEST_VAR": "test_value"},
            providers_file_path="test_providers.json"
        )
        
        with patch.object(UtcpClient, 'load_providers', new_callable=AsyncMock):
            client = await UtcpClient.create(config=config)
            
            assert client.config is config

    @pytest.mark.asyncio
    async def test_register_tool_provider(self, utcp_client, sample_tools):
        """Test registering a tool provider."""
        http_provider = HttpProvider(
            name="test_provider",
            url="https://api.example.com/tool",
            http_method="POST"
        )
        
        # Mock the transport
        mock_transport = MockTransport(sample_tools[:1])  # Return first tool
        utcp_client.transports["http"] = mock_transport
        
        tools = await utcp_client.register_tool_provider(http_provider)
        
        assert len(tools) == 1
        assert tools[0].name == "test_provider.http_tool"  # Should be prefixed
        # Check that the registered provider has the expected properties
        registered_provider = mock_transport.registered_providers[0]
        assert registered_provider.name == "test_provider"
        assert registered_provider.url == "https://api.example.com/tool"
        assert registered_provider.http_method == "POST"
        
        # Verify tool was saved in repository
        saved_tool = await utcp_client.tool_repository.get_tool("test_provider.http_tool")
        assert saved_tool is not None

    @pytest.mark.asyncio
    async def test_register_tool_provider_unsupported_type(self, utcp_client):
        """Test registering a tool provider with unsupported type."""
        # Create a provider with a supported type but then modify it
        provider = HttpProvider(
            name="test_provider",
            url="https://example.com",
            http_method="GET"
        )
        
        # Simulate an unsupported type by removing it from transports
        original_transports = utcp_client.transports.copy()
        del utcp_client.transports["http"]
        
        try:
            with pytest.raises(ValueError, match="Provider type not supported: http"):
                await utcp_client.register_tool_provider(provider)
        finally:
            # Restore original transports
            utcp_client.transports = original_transports

    @pytest.mark.asyncio
    async def test_register_tool_provider_name_sanitization(self, utcp_client, sample_tools):
        """Test that provider names are sanitized."""
        provider = HttpProvider(
            name="test-provider.with/special@chars",
            url="https://api.example.com/tool",
            http_method="POST"
        )
        
        mock_transport = MockTransport(sample_tools[:1])
        utcp_client.transports["http"] = mock_transport
        
        tools = await utcp_client.register_tool_provider(provider)
        
        # Name should be sanitized
        assert provider.name == "test_provider_with_special_chars"
        assert tools[0].name == "test_provider_with_special_chars.http_tool"

    @pytest.mark.asyncio
    async def test_deregister_tool_provider(self, utcp_client, sample_tools):
        """Test deregistering a tool provider."""
        provider = HttpProvider(
            name="test_provider",
            url="https://api.example.com/tool",
            http_method="POST"
        )
        
        mock_transport = MockTransport(sample_tools[:1])
        utcp_client.transports["http"] = mock_transport
        
        # First register the provider
        await utcp_client.register_tool_provider(provider)
        
        # Then deregister it
        await utcp_client.deregister_tool_provider("test_provider")
        
        # Verify provider was removed from repository
        saved_provider = await utcp_client.tool_repository.get_provider("test_provider")
        assert saved_provider is None
        
        # Verify transport deregister was called
        assert len(mock_transport.deregistered_providers) == 1

    @pytest.mark.asyncio
    async def test_deregister_nonexistent_provider(self, utcp_client):
        """Test deregistering a non-existent provider."""
        with pytest.raises(ValueError, match="Provider not found: nonexistent"):
            await utcp_client.deregister_tool_provider("nonexistent")

    @pytest.mark.asyncio
    async def test_call_tool(self, utcp_client, sample_tools):
        """Test calling a tool."""
        provider = HttpProvider(
            name="test_provider",
            url="https://api.example.com/tool",
            http_method="POST"
        )
        
        mock_transport = MockTransport(sample_tools[:1], "test_result")
        utcp_client.transports["http"] = mock_transport
        
        # Register the provider first
        await utcp_client.register_tool_provider(provider)
        
        # Call the tool
        result = await utcp_client.call_tool("test_provider.http_tool", {"param1": "value1"})
        
        assert result == "test_result"
        assert len(mock_transport.tool_calls) == 1
        assert mock_transport.tool_calls[0][0] == "test_provider.http_tool"
        assert mock_transport.tool_calls[0][1] == {"param1": "value1"}

    @pytest.mark.asyncio
    async def test_call_tool_nonexistent_provider(self, utcp_client):
        """Test calling a tool with nonexistent provider."""
        with pytest.raises(ValueError, match="Provider not found: nonexistent"):
            await utcp_client.call_tool("nonexistent.tool", {"param": "value"})

    @pytest.mark.asyncio
    async def test_call_tool_nonexistent_tool(self, utcp_client, sample_tools):
        """Test calling a nonexistent tool."""
        provider = HttpProvider(
            name="test_provider",
            url="https://api.example.com/tool",
            http_method="POST"
        )
        
        mock_transport = MockTransport(sample_tools[:1])
        utcp_client.transports["http"] = mock_transport
        
        # Register the provider first
        await utcp_client.register_tool_provider(provider)
        
        with pytest.raises(ValueError, match="Tool not found: test_provider.nonexistent"):
            await utcp_client.call_tool("test_provider.nonexistent", {"param": "value"})

    @pytest.mark.asyncio
    async def test_search_tools(self, utcp_client, sample_tools):
        """Test searching for tools."""
        # Add tools to the search strategy's repository
        for i, tool in enumerate(sample_tools):
            tool.name = f"provider_{i}.{tool.name}"
            await utcp_client.tool_repository.save_provider_with_tools(
                tool.tool_provider, [tool]
            )
        
        # Search for tools
        results = await utcp_client.search_tools("http", limit=10)
        
        # Should find the HTTP tool
        assert len(results) == 1
        assert "http" in results[0].name.lower() or "http" in results[0].description.lower()

    @pytest.mark.asyncio
    async def test_get_required_variables_for_manual_and_tools(self, utcp_client):
        """Test getting required variables for a provider."""
        provider = HttpProvider(
            name="test_provider",
            url="https://api.example.com/$API_URL",
            http_method="POST",
            auth=ApiKeyAuth(api_key="$API_KEY", var_name="Authorization")
        )
        
        # Mock the variable substitutor
        mock_substitutor = MagicMock()
        mock_substitutor.find_required_variables.return_value = ["API_URL", "API_KEY"]
        mock_substitutor.substitute.return_value = provider.model_dump()  # Return the original dict
        utcp_client.variable_substitutor = mock_substitutor
        
        variables = await utcp_client.get_required_variables_for_manual_and_tools(provider)
        
        assert variables == ["API_URL", "API_KEY"]
        mock_substitutor.find_required_variables.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_required_variables_for_tool(self, utcp_client, sample_tools):
        """Test getting required variables for a tool."""
        provider = HttpProvider(
            name="test_provider",
            url="https://api.example.com/$API_URL",
            http_method="POST"
        )
        
        tool = sample_tools[0]
        tool.name = "test_provider.http_tool"
        tool.tool_provider = provider
        
        # Add tool to repository
        await utcp_client.tool_repository.save_provider_with_tools(provider, [tool])
        
        # Mock the variable substitutor
        mock_substitutor = MagicMock()
        mock_substitutor.find_required_variables.return_value = ["API_URL"]
        utcp_client.variable_substitutor = mock_substitutor
        
        variables = await utcp_client.get_required_variables_for_tool("test_provider.http_tool")
        
        assert variables == ["API_URL"]
        mock_substitutor.find_required_variables.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_required_variables_for_nonexistent_tool(self, utcp_client):
        """Test getting required variables for a nonexistent tool."""
        with pytest.raises(ValueError, match="Tool not found: nonexistent.tool"):
            await utcp_client.get_required_variables_for_tool("nonexistent.tool")


class TestUtcpClientProviderLoading:
    """Test provider loading functionality."""

    @pytest.mark.asyncio
    async def test_load_providers_from_file(self, utcp_client):
        """Test loading providers from a JSON file."""
        # Create a temporary providers file with array format (as expected by load_providers)
        providers_data = [
            {
                "name": "http_provider",
                "provider_type": "http",
                "url": "https://api.example.com/tools",
                "http_method": "GET"
            },
            {
                "name": "cli_provider",
                "provider_type": "cli",
                "command_name": "echo"
            }
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(providers_data, f)
            temp_file = f.name
        
        try:
            # Mock the transports
            mock_http_transport = MockTransport([])
            mock_cli_transport = MockTransport([])
            utcp_client.transports["http"] = mock_http_transport
            utcp_client.transports["cli"] = mock_cli_transport
            
            # Load providers
            providers = await utcp_client.load_providers(temp_file)
            
            assert len(providers) == 2
            assert len(mock_http_transport.registered_providers) == 1
            assert len(mock_cli_transport.registered_providers) == 1
            
        finally:
            os.unlink(temp_file)

    @pytest.mark.asyncio
    async def test_load_providers_file_not_found(self, utcp_client):
        """Test loading providers from a non-existent file."""
        with pytest.raises(FileNotFoundError):
            await utcp_client.load_providers("nonexistent.json")

    @pytest.mark.asyncio
    async def test_load_providers_invalid_json(self, utcp_client):
        """Test loading providers from invalid JSON file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json content")
            temp_file = f.name
        
        try:
            with pytest.raises(ValueError, match="Invalid JSON in providers file"):
                await utcp_client.load_providers(temp_file)
        finally:
            os.unlink(temp_file)

    @pytest.mark.asyncio
    async def test_load_providers_with_variables(self, utcp_client):
        """Test loading providers with variable substitution."""
        providers_data = [
            {
                "name": "http_provider",
                "provider_type": "http",
                "url": "$BASE_URL/tools",
                "http_method": "GET",
                "auth": {
                    "auth_type": "api_key",
                    "api_key": "$API_KEY",
                    "var_name": "Authorization"
                }
            }
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(providers_data, f)
            temp_file = f.name
        
        try:
            # Setup client with variables (need provider prefixed variables)
            utcp_client.config.variables = {
                "http__provider_BASE_URL": "https://api.example.com",
                "http__provider_API_KEY": "secret_key"
            }
            
            # Mock the transport
            mock_transport = MockTransport([])
            utcp_client.transports["http"] = mock_transport
            
            # Load providers
            providers = await utcp_client.load_providers(temp_file)
            
            assert len(providers) == 1
            # Check that the registered provider has substituted values
            registered_provider = mock_transport.registered_providers[0]
            assert registered_provider.url == "https://api.example.com/tools"
            assert registered_provider.auth.api_key == "secret_key"
            
        finally:
            os.unlink(temp_file)

    @pytest.mark.asyncio
    async def test_load_providers_missing_variable(self, utcp_client):
        """Test loading providers with missing variable."""
        providers_data = [
            {
                "name": "http_provider",
                "provider_type": "http",
                "url": "$MISSING_VAR/tools",
                "http_method": "GET"
            }
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(providers_data, f)
            temp_file = f.name
        
        try:
            # Mock transport to avoid registration issues
            utcp_client.transports["http"] = MockTransport([])
            
            # The load_providers method catches exceptions and returns empty list
            # So we need to check the registration directly which will raise the exception
            provider_data = {
                "name": "http_provider",
                "provider_type": "http",
                "url": "$MISSING_VAR/tools",
                "http_method": "GET"
            }
            provider = HttpProvider.model_validate(provider_data)
            
            with pytest.raises(UtcpVariableNotFound, match="Variable http__provider_MISSING_VAR"):
                await utcp_client.register_tool_provider(provider)
        finally:
            os.unlink(temp_file)


class TestUtcpClientTransports:
    """Test transport-related functionality."""

    def test_default_transports_initialized(self, utcp_client):
        """Test that default transports are properly initialized."""
        expected_transport_types = [
            "http", "cli", "sse", "http_stream", "mcp", "text", "graphql", "tcp", "udp"
        ]
        
        for transport_type in expected_transport_types:
            assert transport_type in utcp_client.transports
            assert utcp_client.transports[transport_type] is not None

    @pytest.mark.asyncio
    async def test_variable_substitution(self, utcp_client):
        """Test variable substitution in providers."""
        provider = HttpProvider(
            name="test_provider",
            url="$BASE_URL/api",
            http_method="POST",
            auth=ApiKeyAuth(api_key="$API_KEY", var_name="Authorization")
        )
        
        # Set up variables with provider prefix
        utcp_client.config.variables = {
            "test__provider_BASE_URL": "https://api.example.com",
            "test__provider_API_KEY": "secret_key"
        }
        
        substituted_provider = utcp_client._substitute_provider_variables(provider, "test_provider")
        
        assert substituted_provider.url == "https://api.example.com/api"
        assert substituted_provider.auth.api_key == "secret_key"

    @pytest.mark.asyncio
    async def test_variable_substitution_missing_variable(self, utcp_client):
        """Test variable substitution with missing variable."""
        provider = HttpProvider(
            name="test_provider",
            url="$MISSING_VAR/api",
            http_method="POST"
        )
        
        with pytest.raises(UtcpVariableNotFound, match="Variable test__provider_MISSING_VAR"):
            utcp_client._substitute_provider_variables(provider, "test_provider")


class TestUtcpClientEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_empty_provider_file(self, utcp_client):
        """Test loading an empty provider file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([], f)  # Empty array instead of empty object
            temp_file = f.name
        
        try:
            providers = await utcp_client.load_providers(temp_file)
            assert providers == []
        finally:
            os.unlink(temp_file)

    @pytest.mark.asyncio
    async def test_register_provider_with_existing_name(self, utcp_client, sample_tools):
        """Test registering a provider with an existing name."""
        provider1 = HttpProvider(
            name="duplicate_name",
            url="https://api.example1.com/tool",
            http_method="POST"
        )
        provider2 = HttpProvider(
            name="duplicate_name",
            url="https://api.example2.com/tool",
            http_method="GET"
        )
        
        mock_transport = MockTransport(sample_tools[:1])
        utcp_client.transports["http"] = mock_transport
        
        # Register first provider
        await utcp_client.register_tool_provider(provider1)
        
        # Register second provider with same name (should overwrite)
        await utcp_client.register_tool_provider(provider2)
        
        # Should have the second provider
        saved_provider = await utcp_client.tool_repository.get_provider("duplicate_name")
        assert saved_provider.url == "https://api.example2.com/tool"
        assert saved_provider.http_method == "GET"

    @pytest.mark.asyncio
    async def test_complex_mcp_provider(self, utcp_client):
        """Test loading a complex MCP provider configuration."""
        providers_data = [
            {
                "name": "mcp_provider",
                "provider_type": "mcp",
                "config": {
                    "mcpServers": {
                        "stdio_server": {
                            "transport": "stdio",
                            "command": "python",
                            "args": ["-m", "test_server"],
                            "env": {"TEST_VAR": "test_value"}
                        },
                        "http_server": {
                            "transport": "http",
                            "url": "http://localhost:8000/mcp"
                        }
                    }
                }
            }
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(providers_data, f)
            temp_file = f.name
        
        try:
            # Mock the MCP transport
            mock_transport = MockTransport([])
            utcp_client.transports["mcp"] = mock_transport
            
            providers = await utcp_client.load_providers(temp_file)
            
            assert len(providers) == 1
            provider = providers[0]
            assert isinstance(provider, MCPProvider)
            assert len(provider.config.mcpServers) == 2
            assert "stdio_server" in provider.config.mcpServers
            assert "http_server" in provider.config.mcpServers
            
        finally:
            os.unlink(temp_file)

    @pytest.mark.asyncio
    async def test_text_transport_configuration(self, utcp_client):
        """Test TextTransport base path configuration."""
        # Create a temporary directory structure
        with tempfile.TemporaryDirectory() as temp_dir:
            providers_file = os.path.join(temp_dir, "providers.json")
            
            with open(providers_file, 'w') as f:
                json.dump([], f)  # Empty array
            
            # Create client with providers file path
            config = UtcpClientConfig(providers_file_path=providers_file)
            
            with patch.object(UtcpClient, 'load_providers', new_callable=AsyncMock):
                client = await UtcpClient.create(config=config)
                
                # Check that TextTransport was configured with the correct base path
                text_transport = client.transports["text"]
                assert hasattr(text_transport, 'base_path')
                assert text_transport.base_path == temp_dir

    @pytest.mark.asyncio
    async def test_load_providers_wrong_format(self, utcp_client):
        """Test loading providers with wrong JSON format (object instead of array)."""
        providers_data = {
            "http_provider": {
                "provider_type": "http",
                "url": "https://api.example.com/tools",
                "http_method": "GET"
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(providers_data, f)
            temp_file = f.name
        
        try:
            with pytest.raises(ValueError, match="Providers file must contain a JSON array at the root level"):
                await utcp_client.load_providers(temp_file)
        finally:
            os.unlink(temp_file)
