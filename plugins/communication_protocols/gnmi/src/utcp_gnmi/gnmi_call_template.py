from typing import Optional, Dict, List, Literal
from pydantic import Field

from utcp.data.call_template import CallTemplate
from utcp.interfaces.serializer import Serializer
from utcp.exceptions import UtcpSerializerValidationError
import traceback

class GnmiCallTemplate(CallTemplate):
    call_template_type: Literal["gnmi"] = "gnmi"
    target: str
    use_tls: bool = True
    metadata: Optional[Dict[str, str]] = None
    metadata_fields: Optional[List[str]] = None
    operation: Literal["capabilities", "get", "set", "subscribe"] = "get"
    stub_module: str = "gnmi_pb2_grpc"
    message_module: str = "gnmi_pb2"

class GnmiCallTemplateSerializer(Serializer[GnmiCallTemplate]):
    def to_dict(self, obj: GnmiCallTemplate) -> dict:
        return obj.model_dump()

    def validate_dict(self, obj: dict) -> GnmiCallTemplate:
        try:
            return GnmiCallTemplate.model_validate(obj)
        except Exception as e:
            raise UtcpSerializerValidationError("Invalid GnmiCallTemplate: " + traceback.format_exc()) from e