import importlib
import logging
from typing import Dict, Any, List, AsyncGenerator

from utcp.interfaces.communication_protocol import CommunicationProtocol
from utcp.data.call_template import CallTemplate
from utcp.data.tool import Tool, JsonSchema
from utcp.data.utcp_manual import UtcpManual
from utcp.data.register_manual_response import RegisterManualResult
from utcp_gnmi.gnmi_call_template import GnmiCallTemplate
from utcp.data.auth_implementations.api_key_auth import ApiKeyAuth
from utcp.data.auth_implementations.basic_auth import BasicAuth
from utcp.data.auth_implementations.oauth2_auth import OAuth2Auth

class GnmiCommunicationProtocol(CommunicationProtocol):
    def __init__(self):
        self._oauth_tokens: Dict[str, Dict[str, Any]] = {}
    def _load_gnmi_modules(self, tool_call_template: GnmiCallTemplate) -> tuple[Any, Any, Any, Any, Any]:
        grpc = importlib.import_module("grpc")
        aio = importlib.import_module("grpc.aio")
        json_format = importlib.import_module("google.protobuf.json_format")
        stub_mod = importlib.import_module(tool_call_template.stub_module)
        msg_mod = importlib.import_module(tool_call_template.message_module)
        return grpc, aio, json_format, stub_mod, msg_mod
    def _create_grpc_channel(self, grpc, aio, target: str, use_tls: bool) -> Any:
        if use_tls:
            creds = grpc.ssl_channel_credentials()
            return aio.secure_channel(target, creds)
        return aio.insecure_channel(target)
    def _create_grpc_stub(self, stub_mod, channel) -> Any:
        stub = None
        for attr in dir(stub_mod):
            if attr.endswith("Stub"):
                stub_cls = getattr(stub_mod, attr)
                stub = stub_cls(channel)
                break
        if stub is None:
            raise ValueError("gNMI stub not found in stub_module")
        return stub
    async def _build_metadata(self, tool_call_template: GnmiCallTemplate, tool_args: Dict[str, Any]) -> List[tuple[str, str]]:
        metadata: List[tuple[str, str]] = []
        if tool_call_template.metadata:
            metadata.extend([(k, v) for k, v in tool_call_template.metadata.items()])
        if tool_call_template.metadata_fields:
            for k in tool_call_template.metadata_fields:
                if k in tool_args:
                    metadata.append((k, str(tool_args[k])))
        if tool_call_template.auth:
            if isinstance(tool_call_template.auth, ApiKeyAuth):
                if tool_call_template.auth.api_key:
                    metadata.append((tool_call_template.auth.var_name or "authorization", tool_call_template.auth.api_key))
            elif isinstance(tool_call_template.auth, BasicAuth):
                import base64
                token = base64.b64encode(f"{tool_call_template.auth.username}:{tool_call_template.auth.password}".encode()).decode()
                metadata.append(("authorization", f"Basic {token}"))
            elif isinstance(tool_call_template.auth, OAuth2Auth):
                token = await self._handle_oauth2(tool_call_template.auth)
                metadata.append(("authorization", f"Bearer {token}"))
        return metadata
    async def register_manual(self, caller, manual_call_template: CallTemplate) -> RegisterManualResult:
        if not isinstance(manual_call_template, GnmiCallTemplate):
            raise ValueError("GnmiCommunicationProtocol can only be used with GnmiCallTemplate")

        target = manual_call_template.target
        if not manual_call_template.use_tls:
            host = target
            if host.startswith("[") and "]" in host:
                host = host[1:host.index("]")]
            else:
                host = host.split(":")[0]
            is_local = host == "localhost"
            try:
                from ipaddress import ip_address
                is_loopback = ip_address(host).is_loopback
            except Exception:
                is_loopback = False
            if not (is_local or is_loopback):
                return RegisterManualResult(
                    success=False,
                    manual_call_template=manual_call_template,
                    manual=UtcpManual(manual_version="0.0.0", tools=[]),
                    errors=["Insecure channel only allowed for localhost or loopback addresses"]
                )

        tools: List[Tool] = []
        ops = ["capabilities", "get", "set", "subscribe"]
        for op in ops:
            tct = GnmiCallTemplate(
                name=manual_call_template.name,
                call_template_type="gnmi",
                auth=manual_call_template.auth,
                target=manual_call_template.target,
                use_tls=manual_call_template.use_tls,
                metadata=manual_call_template.metadata,
                metadata_fields=manual_call_template.metadata_fields,
                operation=op,
                stub_module=manual_call_template.stub_module,
                message_module=manual_call_template.message_module,
            )
            inputs = JsonSchema(type="object", properties={})
            outputs = JsonSchema(type="object", properties={})
            tool = Tool(
                name=op,
                description="",
                inputs=inputs,
                outputs=outputs,
                tags=["gnmi", op],
                tool_call_template=tct,
            )
            tools.append(tool)

        manual = UtcpManual(manual_version="1.0.0", tools=tools)
        return RegisterManualResult(
            success=True,
            manual_call_template=manual_call_template,
            manual=manual,
            errors=[],
        )

    async def deregister_manual(self, caller, manual_call_template: CallTemplate) -> None:
        return None

    async def call_tool(self, caller, tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> Any:
        if not isinstance(tool_call_template, GnmiCallTemplate):
            raise ValueError("GnmiCommunicationProtocol can only be used with GnmiCallTemplate")

        op = tool_call_template.operation
        target = tool_call_template.target

        metadata = await self._build_metadata(tool_call_template, tool_args)

        grpc, aio, json_format, stub_mod, msg_mod = self._load_gnmi_modules(tool_call_template)
        channel = self._create_grpc_channel(grpc, aio, target, tool_call_template.use_tls)

        try:
            stub = self._create_grpc_stub(stub_mod, channel)

            if op == "capabilities":
                req = getattr(msg_mod, "CapabilityRequest")()
                resp = await stub.Capabilities(req, metadata=metadata)
            elif op == "get":
                req = getattr(msg_mod, "GetRequest")()
                paths = tool_args.get("paths", [])
                for p in paths:
                    path_msg = getattr(msg_mod, "Path")()
                    for elem in [e for e in p.strip("/").split("/") if e]:
                        pe = getattr(msg_mod, "PathElem")(name=elem)
                        path_msg.elem.append(pe)
                    req.path.append(path_msg)
                resp = await stub.Get(req, metadata=metadata)
            elif op == "set":
                req = getattr(msg_mod, "SetRequest")()
                updates = tool_args.get("updates", [])
                for upd in updates:
                    path_msg = getattr(msg_mod, "Path")()
                    for elem in [e for e in str(upd.get("path", "")).strip("/").split("/") if e]:
                        pe = getattr(msg_mod, "PathElem")(name=elem)
                        path_msg.elem.append(pe)
                    v = upd.get("value", "")
                    val = None
                    try:
                        import json
                        if isinstance(v, (dict, list)):
                            val = getattr(msg_mod, "TypedValue")(json_ietf_val=json.dumps(v).encode("utf-8"))
                        elif isinstance(v, bool):
                            val = getattr(msg_mod, "TypedValue")(bool_val=v)
                        elif isinstance(v, int) and not isinstance(v, bool):
                            val = getattr(msg_mod, "TypedValue")(int_val=v)
                        elif isinstance(v, float):
                            val = getattr(msg_mod, "TypedValue")(float_val=v)
                        elif isinstance(v, str):
                            val = getattr(msg_mod, "TypedValue")(string_val=v)
                        else:
                            val = getattr(msg_mod, "TypedValue")(json_ietf_val=json.dumps(v).encode("utf-8"))
                    except Exception:
                        val = getattr(msg_mod, "TypedValue")(string_val=str(v))
                    update_msg = getattr(msg_mod, "Update")(path=path_msg, val=val)
                    req.update.append(update_msg)
                resp = await stub.Set(req, metadata=metadata)
            elif op == "subscribe":
                raise ValueError("Unsupported gNMI operation")
            else:
                raise ValueError("Unsupported gNMI operation")

            return json_format.MessageToDict(resp)
        finally:
            await channel.close()

    async def call_tool_streaming(self, caller, tool_name: str, tool_args: Dict[str, Any], tool_call_template: CallTemplate) -> AsyncGenerator[Any, None]:
        if not isinstance(tool_call_template, GnmiCallTemplate):
            raise ValueError("GnmiCommunicationProtocol can only be used with GnmiCallTemplate")
        if tool_call_template.operation != "subscribe":
            result = await self.call_tool(caller, tool_name, tool_args, tool_call_template)
            yield result
            return
        grpc, aio, json_format, stub_mod, msg_mod = self._load_gnmi_modules(tool_call_template)
        target = tool_call_template.target
        channel = self._create_grpc_channel(grpc, aio, target, tool_call_template.use_tls)
        try:
            stub = self._create_grpc_stub(stub_mod, channel)
            metadata = await self._build_metadata(tool_call_template, tool_args)
            req = getattr(msg_mod, "SubscribeRequest")()
            sub_list = getattr(msg_mod, "SubscriptionList")()
            mode_str = str(tool_args.get("mode", "STREAM")).upper()
            try:
                sub_list.mode = getattr(msg_mod, "SubscriptionList").Mode.Value(mode_str)
            except Exception:
                mode_map = {"STREAM": 0, "ONCE": 1, "POLL": 2}
                sub_list.mode = mode_map.get(mode_str, 0)
            paths = tool_args.get("paths", [])
            for p in paths:
                path_msg = getattr(msg_mod, "Path")()
                for elem in [e for e in p.strip("/").split("/") if e]:
                    pe = getattr(msg_mod, "PathElem")(name=elem)
                    path_msg.elem.append(pe)
                sub = getattr(msg_mod, "Subscription")(path=path_msg)
                sub_list.subscription.append(sub)
            req.subscribe.CopyFrom(sub_list)
            call = stub.Subscribe(req, metadata=metadata)
            async for resp in call:
                yield json_format.MessageToDict(resp)
        finally:
            await channel.close()

    async def _handle_oauth2(self, auth_details: OAuth2Auth) -> str:
        import aiohttp
        import time
        key = f"{auth_details.token_url}|{auth_details.client_id}|{auth_details.scope}"
        now = time.time()
        cached = self._oauth_tokens.get(key)
        if cached and cached.get("access_token") and cached.get("expires_at", now + 1) > now:
            return cached["access_token"]
        async with aiohttp.ClientSession() as session:
            try:
                body_data = {
                    "grant_type": "client_credentials",
                    "client_id": auth_details.client_id,
                    "client_secret": auth_details.client_secret,
                    "scope": auth_details.scope,
                }
                async with session.post(auth_details.token_url, data=body_data) as response:
                    response.raise_for_status()
                    token_response = await response.json()
                    access_token = token_response.get("access_token")
                    expires_in = token_response.get("expires_in")
                    ttl = expires_in if isinstance(expires_in, (int, float)) else 300
                    self._oauth_tokens[key] = {"access_token": access_token, "expires_at": now + ttl - 10}
                    return access_token
            except aiohttp.ClientResponseError as e:
                logging.getLogger(__name__).warning(f"OAuth2 client_credentials failed: {e.status}")
                from aiohttp import BasicAuth as AiohttpBasicAuth
                header_auth = AiohttpBasicAuth(auth_details.client_id, auth_details.client_secret)
                header_data = {
                    "grant_type": "client_credentials",
                    "scope": auth_details.scope,
                }
                async with session.post(auth_details.token_url, data=header_data, auth=header_auth) as response:
                    response.raise_for_status()
                    token_response = await response.json()
                    access_token = token_response.get("access_token")
                    expires_in = token_response.get("expires_in")
                    ttl = expires_in if isinstance(expires_in, (int, float)) else 300
                    self._oauth_tokens[key] = {"access_token": access_token, "expires_at": time.time() + ttl - 10}
                    return access_token
            except aiohttp.ClientError as e:
                logging.getLogger(__name__).warning(f"OAuth2 request error: {e}")
                from aiohttp import BasicAuth as AiohttpBasicAuth
                header_auth = AiohttpBasicAuth(auth_details.client_id, auth_details.client_secret)
                header_data = {
                    "grant_type": "client_credentials",
                    "scope": auth_details.scope,
                }
                async with session.post(auth_details.token_url, data=header_data, auth=header_auth) as response:
                    response.raise_for_status()
                    token_response = await response.json()
                    access_token = token_response.get("access_token")
                    expires_in = token_response.get("expires_in")
                    ttl = expires_in if isinstance(expires_in, (int, float)) else 300
                    self._oauth_tokens[key] = {"access_token": access_token, "expires_at": time.time() + ttl - 10}
                    return access_token
            except Exception as e:
                logging.getLogger(__name__).error(f"OAuth2 unexpected error: {e}")
                from aiohttp import BasicAuth as AiohttpBasicAuth
                header_auth = AiohttpBasicAuth(auth_details.client_id, auth_details.client_secret)
                header_data = {
                    "grant_type": "client_credentials",
                    "scope": auth_details.scope,
                }
                async with session.post(auth_details.token_url, data=header_data, auth=header_auth) as response:
                    response.raise_for_status()
                    token_response = await response.json()
                    access_token = token_response.get("access_token")
                    expires_in = token_response.get("expires_in")
                    ttl = expires_in if isinstance(expires_in, (int, float)) else 300
                    self._oauth_tokens[key] = {"access_token": access_token, "expires_at": time.time() + ttl - 10}
                    return access_token

    async def close(self) -> None:
        self._oauth_tokens.clear()