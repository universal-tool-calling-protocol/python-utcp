# OpenAPI Ingestion Methods in python-utcp

UTCP provides powerful capabilities for automatically converting existing OpenAPI specifications into UTCP tools, enabling AI agents to interact with REST APIs without requiring any server modifications or additional infrastructure.

## Overview

The OpenAPI ingestion feature allows you to:
- **Convert existing APIs**: Transform any OpenAPI 2.0 or 3.0 specification into UTCP tools
- **Zero infrastructure**: No wrapper servers or API modifications required
- **Direct API calls**: Tools call original APIs directly with native performance
- **Automatic schema mapping**: OpenAPI schemas become UTCP input/output definitions
- **Authentication preservation**: OpenAPI security schemes map to UTCP auth objects

## Method 1: Direct OpenAPI Converter

Use the `OpenApiConverter` class directly for maximum control over the conversion process.

### From Local JSON File

```python
from utcp_http.openapi_converter import OpenApiConverter
import json

# Load OpenAPI spec from local JSON file
with open("api_spec.json", "r") as f:
    openapi_spec = json.load(f)

converter = OpenApiConverter(openapi_spec)
manual = converter.convert()

# Use the generated manual
print(f"Generated {len(manual.tools)} tools")
for tool in manual.tools:
    print(f"- {tool.name}: {tool.description}")
```

### From Local YAML File

```python
from utcp_http.openapi_converter import OpenApiConverter
import yaml

# Load OpenAPI spec from local YAML file
with open("api_spec.yaml", "r") as f:
    openapi_spec = yaml.safe_load(f)

converter = OpenApiConverter(openapi_spec)
manual = converter.convert()
```

### With Custom Call Template Name

```python
converter = OpenApiConverter(
    openapi_spec, 
    spec_url="https://api.example.com/openapi.json",
    call_template_name="my_custom_api"
)
manual = converter.convert()
```

## Method 2: Remote OpenAPI Specification

Fetch and convert OpenAPI specifications from remote URLs.

```python
import aiohttp
from utcp_http.openapi_converter import OpenApiConverter

async def load_remote_spec():
    url = "https://api.example.com/openapi.json"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()
            openapi_spec = await response.json()
    
    converter = OpenApiConverter(openapi_spec, spec_url=url)
    return converter.convert()

# Usage
manual = await load_remote_spec()
```

### With Error Handling

```python
async def load_remote_spec_safe(url: str):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                
                # Handle both JSON and YAML responses
                content_type = response.headers.get('content-type', '')
                if 'yaml' in content_type or url.endswith('.yaml'):
                    import yaml
                    text = await response.text()
                    openapi_spec = yaml.safe_load(text)
                else:
                    openapi_spec = await response.json()
        
        converter = OpenApiConverter(openapi_spec, spec_url=url)
        return converter.convert()
        
    except Exception as e:
        print(f"Error loading OpenAPI spec from {url}: {e}")
        return None
```

## Method 3: Using UTCP Client Configuration

Include OpenAPI specs directly in your UTCP client configuration using HTTP call templates.

```python
from utcp.utcp_client import UtcpClient

async def use_openapi_via_config():
    # Configure client to automatically detect and convert OpenAPI specs
    config = {
        "manual_call_templates": [
            {
                "name": "weather_api",
                "call_template_type": "http",
                "url": "https://api.weather.com/openapi.json",  # Points to OpenAPI spec
                "http_method": "GET"
            }
        ]
    }

    client = await UtcpClient.create(config=config)
    print("Client configured with OpenAPI spec")
    return client

# Usage
client = await use_openapi_via_config()
```

### With Authentication

```python
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

## Method 4: Batch Processing Multiple Specs

Process multiple OpenAPI specifications programmatically using the converter directly.

```python
import aiohttp
from utcp_http.openapi_converter import OpenApiConverter
from utcp.data.utcp_manual import UtcpManual

async def process_multiple_specs(spec_urls):
    all_tools = []
    
    for i, url in enumerate(spec_urls):
        try:
            # Fetch OpenAPI spec
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    response.raise_for_status()
                    openapi_spec = await response.json()
            
            # Convert to UTCP tools
            converter = OpenApiConverter(openapi_spec, spec_url=url, call_template_name=f"api_{i}")
            manual = converter.convert()
            all_tools.extend(manual.tools)
            print(f"✓ Processed {url}: {len(manual.tools)} tools")
            
        except Exception as e:
            print(f"✗ Failed to process {url}: {e}")
    
    return all_tools

