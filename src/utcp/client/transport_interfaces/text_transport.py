"""
Text file transport for UTCP client.

This transport reads tool definitions from local text files.
"""
import json
import logging
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

from utcp.client.client_transport_interface import ClientTransportInterface
from utcp.client.openapi_converter import OpenApiConverter
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
    
    async def register_tool_provider(self, manual_provider: Provider) -> List[Tool]:
        """Register a text provider and discover its tools.
        
        Args:
            manual_provider: The TextProvider to register
            
        Returns:
            List of tools defined in the text file
            
        Raises:
            ValueError: If provider is not a TextProvider
            FileNotFoundError: If the specified file doesn't exist
            json.JSONDecodeError: If the file contains invalid JSON
        """
        if not isinstance(manual_provider, TextProvider):
            raise ValueError("TextTransport can only be used with TextProvider")
        
        file_path = Path(manual_provider.file_path)
        if not file_path.is_absolute() and self.base_path:
            file_path = Path(self.base_path) / file_path
        
        self._log_info(f"Reading tool definitions from '{file_path}'")
        
        try:
            if not file_path.exists():
                raise FileNotFoundError(f"Tool definition file not found: {file_path}")

            with open(file_path, 'r', encoding='utf-8') as f:
                file_content = f.read()

            # Parse based on file extension
            if file_path.suffix in ['.yaml', '.yml']:
                data = yaml.safe_load(file_content)
            else:
                data = json.loads(file_content)

            # Check if the data is a UTCP manual, an OpenAPI spec, or neither
            if isinstance(data, dict) and "version" in data and "tools" in data:
                self._log_info(f"Detected UTCP manual in '{file_path}'.")
                utcp_manual = UtcpManual(**data)
            elif isinstance(data, dict) and ('openapi' in data or 'swagger' in data or 'paths' in data):
                self._log_info(f"Assuming OpenAPI spec in '{file_path}'. Converting to UTCP manual.")
                converter = OpenApiConverter(data, spec_url=file_path.as_uri(), provider_name=manual_provider.name)
                utcp_manual = converter.convert()
            else:
                raise ValueError(f"File '{file_path}' is not a valid OpenAPI specification or UTCP manual")

            self._log_info(f"Successfully loaded {len(utcp_manual.tools)} tools from '{file_path}'")
            return utcp_manual.tools

        except FileNotFoundError:
            self._log_error(f"Tool definition file not found: {file_path}")
            raise
        except (json.JSONDecodeError, yaml.YAMLError) as e:
            self._log_error(f"Failed to parse file '{file_path}': {e}")
            raise
        except Exception as e:
            self._log_error(f"Unexpected error reading file '{file_path}': {e}")
            return []
    
    async def deregister_tool_provider(self, manual_provider: Provider) -> None:
        """Deregister a text provider.
        
        This is a no-op for text providers since they are stateless.
        
        Args:
            manual_provider: The provider to deregister
        """
        if isinstance(manual_provider, TextProvider):
            self._log_info(f"Deregistering text provider '{manual_provider.name}' (no-op)")
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], tool_provider: Provider) -> Any:
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
        if not isinstance(tool_provider, TextProvider):
            raise ValueError("TextTransport can only be used with TextProvider")
        
        file_path = Path(tool_provider.file_path)
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
