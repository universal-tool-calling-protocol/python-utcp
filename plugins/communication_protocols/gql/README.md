
UTCP GraphQL Communication Protocol Plugin

This plugin integrates GraphQL as a UTCP 1.0 communication protocol and call template. It supports discovery via schema introspection, authenticated calls, and header handling.

Getting Started

Installation

```bash
pip install gql
```

Registration

```python
import utcp_gql
utcp_gql.register()
```

How To Use

- Ensure the plugin is imported and registered: `import utcp_gql; utcp_gql.register()`.
- Add a manual in your client config:
  ```json
  {
    "name": "my_graph",
    "call_template_type": "graphql",
    "url": "https://your.graphql/endpoint",
    "operation_type": "query",
    "headers": { "x-client": "utcp" },
    "header_fields": ["x-session-id"]
  }
  ```
- Call a tool:
  ```python
  await client.call_tool("my_graph.someQuery", {"id": "123", "x-session-id": "abc"})
  ```

Notes

- Tool names are prefixed by the manual name (e.g., `my_graph.someQuery`).
- Headers merge static `headers` plus whitelisted dynamic fields from `header_fields`.
- Supported auth: API key, Basic auth, OAuth2 (client-credentials).
- Security: only `https://` or `http://localhost`/`http://127.0.0.1` endpoints.

For UTCP core docs, see https://github.com/universal-tool-calling-protocol/python-utcp.