# Usage
spec_urls = [
    "https://api.github.com/openapi.json",
    "https://api.stripe.com/openapi.yaml", 
    "https://api.twilio.com/swagger.json"
]

all_tools = await process_multiple_specs(spec_urls)
print(f"Total tools processed: {len(all_tools)}")

# Create combined manual and save to file
combined_manual = UtcpManual(tools=all_tools)
with open("combined_manual.json", "w") as f:
    f.write(combined_manual.model_dump_json(indent=2))
```

### Script Features

- **Batch processing**: Combine multiple OpenAPI specs
- **Deduplication**: Automatically handles duplicate tool names
- **Error handling**: Continues processing if individual specs fail
- **File output**: Save combined manual to JSON file

## Method 5: Batch Processing Multiple Specs

Process multiple OpenAPI specifications programmatically using the converter directly.

```python
import aiohttp
from utcp_http.openapi_converter import OpenApiConverter
from utcp.data.utcp_manual import UtcpManual

async def process_multiple_specs(spec_urls):
    all_tools = []
    
    for i, url in enumerate(spec_urls):
        try:
            # Fetch OpenAPI spec
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    response.raise_for_status()
                    openapi_spec = await response.json()
            
            # Convert to UTCP tools
            converter = OpenApiConverter(openapi_spec, spec_url=url, call_template_name=f"api_{i}")
            manual = converter.convert()
            all_tools.extend(manual.tools)
            print(f"✓ Processed {url}: {len(manual.tools)} tools")
            
        except Exception as e:
            print(f"✗ Failed to process {url}: {e}")
    
    return all_tools

# Usage
spec_urls = [
    "https://api.github.com/openapi.json",
    "https://api.stripe.com/openapi.yaml", 
    "https://api.twilio.com/swagger.json"
]

all_tools = await process_multiple_specs(spec_urls)
print(f"Total tools processed: {len(all_tools)}")

# Create combined manual
combined_manual = UtcpManual(tools=all_tools)
```

## Method 5: Integration with UTCP Client Configuration

Include OpenAPI specs directly in your UTCP client configuration.

```python
from utcp.utcp_client import UtcpClient

# Configuration with OpenAPI specs
config = {
    "variables": {
        "GITHUB_API_KEY": "${GITHUB_TOKEN}",
        "STRIPE_API_KEY": "${STRIPE_SECRET_KEY}"
    },
    "manual_call_templates": [
        {
            "name": "github_api",
            "call_template_type": "http",
            "url": "https://api.github.com/openapi.json",
            "auth": {
                "auth_type": "api_key",
                "api_key": "Bearer ${GITHUB_API_KEY}",
                "var_name": "Authorization",
                "location": "header"
            }
        },
        {
            "name": "stripe_api", 
            "call_template_type": "http",
            "url": "https://api.stripe.com/openapi.yaml",
            "auth": {
                "auth_type": "api_key",
                "api_key": "${STRIPE_API_KEY}",
                "var_name": "Authorization", 
                "location": "header"
            }
        }
    ]
}

client = await UtcpClient.create(config=config)
```

## Key Features

### Automatic Schema Resolution
- **JSON References**: Handles `$ref` references in OpenAPI specs
- **Nested schemas**: Resolves complex nested object definitions
- **Circular references**: Detects and handles circular schema references

### Authentication Mapping
OpenAPI security schemes are automatically converted to UTCP auth objects:

| OpenAPI Security | UTCP Auth | Example |
|------------------|-----------|---------|
| `apiKey` | `ApiKeyAuth` | API keys in headers/query/cookies |
| `http` (basic) | `BasicAuth` | Username/password authentication |
| `http` (bearer) | `ApiKeyAuth` | Bearer tokens |
| `oauth2` | `OAuth2Auth` | OAuth2 flows |

### Multi-format Support
- **OpenAPI 2.0**: Full support for Swagger 2.0 specifications
- **OpenAPI 3.0**: Complete OpenAPI 3.0+ compatibility
- **JSON/YAML**: Automatic format detection and parsing

### Version Compatibility
- **OpenAPI 2.0**: `securityDefinitions`, `swagger` field
- **OpenAPI 3.0**: `components.securitySchemes`, `openapi` field
- **Mixed specs**: Handles specifications with mixed version elements

## Advanced Usage

### Custom Placeholder Variables

```python
from utcp_http.openapi_converter import OpenApiConverter

