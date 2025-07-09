"""
Text file transport for UTCP client.

This transport reads tool definitions from local text files.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

from utcp.client.client_transport_interface import ClientTransportInterface
from utcp.shared.provider import Provider, TextProvider
from utcp.shared.tool import Tool
from utcp.shared.utcp_manual import UtcpManual


class TextTransport(ClientTransportInterface):
    """Transport implementation for text file-based tool providers.
    
    This transport reads tool definitions from local text files. The file should
    contain a JSON object with a 'tools' array containing tool definitions.
    
    Since tools are defined statically in text files, tool calls are not supported
    and will raise a ValueError.
    """
    
    def __init__(self, base_path: Optional[str] = None):
        """Initialize the text transport.
        
        Args:
            base_path: The base path to resolve relative file paths from.
        """
        self.base_path = base_path
    
    def _log_info(self, message: str):
        """Log informational messages."""
        print(f"[TextTransport] {message}")
        
    def _log_error(self, message: str):
        """Log error messages."""
        logging.error(f"[TextTransport Error] {message}")
    
    async def register_tool_provider(self, provider: Provider) -> List[Tool]:
        """Register a text provider and discover its tools.
        
        Args:
            provider: The TextProvider to register
            
        Returns:
            List of tools defined in the text file
            
        Raises:
            ValueError: If provider is not a TextProvider
            FileNotFoundError: If the specified file doesn't exist
            json.JSONDecodeError: If the file contains invalid JSON
        """
        if not isinstance(provider, TextProvider):
            raise ValueError("TextTransport can only be used with TextProvider")
        
        file_path = Path(provider.file_path)
        if not file_path.is_absolute() and self.base_path:
            file_path = Path(self.base_path) / file_path
        
        self._log_info(f"Reading tool definitions from '{file_path}'")
        
        try:
            # Check if file exists
            if not file_path.exists():
                raise FileNotFoundError(f"Tool definition file not found: {file_path}")
            
            # Read and parse the file
            with open(file_path, 'r', encoding='utf-8') as f:
                file_content = f.read()
            
            # Parse as JSON
            try:
                data = json.loads(file_content)
            except json.JSONDecodeError as e:
                self._log_error(f"Invalid JSON in file '{file_path}': {e}")
                raise
            
            # Validate structure and extract tools
            if isinstance(data, dict):
                if 'tools' in data:
                    # Standard UTCP manual format
                    utcp_manual = UtcpManual(**data)
                    tools = utcp_manual.tools
                elif 'name' in data and 'description' in data:
                    # Single tool definition
                    tools = [Tool(**data)]
                else:
                    self._log_error(f"Invalid file format in '{file_path}': expected 'tools' array or single tool definition")
                    return []
            elif isinstance(data, list):
                # Array of tool definitions
                tools = [Tool(**tool_data) for tool_data in data]
            else:
                self._log_error(f"Invalid file format in '{file_path}': expected object or array")
                return []
            
            self._log_info(f"Successfully loaded {len(tools)} tools from '{file_path}'")
            return tools
            
        except FileNotFoundError:
            self._log_error(f"Tool definition file not found: {file_path}")
            raise
        except json.JSONDecodeError:
            # Already logged in the except block above
            raise
        except Exception as e:
            self._log_error(f"Unexpected error reading file '{file_path}': {e}")
            return []
    
    async def deregister_tool_provider(self, provider: Provider) -> None:
        """Deregister a text provider.
        
        This is a no-op for text providers since they are stateless.
        
        Args:
            provider: The provider to deregister
        """
        if isinstance(provider, TextProvider):
            self._log_info(f"Deregistering text provider '{provider.name}' (no-op)")
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], provider: Provider) -> Any:
        """Call a tool on a text provider.
        
        For text providers, this returns the content of the text file.
        
        Args:
            tool_name: Name of the tool to call (ignored for text providers)
            arguments: Arguments for the tool call (ignored for text providers)
            provider: The TextProvider containing the file
            
        Returns:
            The content of the text file as a string
            
        Raises:
            ValueError: If provider is not a TextProvider
            FileNotFoundError: If the specified file doesn't exist
        """
        if not isinstance(provider, TextProvider):
            raise ValueError("TextTransport can only be used with TextProvider")
        
        file_path = Path(provider.file_path)
        if not file_path.is_absolute() and self.base_path:
            file_path = Path(self.base_path) / file_path
            
        self._log_info(f"Reading content from '{file_path}' for tool '{tool_name}'")
        
        try:
            # Check if file exists
            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")
            
            # Read and return the file content
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            self._log_info(f"Successfully read {len(content)} characters from '{file_path}'")
            return content
            
        except FileNotFoundError:
            self._log_error(f"File not found: {file_path}")
            raise
        except Exception as e:
            self._log_error(f"Error reading file '{file_path}': {e}")
            raise
    
    async def close(self) -> None:
        """Close the transport.
        
        This is a no-op for text transports since they don't maintain connections.
        """
        self._log_info("Closing text transport (no-op)")
