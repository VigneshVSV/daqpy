import typing 
import msgspec
from uuid import uuid4
from dataclasses import dataclass

import zmq
import zmq.asyncio

from ...constants import JSON, byte_types
from ...serializers import Serializers
from ....param.parameters import Integer

# message types
# both directions
HANDSHAKE = 'HANDSHAKE' # 1 - find out if the server is alive/connect to it
# client to server 
OPERATION = 'OPERATION' # 2 - i.e. message type is a request to perform an operation on the interaction affordance
EXIT = 'EXIT' # 3 - exit the server
# server to client
REPLY = 'REPLY' # 4 - response for operation
TIMEOUT = 'TIMEOUT' # 5 - timeout message, operation could not be completed
ERROR = 'EXCEPTION' # 6 - exception occurred while executing operation
INVALID_MESSAGE = 'INVALID_MESSAGE' # 7 - invalid message
SERVER_DISCONNECTED = 'EVENT_DISCONNECTED' # 8 - socket died - zmq's builtin event EVENT_DISCONNECTED
# peer to peer
INTERRUPT = 'INTERRUPT' # 9 - interrupt a socket while polling 

# not used now
EVENT       = 'EVENT'
EVENT_SUBSCRIPTION = 'EVENT_SUBSCRIPTION'
SUCCESS     = 'SUCCESS'


EMPTY_BYTE = b''
EMPTY_DICT = {}
"""
Message indices 

client's message to server: |br|
[address, message type, messsage id, server execution context, 
[   0   ,      1      ,      2     ,          3              ,  
    
thing instance name,  object, operation, payload, thing execution context] 
      4            ,    5   ,      6   ,     7    ,       8              ] 

    
[address, message_type, message id, data, pre encoded data]|br|
[   0   ,      1      ,      2    ,  3  ,       4         ]|br|
"""
# CM = Client Message
INDEX_ADDRESS = 0
INDEX_HEADER= 1
INDEX_BODY = 2
INDEX_PRESERIALIZED_BODY = 3



@dataclass
class SerializableData:
    """
    A container for data that can be serialized. 
    The content type decides the serializer to be used. 
    """
    value: typing.Any
    content_type: str = 'application/json'

    def serialize(self):
        """serialize the value"""
        if self.content_type == 'json' or self.content_type == 'application/json':
            return Serializers.json.dumps(self.value)
        elif self.content_type == 'pickle':
            return Serializers.pickle.dumps(self.value)
        elif self.content_type == 'x-msgpack':
            return Serializers.msgpack.dumps(self.value)
        elif self.content_type == 'text/plain':
            if not isinstance(self.value, str):
                value = str(self.value)
            else:
                value = self.value
            return value.encode('utf-8')
        raise ValueError(f"content type {self.content_type} not supported for serialization")
    
    def deserialize(self):
        """deserialize the value"""
        if self.content_type == 'json' or self.content_type == 'application/json':
            return Serializers.json.loads(self.value)
        elif self.content_type == 'pickle':
            return Serializers.pickle.loads(self.value)
        elif self.content_type == 'x-msgpack':
            return Serializers.msgpack.loads(self.value)
        elif self.content_type == 'text/plain':
            return self.value.decode('utf-8')
        raise ValueError(f"content type {self.content_type} not supported for deserialization")
    
  

@dataclass
class PreserializedData:
    """
    A container for data that is already serialized. 
    The content type may indicate the serializer used.
    """
    value: bytes
    content_type: str


class ServerExecutionContext(msgspec.Struct):
    invokationTimeout: float
    executionTimeout: float
    oneway: bool

class ThingExecutionContext(msgspec.Struct):
    fetchExecutionLogs: bool

default_server_execution_context = ServerExecutionContext(
    invokationTimeout=5,
    executionTimeout=5,
    oneway=False
)

default_thing_execution_context = ThingExecutionContext(
    fetchExecutionLogs=False
)