# Converter automatically generates unique placeholders
converter = OpenApiConverter(openapi_spec)
manual = converter.convert()

# Placeholders are generated as ${VARIABLE_NAME_1}, ${VARIABLE_NAME_2}, etc.
# This ensures no conflicts when combining multiple specs
```

### Error Handling and Validation

```python
def safe_convert_openapi(spec_data, spec_url=None):
    try:
        converter = OpenApiConverter(spec_data, spec_url=spec_url)
        manual = converter.convert()
        
        if not manual.tools:
            print("Warning: No tools generated from OpenAPI spec")
            return None
            
        # Validate generated tools
        for tool in manual.tools:
            if not tool.name or not tool.tool_call_template:
                print(f"Warning: Invalid tool generated: {tool.name}")
                
        return manual
        
    except Exception as e:
        print(f"Error converting OpenAPI spec: {e}")
        return None
```

### Filtering and Post-processing

```python
def filter_openapi_tools(manual, include_tags=None, exclude_operations=None):
    """Filter tools based on tags or operation IDs"""
    filtered_tools = []
    
    for tool in manual.tools:
        # Filter by tags
        if include_tags and not any(tag in tool.tags for tag in include_tags):
            continue
            
        # Exclude specific operations
        if exclude_operations and tool.name in exclude_operations:
            continue
            
        filtered_tools.append(tool)
    
    manual.tools = filtered_tools
    return manual

# Usage
manual = converter.convert()
manual = filter_openapi_tools(
    manual, 
    include_tags=["public", "v1"],
    exclude_operations=["deprecated_endpoint"]
)
```

## Best Practices

### 1. Environment Variables for Secrets
```python
# Use environment variables for API keys and secrets
config = {
    "variables": {
        "API_KEY": "${MY_API_KEY}",  # Will be loaded from environment
        "BASE_URL": "https://api.example.com"
    }
}
```

### 2. Error Handling
```python
async def robust_openapi_loading(urls):
    successful_manuals = []
    
    for url in urls:
        try:
            # Load and convert spec
            manual = await load_remote_spec(url)
            if manual and manual.tools:
                successful_manuals.append(manual)
        except Exception as e:
            print(f"Failed to load {url}: {e}")
            continue
    
    return successful_manuals
```

### 3. Caching OpenAPI Specs
```python
import json
from pathlib import Path

def cache_openapi_spec(url, cache_dir="./cache"):
    """Cache OpenAPI specs locally to avoid repeated downloads"""
    cache_path = Path(cache_dir) / f"{url.replace('/', '_').replace(':', '')}.json"
    
    if cache_path.exists():
        with open(cache_path) as f:
            return json.load(f)
    
    # Download and cache
    spec = download_openapi_spec(url)  # Your download function
    cache_path.parent.mkdir(exist_ok=True)
    with open(cache_path, 'w') as f:
        json.dump(spec, f)
    
    return spec
```

## Troubleshooting

### Common Issues

1. **No tools generated**: Check if OpenAPI spec has valid `operationId` fields
2. **Authentication errors**: Verify security schemes are properly defined
3. **Schema resolution failures**: Check for circular references in schemas
4. **Invalid URLs**: Ensure base URLs are properly specified in OpenAPI spec

### Debug Mode

```python
import logging

# Enable debug logging to see conversion details
logging.basicConfig(level=logging.DEBUG)

converter = OpenApiConverter(openapi_spec)
manual = converter.convert()
```

## Examples

See the [examples repository](https://github.com/universal-tool-calling-protocol/utcp-examples) for complete working examples of OpenAPI ingestion with popular APIs like:

- GitHub API
- Stripe API  
- OpenAI API
- Twilio API
- And many more...

## Conclusion

OpenAPI ingestion in UTCP provides a seamless way to make existing REST APIs available to AI agents without any infrastructure changes. The automatic conversion process handles the complexity of schema mapping, authentication, and protocol translation, allowing you to focus on building powerful AI applications.
