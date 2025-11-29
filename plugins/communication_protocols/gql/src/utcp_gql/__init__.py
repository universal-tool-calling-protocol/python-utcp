from utcp.plugins.discovery import register_communication_protocol, register_call_template

from .gql_communication_protocol import GraphQLCommunicationProtocol
from .gql_call_template import GraphQLCallTemplate, GraphQLCallTemplateSerializer


def register():
    register_communication_protocol("graphql", GraphQLCommunicationProtocol())
    register_call_template("graphql", GraphQLCallTemplateSerializer())