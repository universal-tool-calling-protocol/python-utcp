from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from utcp.shared.provider import Provider
from utcp.shared.tool import Tool

class ToolRepository(ABC):
    @abstractmethod
    async def save_provider_with_tools(self, provider: Provider, tools: List[Tool]) -> None:
        """
        Save a provider and its tools in the repository.

        Args:
            provider: The provider to save.
            tools: The tools associated with the provider.
        """
        pass

    @abstractmethod
    async def remove_provider(self, provider_name: str) -> None:
        """
        Remove a provider and its tools from the repository.

        Args:
            provider_name: The name of the provider to remove.

        Raises:
            ValueError: If the provider is not found.
        """
        pass

    @abstractmethod
    async def remove_tool(self, tool_name: str) -> None:
        """
        Remove a tool from the repository.

        Args:
            tool_name: The name of the tool to remove.

        Raises:
            ValueError: If the tool is not found.
        """
        pass

    @abstractmethod
    async def get_tool(self, tool_name: str) -> Optional[Tool]:
        """
        Get a tool from the repository.

        Args:
            tool_name: The name of the tool to retrieve.

        Returns:
            The tool if found, otherwise None.
        """
        pass

    @abstractmethod
    async def get_tools(self) -> List[Tool]:
        """
        Get all tools from the repository.

        Returns:
            A list of tools.
        """
        pass
    
    @abstractmethod
    async def get_tools_by_provider(self, provider_name: str) -> Optional[List[Tool]]:
        """
        Get tools associated with a specific provider.

        Args:
            provider_name: The name of the provider.

        Returns:
            A list of tools associated with the provider, or None if the provider is not found.
        """
        pass

    @abstractmethod
    async def get_provider(self, provider_name: str) -> Optional[Provider]:
        """
        Get a provider from the repository.

        Args:
            provider_name: The name of the provider to retrieve.

        Returns:
            The provider if found, otherwise None.
        """
        pass

    @abstractmethod
    async def get_providers(self) -> List[Provider]:
        """
        Get all providers from the repository.

        Returns:
            A list of providers.
        """
        pass