class RequestHeader(msgspec.Struct):
    """
    Header of a request message
    For detailed schema, visit [here](https://hololinked.readthedocs.io/en/latest/protocols/zmq/request-message-header.json).
    """
    messageType: str
    messageID: str
    serverExecutionContext: ServerExecutionContext = msgspec.field(default_factory=lambda: default_server_execution_context)
    thingExecutionContext: ThingExecutionContext = msgspec.field(default_factory=lambda: default_thing_execution_context)
    thingID: typing.Optional[str] = ''
    object: typing.Optional[str] = ''
    operation: typing.Optional[str] = ''
    payloadContentType: typing.Optional[str] = 'application/json'
    preencodedPayloadContentType: typing.Optional[str] = 'text/plain'

    def __getitem__(self, key: str) -> typing.Any:
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(f"key {key} not found in {self.__class__.__name__}") from None
        
    def json(self):
        return {f: getattr(self, f) for f in self.__struct_fields__}
        

class ResponseHeader(msgspec.Struct):
    """
    Header of a response message
    For detailed schema, visit [here](https://hololinked.readthedocs.io/en/latest/protocols/zmq/response-message-header.json).
    """
    messageType: str
    messageID: str
    payloadContentType: typing.Optional[str] = 'application/json'
    preencodedPayloadContentType: typing.Optional[str] = ''

    def __getitem__(self, key: str) -> typing.Any:
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(f"key {key} not found in {self.__class__.__name__}") from None
        
    def json(self):
        return {f: getattr(self, f) for f in self.__struct_fields__}
        
        

