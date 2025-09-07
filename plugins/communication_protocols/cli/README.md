# UTCP CLI Plugin

[![PyPI Downloads](https://static.pepy.tech/badge/utcp-cli)](https://pepy.tech/projects/utcp-cli)

Command-line interface plugin for UTCP, enabling integration with command-line tools and processes.

## Features

- **Command Execution**: Run any command-line tool as a UTCP tool
- **Environment Variables**: Secure credential and configuration passing
- **Working Directory Control**: Execute commands in specific directories
- **Input/Output Handling**: Support for stdin, stdout, stderr processing
- **Cross-Platform**: Works on Windows, macOS, and Linux
- **Timeout Management**: Configurable execution timeouts
- **Argument Validation**: Optional input sanitization

## Installation

```bash
pip install utcp-cli
```

## Quick Start

```python
from utcp.utcp_client import UtcpClient

# Basic CLI tool
client = await UtcpClient.create(config={
    "manual_call_templates": [{
        "name": "file_tools",
        "call_template_type": "cli",
        "command_name": "ls -la ${path}"
    }]
})

result = await client.call_tool("file_tools.list", {"path": "/home"})
```

## Configuration Examples

### Basic Command
```json
{
  "name": "file_ops",
  "call_template_type": "cli",
  "command_name": "ls -la ${path}",
  "working_dir": "/tmp"
}
```

### With Environment Variables
```json
{
  "name": "python_script",
  "call_template_type": "cli",
  "command_name": "python script.py ${input}",
  "env_vars": {
    "PYTHONPATH": "/custom/path",
    "API_KEY": "${API_KEY}"
  }
}
```

### Processing JSON with jq
```json
{
  "name": "json_processor",
  "call_template_type": "cli",
  "command_name": "jq '.data'",
  "stdin": "${json_input}",
  "timeout": 10
}
```

### Git Operations
```json
{
  "name": "git_tools",
  "call_template_type": "cli",
  "command_name": "git ${operation} ${args}",
  "working_dir": "${repo_path}",
  "env_vars": {
    "GIT_AUTHOR_NAME": "${author_name}",
    "GIT_AUTHOR_EMAIL": "${author_email}"
  }
}
```

## Security Considerations

- Commands run in isolated subprocesses
- Environment variables provide secure credential passing
- Working directory restrictions limit file system access
- Input validation prevents command injection

```json
{
  "name": "safe_grep",
  "call_template_type": "cli",
  "command_name": "grep ${pattern} ${file}",
  "working_dir": "/safe/directory",
  "allowed_args": {
    "pattern": "^[a-zA-Z0-9_-]+$",
    "file": "^[a-zA-Z0-9_./-]+\\.txt$"
  }
}
```

## Error Handling

```python
from utcp.exceptions import ToolCallError
import subprocess

try:
    result = await client.call_tool("cli_tool.command", {"arg": "value"})
except ToolCallError as e:
    if isinstance(e.__cause__, subprocess.CalledProcessError):
        print(f"Command failed with exit code {e.__cause__.returncode}")
        print(f"stderr: {e.__cause__.stderr}")
```

## Common Use Cases

- **File Operations**: ls, find, grep, awk, sed
- **Data Processing**: jq, sort, uniq, cut
- **System Monitoring**: ps, top, df, netstat
- **Development Tools**: git, npm, pip, docker
- **Custom Scripts**: Python, bash, PowerShell scripts

## Testing CLI Tools

```python
import pytest
from utcp.utcp_client import UtcpClient

@pytest.mark.asyncio
async def test_cli_tool():
    client = await UtcpClient.create(config={
        "manual_call_templates": [{
            "name": "test_cli",
            "call_template_type": "cli",
            "command_name": "echo ${message}"
        }]
    })
    
    result = await client.call_tool("test_cli.echo", {"message": "hello"})
    assert "hello" in result["stdout"]
```

## Related Documentation

- [Main UTCP Documentation](../../../README.md)
- [Core Package Documentation](../../../core/README.md)
- [HTTP Plugin](../http/README.md)
- [MCP Plugin](../mcp/README.md)
- [Text Plugin](../text/README.md)

## Examples

For complete examples, see the [UTCP examples repository](https://github.com/universal-tool-calling-protocol/utcp-examples).
