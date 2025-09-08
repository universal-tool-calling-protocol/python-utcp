# OpenAPI Ingestion Methods in python-utcp

UTCP automatically converts OpenAPI 2.0/3.0 specifications into UTCP tools, enabling AI agents to interact with REST APIs without requiring server modifications or additional infrastructure.

## Method 1: Direct OpenAPI Converter

Use the `OpenApiConverter` class for maximum control over the conversion process.

```python
from utcp_http.openapi_converter import OpenApiConverter  # utcp-http plugin
import json

# From local JSON file
with open("api_spec.json", "r") as f:
    openapi_spec = json.load(f)

converter = OpenApiConverter(openapi_spec)
manual = converter.convert()

print(f"Generated {len(manual.tools)} tools")
```

```python
from utcp_http.openapi_converter import OpenApiConverter  # utcp-http plugin
import yaml

# From YAML file (can also be JSON)
with open("api_spec.yaml", "r") as f:
    openapi_spec = yaml.safe_load(f)

converter = OpenApiConverter(openapi_spec)
manual = converter.convert()
```

## Method 2: Remote OpenAPI Specification

Fetch and convert OpenAPI specifications from remote URLs.

```python
import aiohttp
from utcp_http.openapi_converter import OpenApiConverter  # utcp-http plugin

async def load_remote_spec(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            openapi_spec = await response.json()
    
    converter = OpenApiConverter(openapi_spec, spec_url=url)
    return converter.convert()

# Usage
manual = await load_remote_spec("https://api.example.com/openapi.json")
```

## Method 3: UTCP Client Configuration

Include OpenAPI specs directly in your UTCP client configuration.

```python
from utcp.utcp_client import UtcpClient  # core utcp package

config = {
    "manual_call_templates": [
        {
            "name": "weather_api",
            "call_template_type": "http",
            "url": "https://api.weather.com/openapi.json",
            "http_method": "GET"
        }
    ]
}

client = await UtcpClient.create(config=config)
```

```python
# With authentication
config = {
    "manual_call_templates": [
        {
            "name": "authenticated_api",
            "call_template_type": "http", 
            "url": "https://api.example.com/openapi.json",
            "auth": {
                "auth_type": "api_key",
                "api_key": "${API_KEY}",
                "var_name": "Authorization",
                "location": "header"
            }
        }
    ]
}
```

## Method 4: Batch Processing

Process multiple OpenAPI specifications programmatically.

```python
import aiohttp
from utcp_http.openapi_converter import OpenApiConverter  # utcp-http plugin
from utcp.data.utcp_manual import UtcpManual  # core utcp package

async def process_multiple_specs(spec_urls):
    all_tools = []
    
    for i, url in enumerate(spec_urls):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                openapi_spec = await response.json()
        
        converter = OpenApiConverter(openapi_spec, spec_url=url, call_template_name=f"api_{i}")
        manual = converter.convert()
        all_tools.extend(manual.tools)
    
    return UtcpManual(tools=all_tools)

# Usage
spec_urls = [
    "https://api.github.com/openapi.json",
    "https://api.stripe.com/openapi.yaml"
]

combined_manual = await process_multiple_specs(spec_urls)
```

## Key Features

### Authentication Mapping
OpenAPI security schemes automatically convert to UTCP auth objects:

- `apiKey` → `ApiKeyAuth`
- `http` (basic) → `BasicAuth` 
- `http` (bearer) → `ApiKeyAuth`
- `oauth2` → `OAuth2Auth`

### Multi-format Support
- **OpenAPI 2.0 & 3.0**: Full compatibility
- **JSON & YAML**: Automatic format detection
- **Local & Remote**: Files or URLs

### Schema Resolution
- Handles `$ref` references automatically
- Resolves nested object definitions
- Detects circular references

## Examples

See the [examples repository](https://github.com/universal-tool-calling-protocol/utcp-examples) for complete working examples.