class RequestMessage:
    """
    A single unit of message from a ZMQ client to server. The message may be parsed and deserialized into header and body.

    Message indices:

    | Index | 0       | 1      |   2     |          3            |
    |-------|---------|--------|---------|-----------------------|
    | Desc  | address | header | payload | preserialized payload |

    The header is a JSON with the following (shortened) schema:

    ```json
   
    {
        "messageType": "string",
        "messageID": "string",
        "senderID": "string",
        "serverExecutionContext": {
            "invokationTimeout": "number",
            "executionTimeout": "number",
            "oneway": "boolean"
        },
        "thingID": "string",
        "object": "string",
        "operation": "string",
        "payloadContentType": "string",
        "preencodedPayloadContentType": "string",
        "thingExecutionContext": {
            "fetchExecutionLogs": "boolean"
        }
    }
    ```

    For detailed schema, visit [here](https://hololinked.readthedocs.io/en/latest/protocols/zmq/message.json).
    """
    length = Integer(default=4, readonly=True, 
                    doc="length of the message") # type: int

    def __init__(self, msg : typing.List[bytes]) -> None:
        self._bytes = msg  
        self._header = None # deserialized header
        self._body = None  # deserialized body
        self._sender_id = None

    @property
    def byte_array(self) -> typing.List[bytes]:
        """returns the message in bytes"""
        return self._bytes
    
    @property
    def header(self) -> typing.Tuple[bytes, bytes, bytes, bytes, bytes, typing.Dict[str, typing.Any]]:
        """
        returns the header of the message, namely index 1 from the following:

        | Index | 0       | 1       | 2       | 3                      |
        |-------|---------|---------|---------|------------------------|
        | Desc  | address | header  | payload | preserialized payload  |

        deserizalized to a dictionary. 
        """
        if self._header is None:
            self.parse_header()
        return self._header 
    
    @property
    def body(self) -> typing.Tuple[bytes, bytes, bytes, typing.Any, typing.Dict[str, typing.Any]]:
        """
        payload of the message
        """
        if self._body is None:
            self.parse_body()
        return self._body
    
    @property
    def id(self) -> str:
        """ID of the message"""
        return self.header['messageID']
    
    @property
    def receiver_id(self) -> str:
        """ID of the sender"""
        if self._sender_id is not None:
            raise ValueError("receiver id unknown")
        return self._bytes[INDEX_ADDRESS].decode('utf-8')
    
    @property
    def sender_id(self) -> str:
        """ID of the receiver"""
        if self._sender_id is None:
            raise ValueError("sender id unknown")
        return self._sender_id
    
    @property
    def thing_id(self) -> str:
        """ID of the thing on which the operation is to be performed"""
        return self.header['thingID']
    
    @property
    def type(self) -> str:
        """type of the message"""
        return self.header['messageType']
    
    
    def parse_header(self) -> None:
        """
        extract the header and deserialize the server execution context
        """
        if isinstance(self._bytes[INDEX_HEADER], RequestHeader):
            self._header = self._bytes[INDEX_HEADER]
        elif isinstance(self._bytes[INDEX_HEADER], byte_types):
            self._header = RequestHeader(**Serializers.json.loads(self._bytes[INDEX_HEADER]))
        else:
            raise ValueError(f"header must be of type RequestHeader or bytes, not {type(self._bytes[INDEX_HEADER])}")

    def parse_body(self) -> None:
        """
        extract the body and deserialize payload and thing execution context
        """
        self._body = [
            SerializableData(self._bytes[INDEX_BODY], self.header['payloadContentType']).deserialize(),
            PreserializedData(self._bytes[INDEX_PRESERIALIZED_BODY], self.header['preencodedPayloadContentType'])
        ]


    @classmethod
    def craft_from_arguments(cls, 
                            server_id: str, 
                            thing_id: str, 
                            objekt: str, 
                            operation: str, 
                            payload: SerializableData = SerializableData(None, 'application/json'),
                            preserialized_payload: PreserializedData = PreserializedData(EMPTY_BYTE, 'text/plain'),
                            server_execution_context: typing.Dict[str, typing.Any] = default_server_execution_context, 
                            thing_execution_context: typing.Dict[str, typing.Any] = default_thing_execution_context
                        ) -> "RequestMessage": 
        """
        create a request message from the given arguments

        Parameters
        ----------
        thing_id: bytes
            id of the thing to which the operation is to be performed
        objekt: str
            object of the thing on which the operation is to be performed, i.e. a property, action or event
        operation: str
            operation to be performed
        payload: SerializableData
            payload for the operation
        server_execution_context: Dict[str, Any]
            server-level execution context while performing the operation
        thing_execution_context: Dict[str, Any]
            thing-level execution context while performing the operation

        Returns
        -------
        message: RequestMessage
            the crafted message
        """
        message = RequestMessage([])
        message._header = RequestHeader(
                                messageID=uuid4(),
                                messageType=OPERATION, 
                                # i.e. the message type is 'OPERATION', not 'HANDSHAKE', 'REPLY', 'TIMEOUT' etc.
                                serverExecutionContext=server_execution_context,
                                thingID=thing_id,
                                object=objekt,
                                operation=operation,
                                payloadContentType=payload.content_type,
                                preencodedPayloadContentType=preserialized_payload.content_type,
                                thingExecutionContext=thing_execution_context
                            )
        message._body = [payload, preserialized_payload]
        message._bytes = [
            bytes(server_id, encoding='utf-8'),
            Serializers.json.dumps(message._header.json()),
            payload.serialize(),
            preserialized_payload.value
        ]
        return message


    @classmethod
    def craft_with_message_type(cls, server_id: bytes, message_type: bytes = HANDSHAKE) -> "RequestMessage":
        """
        create a plain message with a certain type, for example a handshake message.

        Parameters
        ----------
        server_id: bytes
            id of the server
        message_type: bytes
            message type to be sent

        Returns
        -------
        message: RequestMessage
            the crafted message
        """

        message = RequestMessage([])
        message._header = RequestHeader(
            messageID=uuid4(),
            messageType=message_type,
            serverExecutionContext=default_server_execution_context
        )
        payload = SerializableData(None, 'application/json')
        preserialized_payload = PreserializedData(EMPTY_BYTE, 'text/plain')
        message._body = [
            payload,
            preserialized_payload
        ]
        message._bytes = [
            bytes(server_id, encoding='utf-8'),
            Serializers.json.dumps(message._header.json()),
            payload.serialize(),
            preserialized_payload.value
        ]
        return message
    

    @classmethod
    def craft_from_self(self, value: typing.List[bytes]) -> "RequestMessage":
        """
        create a message from the message itself

        Parameters
        ----------
        value: List[bytes]
            the message

        Returns
        -------
        message: RequestMessage
            the crafted message
        """
        message = RequestMessage(value)
        message._sender_id = value[INDEX_ADDRESS].decode('utf-8')
        return message


