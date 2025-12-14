# UTCP gNMI Plugin

This plugin adds a gNMI (gRPC) communication protocol compatible with UTCP 1.0. It follows UTCP’s plugin architecture: a CallTemplate and serializer, a CommunicationProtocol for discovery and execution, and registration via the `utcp.plugins` entry point.

## Installation

- Ensure you have Python 3.10+
- Dependencies: `utcp`, `grpcio`, `protobuf`, `pydantic`, `aiohttp`
- Install in your environment (example if published):

```
pip install utcp-gnmi
```

## Registration

Register the plugin into UTCP’s registries:

```
from utcp_gnmi import register
register()
```

This registers:
- Protocol: `gnmi`
- Call template serializer: `gnmi`

## Configuration (UTCP 1.0)

Use `UtcpClientConfig.manual_call_templates` to declare gNMI providers and tools.

Example:

```
{
  "manual_call_templates": [
    {
      "name": "routerA",
      "call_template_type": "gnmi",
      "target": "localhost:50051",
      "use_tls": false,
      "metadata": {"authorization": "Bearer ${API_TOKEN}"},
      "metadata_fields": ["tenant-id"],
      "operation": "get",
      "stub_module": "gnmi_pb2_grpc",
      "message_module": "gnmi_pb2"
    }
  ]
}
```

Fields:
- `call_template_type`: must be `gnmi`
- `target`: gRPC host:port
- `use_tls`: boolean; TLS required unless localhost/127.0.0.1
- `metadata`: static key/value pairs added to gRPC metadata
- `metadata_fields`: dynamic keys populated from tool args
- `operation`: one of `capabilities`, `get`, `set`, `subscribe`
- `stub_module`/`message_module`: import paths to generated Python stubs

## Security

- Enforces TLS (`grpc.aio.secure_channel`) unless `target` is `localhost` or `127.0.0.1`
- Do not use insecure channels over public networks
- Prefer mTLS for production environments (future enhancement adds cert fields)

## Authentication

Supported via UTCP `Auth` model:
- API Key: injects into `authorization` (or custom) metadata
- Basic: `authorization: Basic <base64(user:pass)>`
- OAuth2: client credentials; token fetched via `aiohttp` and cached

## Operations

- `capabilities`: unary `Capabilities` RPC
- `get`: unary `Get` RPC; maps `paths` list into `GetRequest.path`
- `set`: unary `Set` RPC; maps `updates` list into `SetRequest.update`
- `subscribe`: streaming `Subscribe` RPC; yields responses as dicts

## Testing

Run tests:

```
python -m pytest plugins/communication_protocols/gnmi/tests/test_gnmi_plugin.py -q
```

The tests validate manual registration, tool presence (including `subscribe`), and serializer round-trip.

## Notes

- Tool discovery registers canonical gNMI operations (`capabilities/get/set/subscribe`)
- Reflection-based discovery and mTLS configuration can be added in follow-up PRs