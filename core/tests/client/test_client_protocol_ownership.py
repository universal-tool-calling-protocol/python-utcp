"""A client owns the protocol instances it creates from the factory registry.

Everything here goes through the public surface: the two registries on
``CommunicationProtocol``, ``UtcpClient.create``, ``register_manual``,
``call_tool`` and ``close``.
"""

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, List

import pytest

from utcp.data.call_template import CallTemplate
from utcp.data.register_manual_response import RegisterManualResult
from utcp.data.tool import JsonSchema, Tool
from utcp.data.utcp_manual import UtcpManual
from utcp.exceptions import UtcpProtocolCloseError, UtcpVariableNotFound
from utcp.data.utcp_client_config import UtcpClientConfig
from utcp.implementations.in_mem_tool_repository import InMemToolRepository
from utcp.interfaces.communication_protocol import CommunicationProtocol
from utcp.plugins.plugin_loader import ensure_plugins_initialized
from utcp.utcp_client import UtcpClient
from utcp_http.http_call_template import HttpCallTemplate


class RecordingProtocol(CommunicationProtocol):
    """Records which client-facing calls reached this instance, and how often it was closed."""

    def __init__(self):
        self.registered: List[str] = []
        self.called: List[str] = []
        self.closed = 0

    async def register_manual(self, caller: UtcpClient, manual_call_template: CallTemplate) -> RegisterManualResult:
        self.registered.append(manual_call_template.name)
        tool = Tool(
            name="ping",
            description="answers with the identity of the instance that served it",
            inputs=JsonSchema(type="object", properties={}),
            outputs=JsonSchema(type="object", properties={}),
            tags=[],
            tool_call_template=manual_call_template,
        )
        return RegisterManualResult(
            manual_call_template=manual_call_template,
            manual=UtcpManual(manual_version="1.0.0", tools=[tool]),
            success=True,
            errors=[],
        )

    async def deregister_manual(self, caller: UtcpClient, manual_call_template: CallTemplate) -> None:
        pass

    async def call_tool(self, caller: UtcpClient, tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> Any:
        self.called.append(tool_name)
        return {"served_by": id(self)}

    async def call_tool_streaming(self, caller: UtcpClient, tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> AsyncGenerator[Any, None]:
        yield await self.call_tool(caller, tool_name, tool_args, tool_call_template)

    async def close(self) -> None:
        self.closed += 1


def http_manual(name: str) -> HttpCallTemplate:
    return HttpCallTemplate(name=name, url="https://example.test/utcp", http_method="POST", call_template_type="http")


@pytest.fixture
def isolated_registries(monkeypatch):
    """Both registries start empty and are restored after the test.

    Plugins load lazily on the first ``UtcpClient.create()`` of the session and
    register into whatever dict holds the class attribute at that moment. They
    are loaded here first, so their registrations land in the ORIGINAL dicts
    (which the fixture restores) and never in the throwaway ones.
    """
    ensure_plugins_initialized()
    monkeypatch.setattr(CommunicationProtocol, "communication_protocols", {})
    monkeypatch.setattr(CommunicationProtocol, "communication_protocol_factories", {})


@pytest.fixture
def recording_factory(isolated_registries):
    """Registers a factory for ``http`` and returns the instances it made, in order."""
    made: List[RecordingProtocol] = []

    def factory() -> RecordingProtocol:
        protocol = RecordingProtocol()
        made.append(protocol)
        return protocol

    CommunicationProtocol.communication_protocol_factories["http"] = factory
    return made


class TestPerClientInstances:

    @pytest.mark.asyncio
    async def test_each_client_gets_its_own_instance_and_routes_to_it(self, recording_factory):
        client_a = await UtcpClient.create()
        client_b = await UtcpClient.create()
        assert len(recording_factory) == 2
        own_a, own_b = recording_factory

        await client_a.register_manual(http_manual("a_manual"))
        await client_b.register_manual(http_manual("b_manual"))
        result_a = await client_a.call_tool("a_manual.ping", {})
        result_b = await client_b.call_tool("b_manual.ping", {})

        assert own_a.registered == ["a_manual"] and own_a.called == ["a_manual.ping"]
        assert own_b.registered == ["b_manual"] and own_b.called == ["b_manual.ping"]
        assert result_a["served_by"] == id(own_a)
        assert result_b["served_by"] == id(own_b)

    @pytest.mark.asyncio
    async def test_a_factory_wins_over_a_shared_instance_of_the_same_type(self, recording_factory):
        shared = RecordingProtocol()
        CommunicationProtocol.communication_protocols["http"] = shared

        client = await UtcpClient.create()
        await client.register_manual(http_manual("m"))

        assert recording_factory[0].registered == ["m"]
        assert shared.registered == []

    @pytest.mark.asyncio
    async def test_a_shared_instance_registered_after_the_client_exists_is_still_used(self, isolated_registries):
        # Late registration in the shared registry keeps working: shared
        # instances are looked up live, not snapshotted at creation.
        client = await UtcpClient.create()
        shared = RecordingProtocol()
        CommunicationProtocol.communication_protocols["http"] = shared

        await client.register_manual(http_manual("m"))

        assert shared.registered == ["m"]

    @pytest.mark.asyncio
    async def test_a_factory_registered_after_the_client_exists_is_adopted_on_first_use_and_owned(self, isolated_registries):
        client = await UtcpClient.create()
        made: List[RecordingProtocol] = []

        def factory() -> RecordingProtocol:
            protocol = RecordingProtocol()
            made.append(protocol)
            return protocol

        CommunicationProtocol.communication_protocol_factories["http"] = factory

        await client.register_manual(http_manual("m"))
        await client.register_manual(http_manual("n"))
        # One instance, made on first use, serving every later call...
        assert len(made) == 1
        assert made[0].registered == ["m", "n"]
        # ...and owned: the client's close() reaches it.
        await client.close()
        assert made[0].closed == 1

    @pytest.mark.asyncio
    async def test_a_type_with_no_protocol_in_either_registry_names_what_is_available(self, isolated_registries):
        # "http" has a serializer (the plugin is imported) but, with the
        # registries isolated, no protocol in either of them.
        CommunicationProtocol.communication_protocol_factories["cli"] = RecordingProtocol
        CommunicationProtocol.communication_protocols["text"] = RecordingProtocol()
        client = await UtcpClient.create()

        with pytest.raises(ValueError, match=r"type http found, available types: \['cli', 'text'\]"):
            await client.register_manual(http_manual("m"))


class TestCloseIsScopedToWhatTheClientOwns:

    @pytest.mark.asyncio
    async def test_close_drains_own_instance_and_leaves_other_clients_and_shared_ones_running(self, recording_factory):
        shared = RecordingProtocol()
        CommunicationProtocol.communication_protocols["cli"] = shared
        client_a = await UtcpClient.create()
        client_b = await UtcpClient.create()
        own_a, own_b = recording_factory

        await client_a.close()

        assert own_a.closed == 1
        assert own_b.closed == 0
        # Every other client in the process is still using this one.
        assert shared.closed == 0

        await client_b.close()
        assert own_b.closed == 1
        assert shared.closed == 0

    @pytest.mark.asyncio
    async def test_close_waits_for_every_owned_protocol_even_when_one_fails(self, isolated_registries):
        # The failing close raises IMMEDIATELY; the healthy one takes a moment.
        # A first-failure-wins close would return before the healthy one ended.
        class FailingProtocol(RecordingProtocol):
            async def close(self) -> None:
                raise RuntimeError("transport refused to close")

        class SlowProtocol(RecordingProtocol):
            async def close(self) -> None:
                await asyncio.sleep(0.02)
                self.closed += 1

        slow = SlowProtocol()
        CommunicationProtocol.communication_protocol_factories["http"] = FailingProtocol
        CommunicationProtocol.communication_protocol_factories["cli"] = lambda: slow

        client = await UtcpClient.create()
        with pytest.raises(UtcpProtocolCloseError) as raised:
            await client.close()

        # The failure is still surfaced, with its cause inside...
        assert len(raised.value.failures) == 1
        assert isinstance(raised.value.failures[0], RuntimeError)
        # ...but only after every owned protocol has finished closing.
        assert slow.closed == 1


class TestFailedCreateClosesWhatItCreated:

    @pytest.mark.asyncio
    async def test_an_instance_made_for_a_create_that_fails_is_closed_not_orphaned(self, recording_factory):
        # The factory fires, then variable substitution fails on a reference
        # nothing can resolve — create() raises and the caller never gets a
        # client to close.
        with pytest.raises(UtcpVariableNotFound):
            await UtcpClient.create(config={"variables": {"DERIVED": "${NOWHERE_TO_BE_FOUND}"}})

        assert len(recording_factory) == 1
        assert recording_factory[0].closed == 1

    @pytest.mark.asyncio
    async def test_a_factory_that_raises_leaves_the_instances_before_it_closed(self, recording_factory):
        def broken_factory() -> CommunicationProtocol:
            raise RuntimeError("no transport available")

        CommunicationProtocol.communication_protocol_factories["cli"] = broken_factory

        with pytest.raises(RuntimeError, match="no transport available"):
            await UtcpClient.create()

        assert len(recording_factory) == 1
        assert recording_factory[0].closed == 1

    @pytest.mark.asyncio
    async def test_a_shared_instance_survives_a_failed_create(self, recording_factory):
        shared = RecordingProtocol()
        CommunicationProtocol.communication_protocols["cli"] = shared

        with pytest.raises(UtcpVariableNotFound):
            await UtcpClient.create(config={"variables": {"DERIVED": "${NOWHERE_TO_BE_FOUND}"}})

        assert recording_factory[0].closed == 1
        assert shared.closed == 0

    @pytest.mark.asyncio
    async def test_a_failing_cleanup_is_reported_and_the_original_error_surfaces(self, isolated_registries, caplog):
        class FailingProtocol(RecordingProtocol):
            async def close(self) -> None:
                raise RuntimeError("transport refused to close")

        CommunicationProtocol.communication_protocol_factories["http"] = FailingProtocol

        with caplog.at_level(logging.ERROR, logger="utcp.implementations.utcp_client_implementation"):
            with pytest.raises(UtcpVariableNotFound):
                await UtcpClient.create(config={"variables": {"DERIVED": "${NOWHERE_TO_BE_FOUND}"}})

        reported = [record for record in caplog.records if "closing the protocols it had created failed too" in record.getMessage()]
        assert len(reported) == 1
        assert "transport refused to close" in reported[0].exc_text


def unresolvable_http_manual(name: str) -> HttpCallTemplate:
    """A template whose registration raises UtcpVariableNotFound before it reaches any protocol."""
    return HttpCallTemplate(name=name, url="https://example.test/${NOWHERE_TO_BE_FOUND}", http_method="POST", call_template_type="http")


class SlowRegisteringProtocol(RecordingProtocol):
    """Registration takes a moment and is recorded in a shared event log, as is close()."""

    def __init__(self, events: List[str]):
        super().__init__()
        self.events = events

    async def register_manual(self, caller: UtcpClient, manual_call_template: CallTemplate) -> RegisterManualResult:
        await asyncio.sleep(0.02)
        self.events.append(f"registered {manual_call_template.name}")
        return await super().register_manual(caller, manual_call_template)

    async def close(self) -> None:
        await super().close()
        self.events.append("closed")


class TestABatchRegistrationSettlesEverySiblingBeforeRaising:

    @pytest.mark.asyncio
    async def test_register_manuals_raises_only_once_every_sibling_registration_has_finished(self, isolated_registries):
        # The first manual fails immediately (unresolvable variable); the
        # second is still registering. A first-failure-wins gather would raise
        # with the second still running underneath the caller.
        events: List[str] = []
        CommunicationProtocol.communication_protocols["http"] = SlowRegisteringProtocol(events)
        client = await UtcpClient.create()

        with pytest.raises(UtcpVariableNotFound):
            await client.register_manuals([unresolvable_http_manual("bad_manual"), http_manual("slow_manual")])

        assert events == ["registered slow_manual"]

    @pytest.mark.asyncio
    async def test_a_failed_create_closes_its_protocols_only_after_every_registration_has_finished(self, isolated_registries):
        # Same batch, through create(): the owned protocol must not be closed
        # while a sibling registration is still using it.
        events: List[str] = []
        CommunicationProtocol.communication_protocol_factories["http"] = lambda: SlowRegisteringProtocol(events)

        with pytest.raises(UtcpVariableNotFound):
            await UtcpClient.create(config={"manual_call_templates": [
                unresolvable_http_manual("bad_manual"),
                http_manual("slow_manual"),
            ]})

        assert events == ["registered slow_manual", "closed"]


class TestAFailedCreateLeavesNoManualBehind:

    @pytest.mark.asyncio
    async def test_a_manual_registered_by_the_failed_attempt_is_removed_from_a_shared_repository(self, isolated_registries):
        # The caller supplies (and keeps) the repository; the second manual
        # registers fine before the first one's failure surfaces. create()
        # raises -- and must not leave that manual behind in the caller's repo.
        CommunicationProtocol.communication_protocols["http"] = RecordingProtocol()
        repo = InMemToolRepository()

        with pytest.raises(UtcpVariableNotFound):
            await UtcpClient.create(config=UtcpClientConfig(
                tool_repository=repo,
                manual_call_templates=[unresolvable_http_manual("bad_manual"), http_manual("good_manual")],
            ))

        assert await repo.get_manual("good_manual") is None
        assert await repo.get_tool("good_manual.ping") is None

    @pytest.mark.asyncio
    async def test_a_manual_that_was_in_the_repository_before_the_attempt_survives_it(self, isolated_registries):
        # "existing" is already registered by an earlier client on the same
        # shared repository. This attempt names it again (that registration
        # fails as a duplicate, without raising) and also fails outright on
        # the bad manual. The rollback must remove only what THIS attempt
        # added -- never the pre-existing manual.
        CommunicationProtocol.communication_protocols["http"] = RecordingProtocol()
        repo = InMemToolRepository()
        earlier = await UtcpClient.create(config=UtcpClientConfig(tool_repository=repo, manual_call_templates=[http_manual("existing")]))
        assert await repo.get_manual("existing") is not None

        with pytest.raises(UtcpVariableNotFound):
            await UtcpClient.create(config=UtcpClientConfig(
                tool_repository=repo,
                manual_call_templates=[http_manual("existing"), unresolvable_http_manual("bad_manual"), http_manual("added_by_attempt")],
            ))

        assert await repo.get_manual("existing") is not None
        assert await repo.get_manual("added_by_attempt") is None
        await earlier.close()


def test_plugin_registrations_survive_the_isolated_tests_above():
    # Runs after every isolated test in this file. If any of them had been the
    # session's first create() and the fixture had patched the registry before
    # plugins loaded, the plugin instances would have gone into the throwaway
    # dict and be missing here.
    ensure_plugins_initialized()
    assert "http" in CommunicationProtocol.communication_protocols
    assert "mcp" in CommunicationProtocol.communication_protocol_factories
