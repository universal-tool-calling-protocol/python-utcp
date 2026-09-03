"""A manual stays usable when it names things this client does not know."""

import logging

import pytest

from utcp.data.call_template import CallTemplate, CallTemplateSerializer
from utcp.data.utcp_manual import UtcpManualSerializer
from utcp.exceptions import UtcpSerializerValidationError


class _MockCallTemplate(CallTemplate):
    call_template_type: str = "mock"


class _MockCallTemplateSerializer:
    def to_dict(self, obj):
        return obj.model_dump()

    def validate_dict(self, obj):
        return _MockCallTemplate.model_validate(obj)


@pytest.fixture(autouse=True)
def register_mock_protocol():
    CallTemplateSerializer.call_template_serializers["mock"] = _MockCallTemplateSerializer()
    yield
    CallTemplateSerializer.call_template_serializers.pop("mock", None)


def _tool(name: str, call_template: dict) -> dict:
    return {
        "name": name,
        "description": "",
        "inputs": {"type": "object"},
        "tool_call_template": call_template,
    }


def test_unknown_call_template_type_skips_only_that_tool(caplog):
    manual_dict = {
        "utcp_version": "1.0.1",
        "manual_version": "1.0.0",
        "tools": [
            _tool("known", {"call_template_type": "mock"}),
            _tool("future", {"call_template_type": "quantum_teleport", "qubits": 4}),
        ],
    }

    with caplog.at_level(logging.WARNING):
        manual = UtcpManualSerializer().validate_dict(manual_dict)

    assert [t.name for t in manual.tools] == ["known"]
    assert "future" in caplog.text
    assert "quantum_teleport" in caplog.text


def test_unknown_keys_are_kept_and_round_trip():
    manual_dict = {
        "utcp_version": "1.0.1",
        "manual_version": "1.0.0",
        "info": {"title": "Weather API", "version": "1.0.0"},
        "tools": [
            _tool("known", {"call_template_type": "mock", "x-acme-retry": {"attempts": 3}}),
        ],
    }

    manual = UtcpManualSerializer().validate_dict(manual_dict)

    assert manual.model_extra["info"] == {"title": "Weather API", "version": "1.0.0"}
    assert manual.tools[0].tool_call_template.model_extra["x-acme-retry"] == {"attempts": 3}

    as_dict = UtcpManualSerializer().to_dict(manual)
    assert as_dict["info"] == {"title": "Weather API", "version": "1.0.0"}


def test_malformed_call_template_still_fails_loudly():
    manual_dict = {
        "utcp_version": "1.0.1",
        "manual_version": "1.0.0",
        "tools": [_tool("broken", {"url": "https://example.com"})],
    }

    with pytest.raises(UtcpSerializerValidationError):
        UtcpManualSerializer().validate_dict(manual_dict)
