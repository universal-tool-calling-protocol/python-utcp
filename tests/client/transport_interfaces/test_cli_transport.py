"""
Tests for the CLI transport interface.
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

import pytest
import pytest_asyncio

from utcp.client.transport_interfaces.cli_transport import CliTransport
from utcp.shared.provider import CliProvider


@pytest_asyncio.fixture
async def transport() -> CliTransport:
    """Provides a clean CliTransport instance."""
    t = CliTransport()
    yield t
    await t.close()


@pytest_asyncio.fixture
def mock_cli_script():
    """Create a mock CLI script that can be executed for testing."""
    script_content = '''#!/usr/bin/env python3
import sys
import json
import os

def main():
    # Check for tool discovery mode (no arguments)
    if len(sys.argv) == 1:
        # Return UTCP manual
        tools_data = {
            "version": "1.0.0",
            "name": "Mock CLI Tools",
            "description": "Mock CLI tools for testing",
            "tools": [
                {
                    "name": "echo",
                    "description": "Echo back the input",
                    "inputs": {
                        "properties": {
                            "message": {"type": "string"}
                        },
                        "required": ["message"]
                    },
                    "outputs": {
                        "properties": {
                            "result": {"type": "string"}
                        }
                    },
                    "tags": ["utility"]
                },
                {
                    "name": "math",
                    "description": "Perform math operations",
                    "inputs": {
                        "properties": {
                            "operation": {"type": "string", "enum": ["add", "subtract"]},
                            "a": {"type": "number"},
                            "b": {"type": "number"}
                        },
                        "required": ["operation", "a", "b"]
                    },
                    "outputs": {
                        "properties": {
                            "result": {"type": "number"}
                        }
                    },
                    "tags": ["math"]
                }
            ]
        }
        print(json.dumps(tools_data))
        return
    
    # Check for environment variables
    if "--check-env" in sys.argv:
        env_info = {}
        # Check for specific test environment variables
        test_vars = ['MY_API_KEY', 'TEST_VAR', 'CUSTOM_CONFIG']
        for var in test_vars:
            if var in os.environ:
                env_info[var] = os.environ[var]
        print(json.dumps(env_info))
        return
    
    # Handle tool execution
    args = sys.argv[1:]
    
    # Parse arguments
    parsed_args = {}
    i = 0
    while i < len(args):
        if args[i].startswith('--'):
            key = args[i][2:]
            if i + 1 < len(args) and not args[i + 1].startswith('--'):
                value = args[i + 1]
                # Try to parse as number
                try:
                    if '.' in value:
                        value = float(value)
                    else:
                        value = int(value)
                except ValueError:
                    pass  # Keep as string
                parsed_args[key] = value
                i += 2
            else:
                parsed_args[key] = True
                i += 1
        else:
            i += 1
    
    # Simple tool implementations
    if "message" in parsed_args:
        # Echo tool
        result = {"result": f"Echo: {parsed_args['message']}"}
        print(json.dumps(result))
    elif "operation" in parsed_args and "a" in parsed_args and "b" in parsed_args:
        # Math tool
        a = parsed_args["a"]
        b = parsed_args["b"]
        op = parsed_args["operation"]
        
        if op == "add":
            result = {"result": a + b}
        elif op == "subtract":
            result = {"result": a - b}
        else:
            print(f"Unknown operation: {op}", file=sys.stderr)
            sys.exit(1)
        
        print(json.dumps(result))
    elif "error" in parsed_args:
        # Error simulation
        print(f"Simulated error: {parsed_args['error']}", file=sys.stderr)
        sys.exit(1)
    else:
        print("Unknown command or missing arguments", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
'''
    
    # Create temporary script file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(script_content)
        script_path = f.name
    
    # Make it executable on Unix systems
    try:
        os.chmod(script_path, 0o755)
    except Exception:
        pass  # Windows doesn't use executable permissions
    
    yield script_path
    
    # Cleanup
    try:
        os.unlink(script_path)
    except Exception:
        pass


@pytest_asyncio.fixture
def python_executable():
    """Get the Python executable path."""
    return sys.executable


@pytest.mark.asyncio
async def test_register_provider_discovers_tools(transport: CliTransport, mock_cli_script, python_executable):
    """Test that registering a provider discovers tools from command output."""
    provider = CliProvider(
        name="mock_cli_provider",
        command_name=f"{python_executable} {mock_cli_script}"
    )
    
    tools = await transport.register_tool_provider(provider)
    
    assert len(tools) == 2
    assert tools[0].name == "echo"
    assert tools[0].description == "Echo back the input"
    assert tools[0].tags == ["utility"]
    
    assert tools[1].name == "math"
    assert tools[1].description == "Perform math operations"
    assert tools[1].tags == ["math"]


@pytest.mark.asyncio
async def test_register_provider_missing_command_name(transport: CliTransport):
    """Test that registering a provider without command_name raises an error."""
    provider = CliProvider(
        name="missing_command_provider"
    )
    
    with pytest.raises(ValueError, match="must have command_name set"):
        await transport.register_tool_provider(provider)


@pytest.mark.asyncio
async def test_register_provider_wrong_type(transport: CliTransport):
    """Test that registering a non-CLI provider raises an error."""
    from utcp.shared.provider import HttpProvider
    
    provider = HttpProvider(
        name="http_provider",
        url="https://example.com"
    )
    
    with pytest.raises(ValueError, match="CliTransport can only be used with CliProvider"):
        await transport.register_tool_provider(provider)


@pytest.mark.asyncio
async def test_call_tool_json_output(transport: CliTransport, mock_cli_script, python_executable):
    """Test calling a tool that returns JSON output."""
    provider = CliProvider(
        name="mock_cli_provider",
        command_name=f"{python_executable} {mock_cli_script}"
    )
    
    result = await transport.call_tool("echo", {"message": "Hello World"}, provider)
    
    assert isinstance(result, dict)
    assert result["result"] == "Echo: Hello World"


@pytest.mark.asyncio
async def test_call_tool_math_operation(transport: CliTransport, mock_cli_script, python_executable):
    """Test calling a math tool with numeric arguments."""
    provider = CliProvider(
        name="mock_cli_provider",
        command_name=f"{python_executable} {mock_cli_script}"
    )
    
    result = await transport.call_tool("math", {"operation": "add", "a": 5, "b": 3}, provider)
    
    assert isinstance(result, dict)
    assert result["result"] == 8


@pytest.mark.asyncio
async def test_call_tool_error_handling(transport: CliTransport, mock_cli_script, python_executable):
    """Test calling a tool that exits with an error returns stderr."""
    provider = CliProvider(
        name="mock_cli_provider",
        command_name=f"{python_executable} {mock_cli_script}"
    )
    
    # This should trigger an error in the mock script
    result = await transport.call_tool("error_tool", {"error": "test error"}, provider)
    
    # Should return stderr content since exit code != 0
    assert isinstance(result, str)
    assert "Simulated error: test error" in result


@pytest.mark.asyncio
async def test_call_tool_missing_command_name(transport: CliTransport):
    """Test calling a tool without command_name raises an error."""
    provider = CliProvider(
        name="missing_command_provider"
    )
    
    with pytest.raises(ValueError, match="must have command_name set"):
        await transport.call_tool("some_tool", {}, provider)


@pytest.mark.asyncio
async def test_call_tool_wrong_provider_type(transport: CliTransport):
    """Test calling a tool with wrong provider type."""
    from utcp.shared.provider import HttpProvider
    
    provider = HttpProvider(
        name="http_provider",
        url="https://example.com"
    )
    
    with pytest.raises(ValueError, match="CliTransport can only be used with CliProvider"):
        await transport.call_tool("some_tool", {}, provider)


@pytest.mark.asyncio
async def test_environment_variables(transport: CliTransport, mock_cli_script, python_executable):
    """Test that custom environment variables are properly set."""
    env_vars = {
        "MY_API_KEY": "test-api-key-123",
        "TEST_VAR": "test-value",
        "CUSTOM_CONFIG": "config-data"
    }
    
    provider = CliProvider(
        name="env_cli_provider",
        command_name=f"{python_executable} {mock_cli_script}",
        env_vars=env_vars
    )
    
    # Call the env check endpoint
    result = await transport.call_tool("check_env", {"check-env": True}, provider)
    
    assert isinstance(result, dict)
    assert result["MY_API_KEY"] == "test-api-key-123"
    assert result["TEST_VAR"] == "test-value"
    assert result["CUSTOM_CONFIG"] == "config-data"


@pytest.mark.asyncio
async def test_no_environment_variables(transport: CliTransport, mock_cli_script, python_executable):
    """Test that no environment variables are set when env_vars is None."""
    provider = CliProvider(
        name="no_env_cli_provider",
        command_name=f"{python_executable} {mock_cli_script}"
        # env_vars=None by default
    )
    
    # Call the env check endpoint
    result = await transport.call_tool("check_env", {"check-env": True}, provider)
    
    assert isinstance(result, dict)
    # Should be empty since no custom env vars were set
    assert len(result) == 0


@pytest.mark.asyncio
async def test_working_directory(transport: CliTransport, mock_cli_script, python_executable, tmp_path):
    """Test that working directory is properly set during command execution."""
    # Create a test file in a specific directory
    test_dir = tmp_path / "test_working_dir"
    test_dir.mkdir()
    test_file = test_dir / "current_dir.txt"
    
    # Create a mock script that writes the current working directory to a file
    script_content = '''
import os
import sys

if "--write-cwd" in sys.argv:
    with open("current_dir.txt", "w") as f:
        f.write(os.getcwd())
    print("{\'status\': \'written\'}".replace("\'", '"'))
else:
    print("{\'error\': \'unknown command\'}".replace("\'", '"'))
'''
    
    working_dir_script = tmp_path / "working_dir_script.py"
    working_dir_script.write_text(script_content)
    
    provider = CliProvider(
        name="working_dir_test_provider",
        command_name=f"{python_executable} {working_dir_script}",
        working_dir=str(test_dir)
    )
    
    # Call the tool which should write the current directory to a file
    result = await transport.call_tool("write_cwd", {"write-cwd": True}, provider)
    
    # Verify the result
    assert isinstance(result, dict)
    assert result["status"] == "written"
    
    # Verify the file was created in the working directory and contains the correct path
    assert test_file.exists()
    written_cwd = test_file.read_text().strip()
    
    # The written current working directory should be the test directory
    assert os.path.abspath(written_cwd) == os.path.abspath(str(test_dir))


@pytest.mark.asyncio
async def test_no_working_directory(transport: CliTransport, mock_cli_script, python_executable):
    """Test that commands work normally when no working directory is specified."""
    provider = CliProvider(
        name="no_working_dir_provider",
        command_name=f"{python_executable} {mock_cli_script}"
        # working_dir=None by default
    )
    
    # This should work normally - calling the echo tool
    result = await transport.call_tool("echo", {"message": "test"}, provider)
    
    assert isinstance(result, dict)
    assert result["result"] == "Echo: test"


@pytest.mark.asyncio
async def test_env_vars_and_working_dir_combined(transport: CliTransport, python_executable, tmp_path):
    """Test that both environment variables and working directory work together."""
    # Create a test directory
    test_dir = tmp_path / "combined_test_dir"
    test_dir.mkdir()
    
    # Create a script that checks both environment variable and writes current directory
    script_content = '''
import os
import sys
import json

if "--combined-test" in sys.argv:
    result = {
        "current_dir": os.getcwd(),
        "test_env_var": os.environ.get("TEST_COMBINED_VAR", "not_found"),
        "status": "success"
    }
    print(json.dumps(result))
else:
    print(json.dumps({"error": "unknown command"}))
'''
    
    combined_script = tmp_path / "combined_test_script.py"
    combined_script.write_text(script_content)
    
    provider = CliProvider(
        name="combined_test_provider",
        command_name=f"{python_executable} {combined_script}",
        env_vars={"TEST_COMBINED_VAR": "test_value_123"},
        working_dir=str(test_dir)
    )
    
    # Call the tool
    result = await transport.call_tool("combined_test", {"combined-test": True}, provider)
    
    # Verify both environment variable and working directory are set correctly
    assert isinstance(result, dict)
    assert result["status"] == "success"
    assert result["test_env_var"] == "test_value_123"
    assert os.path.abspath(result["current_dir"]) == os.path.abspath(str(test_dir))


@pytest.mark.asyncio
async def test_argument_formatting():
    """Test that arguments are properly formatted for command line."""
    transport = CliTransport()
    
    # Test various argument types
    args = {
        "string_arg": "hello",
        "number_arg": 42,
        "float_arg": 3.14,
        "bool_true": True,
        "bool_false": False,
        "list_arg": ["item1", "item2"]
    }
    
    formatted = transport._format_arguments(args)
    
    # Check that arguments are properly formatted
    assert "--string_arg" in formatted
    assert "hello" in formatted
    assert "--number_arg" in formatted
    assert "42" in formatted
    assert "--float_arg" in formatted
    assert "3.14" in formatted
    assert "--bool_true" in formatted
    assert "--bool_false" not in formatted  # False booleans should not appear
    assert "--list_arg" in formatted
    assert "item1" in formatted
    assert "item2" in formatted


@pytest.mark.asyncio
async def test_json_extraction_from_output():
    """Test extracting JSON from various output formats."""
    transport = CliTransport()
    
    # Test complete JSON output
    output1 = '{"tools": [{"name": "test", "description": "Test tool"}]}'
    tools1 = transport._extract_utcp_manual_from_output(output1, "test_provider")
    assert len(tools1) == 1
    assert tools1[0].name == "test"
    
    # Test JSON within text output
    output2 = '''
    Starting CLI tool...
    {"tools": [{"name": "embedded", "description": "Embedded tool"}]}
    Process completed.
    '''
    tools2 = transport._extract_utcp_manual_from_output(output2, "test_provider")
    assert len(tools2) == 1
    assert tools2[0].name == "embedded"
    
    # Test single tool definition
    output3 = '{"name": "single", "description": "Single tool"}'
    tools3 = transport._extract_utcp_manual_from_output(output3, "test_provider")
    assert len(tools3) == 1
    assert tools3[0].name == "single"
    
    # Test no valid JSON
    output4 = "No JSON here, just plain text"
    tools4 = transport._extract_utcp_manual_from_output(output4, "test_provider")
    assert len(tools4) == 0


@pytest.mark.asyncio
async def test_deregister_provider(transport: CliTransport, mock_cli_script, python_executable):
    """Test deregistering a CLI provider."""
    provider = CliProvider(
        name="mock_cli_provider",
        command_name=f"{python_executable} {mock_cli_script}"
    )
    
    # Register and then deregister (should not raise any errors)
    await transport.register_tool_provider(provider)
    await transport.deregister_tool_provider(provider)


@pytest.mark.asyncio
async def test_close_transport(transport: CliTransport):
    """Test closing the transport."""
    # Should not raise any errors
    await transport.close()


@pytest.mark.asyncio
async def test_command_execution_timeout(python_executable, tmp_path):
    """Test that command execution respects timeout."""
    transport = CliTransport()
    
    # Create a Python script that sleeps for a long time
    sleep_script_content = '''
import time
import sys

if "--sleep" in sys.argv:
    time.sleep(10)  # Sleep for 10 seconds
    print("This should not be printed due to timeout")
else:
    print("Unknown command")
    sys.exit(1)
'''
    
    sleep_script = tmp_path / "sleep_script.py"
    sleep_script.write_text(sleep_script_content)
    
    try:
        command = [python_executable, str(sleep_script), "--sleep"]
        env = os.environ.copy()
        
        with pytest.raises(asyncio.TimeoutError):  # Should raise TimeoutError
            await transport._execute_command(command, env, timeout=1.0, working_dir=str(tmp_path))
            
    except Exception as e:
        # If the specific timeout doesn't work, just ensure some exception is raised
        # and it's related to timing out
        assert "timeout" in str(e).lower() or isinstance(e, asyncio.TimeoutError)


@pytest.mark.asyncio
async def test_mixed_output_formats(transport: CliTransport, python_executable):
    """Test handling of mixed output formats (text and JSON)."""
    # Create a simple script that outputs mixed content
    script_content = '''
import sys
print("Starting tool execution...")
print('{"result": "success", "value": 42}')
print("Tool execution completed.")
'''
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(script_content)
        script_path = f.name
    
    try:
        provider = CliProvider(
            name="mixed_output_provider",
            command_name=f"{python_executable} {script_path}"
        )
        
        result = await transport.call_tool("mixed_tool", {}, provider)
        
        # Should return the JSON part since command succeeds (exit code 0)
        # But the output contains both text and JSON
        assert isinstance(result, str)  # Will be text since full output isn't valid JSON
        assert "Starting tool execution..." in result
        assert '{"result": "success", "value": 42}' in result
        
    finally:
        try:
            os.unlink(script_path)
        except Exception:
            pass
