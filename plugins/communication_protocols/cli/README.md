# UTCP CLI Plugin

[![PyPI Downloads](https://static.pepy.tech/badge/utcp-cli)](https://pepy.tech/projects/utcp-cli)

Command-line interface plugin for UTCP, enabling integration with command-line tools and processes.

## Features

- **Multi-Command Execution**: Execute multiple commands sequentially in a single subprocess
- **State Preservation**: Directory changes and environment persist between commands
- **Cross-Platform Script Generation**: PowerShell on Windows, Bash on Unix/Linux/macOS
- **Flexible Output Control**: Choose which command outputs to include in final result
- **Argument Substitution**: `UTCP_ARG_argname_UTCP_END` placeholder system
- **Output Referencing**: Access previous command outputs with `$CMD_0_OUTPUT`, `$CMD_1_OUTPUT`
- **Environment Variables**: Secure credential and configuration passing
- **Working Directory Control**: Execute commands in specific directories
- **Timeout Management**: Configurable execution timeouts
- **Error Handling**: Comprehensive subprocess error management

## Installation

```bash
pip install utcp-cli
```

## Quick Start

```python
from utcp.utcp_client import UtcpClient

# Multi-step CLI tool
client = await UtcpClient.create(config={
    "manual_call_templates": [{
        "name": "file_analysis",
        "call_template_type": "cli",
        "commands": [
            {
                "command": "cd UTCP_ARG_target_dir_UTCP_END",
                "append_to_final_output": false
            },
            {
                "command": "find . -type f -name '*.py' | wc -l"
            }
        ]
    }]
})

result = await client.call_tool("file_analysis.count_python_files", {"target_dir": "/project"})
```

## Configuration Examples

### Basic Multi-Command Operation
```json
{
  "name": "file_analysis",
  "call_template_type": "cli",
  "commands": [
    {
      "command": "cd UTCP_ARG_target_dir_UTCP_END",
      "append_to_final_output": false
    },
    {
      "command": "ls -la"
    }
  ],
  "working_dir": "/tmp"
}
```

### With Environment Variables and Output Control
```json
{
  "name": "python_pipeline",
  "call_template_type": "cli",
  "commands": [
    {
      "command": "python setup.py install",
      "append_to_final_output": false
    },
    {
      "command": "python script.py --input UTCP_ARG_input_file_UTCP_END --result \"$CMD_0_OUTPUT\"",
      "append_to_final_output": true
    }
  ],
  "env_vars": {
    "PYTHONPATH": "/custom/path",
    "API_KEY": "${API_KEY}"
  }
}
```

### Cross-Platform Git Operations
```json
{
  "name": "git_analysis",
  "call_template_type": "cli",
  "commands": [
    {
      "command": "git clone UTCP_ARG_repo_url_UTCP_END temp_repo",
      "append_to_final_output": false
    },
    {
      "command": "cd temp_repo",
      "append_to_final_output": false  
    },
    {
      "command": "git log --oneline -10",
      "append_to_final_output": true
    },
    {
      "command": "echo \"Repository has $(find . -name '*.py' | wc -l) Python files\"",
      "append_to_final_output": true
    }
  ],
  "env_vars": {
    "GIT_AUTHOR_NAME": "UTCP Bot",
    "GIT_AUTHOR_EMAIL": "bot@utcp.dev"
  }
}
```

### Referencing Previous Command Output
```json
{
  "name": "conditional_processor",
  "call_template_type": "cli",
  "commands": [
    {
      "command": "git status --porcelain",
      "append_to_final_output": false
    },
    {
      "command": "echo \"Changes detected: $CMD_0_OUTPUT\"",
      "append_to_final_output": true
    }
  ]
}
```

## Cross-Platform Considerations

### Command Syntax
Commands should use appropriate syntax for the target platform:

**Windows (PowerShell):**
```json
{
  "commands": [
    {"command": "Get-ChildItem UTCP_ARG_path_UTCP_END"},
    {"command": "Set-Location UTCP_ARG_dir_UTCP_END"}
  ]
}
```

**Unix/Linux/macOS (Bash):**
```json
{
  "commands": [
    {"command": "ls -la UTCP_ARG_path_UTCP_END"},
    {"command": "cd UTCP_ARG_dir_UTCP_END"}
  ]
}
```

### Universal Commands
Some commands work across platforms:
```json
{
  "commands": [
    {"command": "git status"},
    {"command": "python --version"},
    {"command": "node -v"}
  ]
}
```

## Security Considerations

- Commands execute in isolated subprocesses with controlled environment
- Environment variables provide secure credential passing
- Working directory restrictions limit file system access  
- UTCP_ARG placeholders prevent command injection
- Previous command outputs should be used carefully to avoid injection
- Commands should use platform-appropriate syntax

## Error Handling

```python
from utcp.exceptions import ToolCallError

try:
    result = await client.call_tool("cli_tool.multi_command", {
        "repo_url": "https://github.com/example/repo.git",
        "target_dir": "analysis_temp"
    })
except ToolCallError as e:
    print(f"CLI tool execution failed: {e}")
    # Script execution failed - check individual command outputs
```

## Common Use Cases

- **Multi-step Builds**: setup → compile → test → package
- **Git Workflows**: clone → analyze → commit → push  
- **Data Pipelines**: fetch → transform → validate → output
- **File Operations**: navigate → search → process → report
- **Development Tools**: install dependencies → run tests → generate docs
- **System Administration**: check status → backup → cleanup → verify
- **Custom Workflows**: Any sequence of command-line operations

## Testing CLI Tools

```python
import pytest
from utcp.utcp_client import UtcpClient

@pytest.mark.asyncio
async def test_multi_command_cli_tool():
    client = await UtcpClient.create(config={
        "manual_call_templates": [{
            "name": "test_cli",
            "call_template_type": "cli",
            "commands": [
                {
                    "command": "echo UTCP_ARG_message_UTCP_END",
                    "append_to_final_output": false
                },
                {
                    "command": "echo \"Previous: $CMD_0_OUTPUT\""
                }
            ]
        }]
    })
    
    result = await client.call_tool("test_cli.echo_chain", {"message": "hello"})
    assert "Previous: hello" in result
```

## Related Documentation

- [Main UTCP Documentation](../../../README.md)
- [Core Package Documentation](../../../core/README.md)
- [HTTP Plugin](../http/README.md)
- [MCP Plugin](../mcp/README.md)
- [Text Plugin](../text/README.md)

## Examples

For complete examples, see the [UTCP examples repository](https://github.com/universal-tool-calling-protocol/utcp-examples).
