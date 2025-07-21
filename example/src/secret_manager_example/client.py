import asyncio
from os import getcwd
from typing import Optional
from google.cloud import secretmanager
from utcp.client.utcp_client import UtcpClient
from utcp.client.utcp_client_config import UtcpClientConfig, UtcpVariablesConfig


class UtcpGcpSecretManager(UtcpVariablesConfig):
    """Configuration for UTCP GCP Secret Manager client."""
    def __init__(self, project_id: str):
        self.secrets_path = f"projects/{project_id}/secrets"
        self.client = secretmanager.SecretManagerServiceClient()

    def get(self, key: str, version: str = "latest") -> Optional[str]:
        """Get a specific secret by key."""
        request = {"name": f"{self.secrets_path}/{key}/versions/{version}"}
        response = self.client.access_secret_version(request=request)
        secret_value = response.payload.data.decode('UTF-8')
        return secret_value

async def main():
    client: UtcpClient = await UtcpClient.create(
        config=UtcpClientConfig(
            providers_file_path=str(getcwd() + "/providers.json"),
            load_variables_from=[
                UtcpGcpSecretManager(project_id="your-gcp-project-id")
            ]
        )
    )

    # List all available tools
    print("Registered tools:")
    for tool in await client.tool_repository.get_tools():
        print(f" - {tool.name}")

    # Call one of the tools
    tool_to_call = (await client.tool_repository.get_tools())[0].name
    args = {"body": {"value": "test"}}

    result = await client.call_tool(tool_to_call, args)
    print(f"\nTool call result for '{tool_to_call}':")
    print(result)

if __name__ == "__main__":
    asyncio.run(main())