class ResponseMessage:
    """
    A single unit of message from a ZMQ server to client. 
    The message may be parsed and deserialized into header and body.

    Message indices:

    | Index | 0       |   2    | 3    |     4            |
    |-------|---------|--------|------|------------------|
    | Desc  | address | header | data | pre encoded data |

    
    The header is a JSON with the following (shortened) schema:
    
    ```json
    {
        "messageType": "string",
        "messageID": "string",
        "payloadContentType": "string",
        "preencodedPayloadContentType": "string"
    }
    ```
    
    For detailed schema, visit [here](https://hololinked.readthedocs.io/en/latest/protocols/zmq/response-message-header.json).
    """

    length = Integer(default=4, readonly=True, 
                    doc="length of the message") # type: int

    def __init__(self, msg: typing.List[bytes]):
        self._bytes = msg
        self._header = None
        self._body = None
        self._sender_id = None

    @property
    def byte_array(self) -> typing.List[bytes]:
        """returns the message in bytes"""
        return self._bytes

    @property
    def id(self) -> str:
        """ID of the message"""
        return self.header['messageID']
        
    @property
    def type(self) -> str:
        """type of the message"""
        return self.header['messageType']

    @property
    def receiver_id(self) -> str:
        """ID of the sender"""
        if self._sender_id is not None:
            raise ValueError("receiver id unknown")
        return self._bytes[INDEX_ADDRESS].decode('utf-8')

    @property
    def sender_id(self) -> str:
        """ID of the receiver"""
        if self._sender_id is None:
            raise ValueError("sender id unknown")
        return self._sender_id

    @property
    def header(self) -> JSON:
        """Returns the header of the message"""
        if self._header is None:
            self.parse_header()
        return self._header

    @property
    def body(self) -> typing.Tuple[bytes, bytes, bytes, bytes, bytes]:
        """Returns the body of the message"""
        if self._body is None:
            self.parse_body()
        return self._body
    
    @property
    def payload(self) -> typing.Any:
        """Returns the payload of the message"""
        return self.body[0]
    
    @property
    def preserialized_payload(self) -> bytes:
        """Returns the pre-encoded payload of the message"""
        return self.body[1]
    
    def parse_header(self) -> None:
        """parse the header"""
        self._header = Serializers.json.loads(self._bytes[INDEX_HEADER])

    def parse_body(self) -> None:
        """parse the body"""
        self._body = [
            SerializableData(self._bytes[INDEX_BODY], self.header['payloadContentType']).deserialize(),
            PreserializedData(self._bytes[INDEX_PRESERIALIZED_BODY], self.header['preencodedPayloadContentType'])
        ]

    @classmethod
    def craft_from_arguments(cls, 
                            client_id: str, 
                            message_type: str, 
                            message_id: bytes = b'', 
                            payload: SerializableData = SerializableData(None, 'application/json'), 
                            preserialized_payload: PreserializedData = PreserializedData(EMPTY_BYTE, 'text/plain')
                        ) -> "ResponseMessage":
        """
        Crafts an arbitrary response to the client using the method's arguments. 

        Parameters
        ----------
        address: bytes 
            the ROUTER address of the client
        message_type: bytes 
            type of the message, possible values are 'REPLY', 'HANDSHAKE' and 'TIMEOUT' 
        message_id: bytes
            message id of the original client message for which the response is being crafted
        data: Any
            serializable data
        preserialized_payload: bytes
            pre-encoded data, generally used for large or custom data that is already serialized
        
        Returns
        -------
        message: List[bytes]
            the crafted response with information in the correct positions within the list
        """
        message = ResponseMessage([])
        message._header = ResponseHeader(
            messageType=message_type,
            messageID=message_id,
            payloadContentType=payload.content_type,
            preencodedPayloadContentType=preserialized_payload.content_type
        )
        message._body = [payload, preserialized_payload]
        message._bytes = [
            bytes(client_id, encoding='utf-8'),
            Serializers.json.dumps(message._header.json()),
            payload.serialize(),
            preserialized_payload.value
        ]
        return message
           

    @classmethod
    def craft_reply_from_request(self, 
                        request_message: RequestMessage, 
                        payload: SerializableData = SerializableData(None, 'application/json'),
                        preserialized_payload: PreserializedData = PreserializedData(EMPTY_BYTE, 'text/plain')
                    ) -> "ResponseMessage":
        """
        Craft a response with certain data extracted from an originating client message, 
        like the client's address, message id etc. 

        Parameters
        ----------
        original_client_message: List[bytes]
            The message originated by the clieht for which the response is being crafted
        data: Any
            serializable data 
        preserialized_payload: bytes
            pre-encoded data, generally used for large or custom data that is already serialized

        Returns
        -------
        message: List[bytes]
            the crafted response with information in the correct positions within the list
        """
        message = ResponseMessage([])
        message._header = ResponseHeader(
            messageType=REPLY,
            messageID=request_message.id,
            payloadContentType=payload.content_type,
            preencodedPayloadContentType=preserialized_payload.content_type
        )
        message._body = [payload, preserialized_payload]
        message._bytes = [
            bytes(request_message.sender_id, encoding='utf-8'),    
            Serializers.json.dumps(message._header.json()),
            payload.serialize(),
            preserialized_payload.value
        ]
        return message
    

    @classmethod
    def craft_from_self(self, byte_array: typing.List[bytes]) -> "ResponseMessage":
        """
        create a message from the message itself

        Parameters
        ----------
        value: List[bytes]
            the message

        Returns
        -------
        message: ResponseMessage
            the crafted message
        """
        message = ResponseMessage(byte_array)
        message._sender_id = byte_array[INDEX_ADDRESS].decode('utf-8')
        return message

    
