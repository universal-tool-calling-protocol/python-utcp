# UTCP Socket Plugin (UDP/TCP)

This plugin adds UDP and TCP communication protocols to UTCP 1.0.

## Running Tests

Prerequisites:
- Python 3.10+
- `pip`
- (Optional) a virtual environment

1) Install core and the socket plugin in editable mode with dev extras:

```bash
pip install -e "./core[dev]"
pip install -e "./plugins/communication_protocols/socket[dev]"
```

2) Run the socket plugin tests:

```bash
python -m pytest plugins/communication_protocols/socket/tests -v
```

3) Run a single test or filter by keyword:

```bash
# One file
python -m pytest plugins/communication_protocols/socket/tests/test_tcp_communication_protocol.py -v

# Filter by keyword (e.g., delimiter framing)
python -m pytest plugins/communication_protocols/socket/tests -k delimiter -q
```

4) Optional end-to-end sanity check (mock UDP/TCP servers):

```bash
python scripts/socket_sanity.py
```

Notes:
- On Windows, your firewall may prompt the first time tests open UDP/TCP sockets; allow access or run as admin if needed.
- Tests use `pytest-asyncio`. The dev extras installed above provide required dependencies.
- Streaming is single-chunk by design, consistent with HTTP/Text transports. Multi-chunk streaming can be added later behind provider configuration.