class EventMessage(ResponseMessage):
    pass




def parse_server_message(self, message : ResponseMessage, raise_client_side_exception : bool = False, 
                            deserialize_response : bool = True) -> typing.Any:
    """
    server's message to client: 

    ::
        [address, bytes(), server_type, message_type, message id, data, pre encoded data]|br|
        [   0   ,   1    ,    2       ,      3      ,      4    ,  5  ,       6         ]|br|

    Parameters
    ----------
    message: List[bytes]
        message sent be server
    raise_client_side_exception: bool
        raises exception from server on client
    deserialize_response: bool
        deserializes the data field of the message
    
    Raises
    ------
    NotImplementedError:
        if message type is not response, handshake or invalid
    """
    if len(message) == 2: # socket monitor message, not our message
        try: 
            if ZMQ_EVENT_MAP[parse_monitor_message(message)['event']] == SERVER_DISCONNECTED:
                raise ConnectionAbortedError(f"server disconnected for {self.id}")
            return None # None should simply continue the message receive logic
        except RuntimeError as ex:
            raise RuntimeError(f'message received from monitor socket cannot be deserialized for {self.id}') from None
    message_type = message[SM_INDEX_MESSAGE_TYPE]
    if message_type == REPLY:
        if deserialize_response:
            if self.client_type == HTTP_SERVER:
                message[SM_INDEX_DATA] = self.http_serializer.loads(message[SM_INDEX_DATA]) # type: ignore
            elif self.client_type == PROXY:
                message[SM_INDEX_DATA] = self.zmq_serializer.loads(message[SM_INDEX_DATA]) # type: ignore
        return message 
    elif message_type == HANDSHAKE:
        self.logger.debug("""handshake messages arriving out of order are silently dropped as receiving this message 
            means handshake was successful before. Received hanshake from {}""".format(message[0]))
        return message
    elif message_type == logging.ERROR or message_type == INVALID_MESSAGE:
        if self.client_type == HTTP_SERVER:
            message[SM_INDEX_DATA] = self.http_serializer.loads(message[SM_INDEX_DATA]) # type: ignore
        elif self.client_type == PROXY:
            message[SM_INDEX_DATA] = self.zmq_serializer.loads(message[SM_INDEX_DATA]) # type: ignore
        if not raise_client_side_exception:
            return message
        if message[SM_INDEX_DATA].get('exception', None) is not None:
            self.raise_local_exception(message[SM_INDEX_DATA]['exception'])
        else:
            raise NotImplementedError("message type {} received. No exception field found, exception field mandatory.".format(
                message_type))
    elif message_type == TIMEOUT:
        if self.client_type == HTTP_SERVER:
            timeout_type = self.http_serializer.loads(message[SM_INDEX_DATA]) # type: ignore
        elif self.client_type == PROXY:
            timeout_type = self.zmq_serializer.loads(message[SM_INDEX_DATA]) # type: ignore
        exception =  TimeoutError(f"{timeout_type} timeout occurred")
        if raise_client_side_exception:
            raise exception from None 
        message[SM_INDEX_DATA] = format_exception_as_json(exception)
        return message
    elif response_message.type == HANDSHAKE:
                pass 
    else:
        raise NotImplementedError("Unknown message type {} received. This message cannot be dealt.".format(message_type))
    

