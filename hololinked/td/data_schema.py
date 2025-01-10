from abc import abstractmethod
import typing
from dataclasses import dataclass, field

from ..constants import JSON, ResourceTypes
from .dataklasses import ActionInfoValidator
from .events import Event
from .properties import *
from .property import Property
from .thing import Thing
from .state_machine import StateMachine



@dataclass
class DataSchema(Schema):
    """
    implementes Dataschema attributes.
    https://www.w3.org/TR/wot-thing-description11/#sec-data-schema-vocabulary-definition
    """
    title : str 
    titles : typing.Optional[typing.Dict[str, str]]
    description : str
    descriptions : typing.Optional[typing.Dict[str, str]] 
    const : bool
    default : typing.Optional[typing.Any] 
    readOnly : bool
    writeOnly : bool # write only are to be considered actions with no return value
    format : typing.Optional[str]
    unit : typing.Optional[str]
    type : str
    oneOf : typing.Optional[typing.List[JSON]]
    enum : typing.Optional[typing.List[typing.Any]]

    def __init__(self):
        super().__init__()

    def build(self, property : Property, owner : Thing, authority : str) -> None:
        """generates the schema"""
        self.title = property.label or property.name 
        if property.constant:
            self.const = property.constant 
        if property.readonly:
            self.readOnly = property.readonly
        if property.fget is None:
            self.default = property.default
        if property.doc:
            self.description = Schema.format_doc(property.doc)
        if property.metadata and property.metadata.get("unit", None) is not None:
            self.unit = property.metadata["unit"]
        if property.allow_None:
            if not hasattr(self, 'oneOf'):
                self.oneOf = []
            if hasattr(self, 'type'):
                self.oneOf.append(dict(type=self.type))
                del self.type
            if not any(types["type"] == None for types in self.oneOf):
                self.oneOf.append(dict(type="null"))



@dataclass
class BooleanSchema(PropertyAffordance):
    """
    boolean schema - https://www.w3.org/TR/wot-thing-description11/#booleanschema
    used by Boolean descriptor    
    """
    def __init__(self):
        super().__init__()

    def build(self, property: Property, owner: Thing, authority: str) -> None:
        """generates the schema"""
        self.type = 'boolean'
        PropertyAffordance.build(self, property, owner, authority)


@dataclass
class StringSchema(PropertyAffordance):
    """
    string schema - https://www.w3.org/TR/wot-thing-description11/#stringschema
    used by String, Filename, Foldername, Path descriptors
    """
    pattern : typing.Optional[str] 
    
    def __init__(self):
        super().__init__()
        
    def build(self, property: Property, owner: Thing, authority: str) -> None:
        """generates the schema"""
        self.type = 'string' 
        PropertyAffordance.build(self, property, owner, authority)
        if isinstance(property, String): 
            if property.regex is not None:
                self.pattern = property.regex


@dataclass
class NumberSchema(PropertyAffordance):
    """
    number schema - https://www.w3.org/TR/wot-thing-description11/#numberschema
    used by String, Filename, Foldername, Path descriptors
    """
    minimum : typing.Optional[typing.Union[int, float]]
    maximum : typing.Optional[typing.Union[int, float]]
    exclusiveMinimum : typing.Optional[bool] 
    exclusiveMaximum : typing.Optional[bool] 
    step : typing.Optional[typing.Union[int, float]]

    def __init__(self):
        super().__init__()
        
    def build(self, property: Property, owner: Thing, authority: str) -> None:
        """generates the schema"""
        if isinstance(property, Integer):
            self.type = 'integer'
        elif isinstance(property, Number): # dont change order - one is subclass of other
            self.type = 'number' 
        PropertyAffordance.build(self, property, owner, authority)
        if property.bounds is not None:      
            if isinstance(property.bounds[0], (int, float)): # i.e. value is not None which is allowed by param
                if not property.inclusive_bounds[0]:
                    self.exclusiveMinimum = property.bounds[0]
                else:
                    self.minimum = property.bounds[0]
            if isinstance(property.bounds[1], (int, float)):
                if not property.inclusive_bounds[1]:
                    self.exclusiveMaximum = property.bounds[1]
                else:
                    self.maximum = property.bounds[1]
        if property.step:
            self.multipleOf = property.step


@dataclass
class ArraySchema(PropertyAffordance):
    """
    array schema - https://www.w3.org/TR/wot-thing-description11/#arrayschema
    Used by List, Tuple, TypedList and TupleSelector
    """

    items : typing.Optional[JSON]
    minItems : typing.Optional[int]
    maxItems : typing.Optional[int]

    def __init__(self):
        super().__init__()
        
    def build(self, property: Property, owner: Thing, authority: str) -> None:
        """generates the schema"""
        self.type = 'array'
        PropertyAffordance.build(self, property, owner, authority)
        self.items = []
        if isinstance(property, (List, Tuple, TypedList)) and property.item_type is not None:
            if property.bounds:
                if property.bounds[0]:
                    self.minItems = property.bounds[0]
                if property.bounds[1]:
                    self.maxItems = property.bounds[1]
            if isinstance(property.item_type, (list, tuple)):
                for typ in property.item_type:
                    self.items.append(dict(type=JSONSchema.get_type(typ)))
            elif property.item_type is not None: 
                self.items.append(dict(type=JSONSchema.get_type(property.item_type)))
        elif isinstance(property, TupleSelector):
            objects = list(property.objects)
            for obj in objects:
                if any(types["type"] == JSONSchema._replacements.get(type(obj), None) for types in self.items):
                    continue 
                self.items.append(dict(type=JSONSchema.get_type(type(obj))))
        if len(self.items) == 0:
            del self.items
        elif len(self.items) > 1:
            self.items = dict(oneOf=self.items)
            

@dataclass
class ObjectSchema(PropertyAffordance):
    """
    object schema - https://www.w3.org/TR/wot-thing-description11/#objectschema
    Used by TypedDict
    """
    properties : typing.Optional[JSON]
    required : typing.Optional[typing.List[str]]

    def __init__(self):
        super().__init__()
        
    def build(self, property: Property, owner: Thing, authority: str) -> None:
        """generates the schema"""
        PropertyAffordance.build(self, property, owner, authority)
        properties = None 
        required = None 
        if hasattr(property, 'json_schema'):
            # Code will not reach here for now as have not implemented schema for typed dictionaries. 
            properties = property.json_schema["properties"]
            if property.json_schema.get("required", NotImplemented) is not NotImplemented:
                required = property.json_schema["required"] 
        if not property.allow_None:
            self.type = 'object'
            if properties:
                self.properties = properties
            if required:
                self.required = required
        else:
            schema = dict(type='object')
            if properties:
                schema['properties'] = properties
            if required:
                schema['required'] = required
            self.oneOf.append(schema)


@dataclass
class OneOfSchema(PropertyAffordance):
    """
    custom schema to deal with ClassSelector to fill oneOf field correctly
    https://www.w3.org/TR/wot-thing-description11/#dataschema
    """
    properties : typing.Optional[JSON]
    required : typing.Optional[typing.List[str]]
    items : typing.Optional[JSON]
    minItems : typing.Optional[int]
    maxItems : typing.Optional[int]
    # ClassSelector can technically have a JSON serializable as a class_

    def __init__(self):
        super().__init__()

    def build(self, property: Property, owner: Thing, authority: str) -> None:
        """generates the schema"""
        self.oneOf = []
        if isinstance(property, ClassSelector):
            if not property.isinstance:
                raise NotImplementedError("WoT TD for ClassSelector with isinstance set to True is not supported yet. "  +
                                          "Consider user this property in a different way.")
            if isinstance(property.class_, (list, tuple)):
                objects = list(property.class_)
            else:
                objects = [property.class_]
        elif isinstance(property, Selector):
            objects = list(property.objects)
        else:
            raise TypeError(f"EnumSchema and OneOfSchema supported only for Selector and ClassSelector. Given Type - {property}")
        for obj in objects:
            if any(types["type"] == JSONSchema._replacements.get(type(obj), None) for types in self.oneOf):
                continue 
            if isinstance(property, ClassSelector):
                if not JSONSchema.is_allowed_type(obj):
                    raise TypeError(f"Object for wot-td has invalid type for JSON conversion. Given type - {obj}. " +
                                "Use JSONSchema.register_replacements on hololinked.wot.td.JSONSchema object to recognise the type.")
                subschema = dict(type=JSONSchema.get_type(obj))
                if JSONSchema.is_supported(obj):
                    subschema.update(JSONSchema.get(obj))
                self.oneOf.append(subschema)
            elif isinstance(property, Selector):
                if JSONSchema.get_type(type(obj)) == "null":
                    continue
                self.oneOf.append(dict(type=JSONSchema.get_type(type(obj))))
        PropertyAffordance.build(self, property, owner, authority)
        self.cleanup()

    def cleanup(self):
        if len(self.oneOf) == 1:
            oneOf = self.oneOf[0]
            self.type = oneOf["type"]
            if oneOf["type"] == 'object':
                if oneOf.get("properties", NotImplemented) is not NotImplemented:
                    self.properties = oneOf["properties"]
                if oneOf.get("required", NotImplemented) is not NotImplemented:
                    self.required = oneOf["required"]
            elif oneOf["type"] == 'array':
                if oneOf.get("items", NotImplemented) is not NotImplemented:
                    self.items = oneOf["items"]
                if oneOf.get("maxItems", NotImplemented) is not NotImplemented:
                    self.minItems = oneOf["minItems"]
                if oneOf.get("maxItems", NotImplemented) is not NotImplemented:
                    self.maxItems = oneOf["maxItems"]
            del self.oneOf


@dataclass
class EnumSchema(OneOfSchema):
    """
    custom schema to fill enum field of property affordance correctly
    https://www.w3.org/TR/wot-thing-description11/#dataschema
    """ 
    def __init__(self):
        super().__init__()
        
    def build(self, property: Property, owner: Thing, authority: str) -> None:
        """generates the schema"""
        assert isinstance(property, Selector), f"EnumSchema compatible property is only Selector, not {property.__class__}"
        self.enum = list(property.objects)
        OneOfSchema.build(self, property, owner, authority)


@dataclass
class Link(Schema):
    href : str
    anchor : typing.Optional[str]  
    type : typing.Optional[str] = field(default='application/json')
    # rel : typing.Optional[str] = field(default='next')

    def __init__(self):
        super().__init__()
    
    def build(self, resource : Thing, owner : Thing, authority : str) -> None:
        self.href = f"{authority}{resource._full_URL_path_prefix}/resources/wot-td"
        self.anchor = f"{authority}{owner._full_URL_path_prefix}"



@dataclass
class ExpectedResponse(Schema):
    """
    Form property. 
    schema - https://www.w3.org/TR/wot-thing-description11/#expectedresponse
    """
    contentType : str

    def __init__(self):
        super().__init__()


@dataclass
class AdditionalExpectedResponse(Schema):
    """
    Form field for additional responses which are different from the usual response.
    schema - https://www.w3.org/TR/wot-thing-description11/#additionalexpectedresponse
    """
    success : bool = field(default=False)
    contentType : str = field(default='application/json')
    schema : typing.Optional[JSON] = field(default='exception')

    def __init__(self):
        super().__init__()

   
@dataclass
class Form(Schema):
    """
    Form hypermedia.
    schema - https://www.w3.org/TR/wot-thing-description11/#form
    """
    href : str 
    op : str 
    htv_methodName : str 
    contentType : typing.Optional[str]
    additionalResponses : typing.Optional[typing.List[AdditionalExpectedResponse]]
    contentEncoding : typing.Optional[str]
    security : typing.Optional[str]
    scopes : typing.Optional[str]
    response : typing.Optional[ExpectedResponse]
    subprotocol : typing.Optional[str]
    
    def __init__(self):
        super().__init__()

    
@dataclass
class VersionInfo:
    """
    create version info.
    schema - https://www.w3.org/TR/wot-thing-description11/#versioninfo
    """
    instance : str 
    model : str


@dataclass
class SecurityScheme(Schema):
    """
    create security scheme. 
    schema - https://www.w3.org/TR/wot-thing-description11/#sec-security-vocabulary-definition
    """
    scheme: str 
    description : str 
    descriptions : typing.Optional[typing.Dict[str, str]]
    proxy : typing.Optional[str]

    def __init__(self):
        super().__init__()

    def build(self, name : str, instance):
        self.scheme = 'nosec'
        self.description = 'currently no security scheme supported - use cookie auth directly on hololinked.server.HTTPServer object'
        return { name : self.asdict() }



@dataclass
class ThingDescription(Schema):
    """
    generate Thing Description schema of W3 Web of Things standard. 
    Refer standard - https://www.w3.org/TR/wot-thing-description11
    Refer schema - https://www.w3.org/TR/wot-thing-description11/#thing
    """
    context : typing.Union[typing.List[str], str, typing.Dict[str, str]] 
    type : typing.Optional[typing.Union[str, typing.List[str]]]
    id : str 
    title : str 
    description : str 
    version : typing.Optional[VersionInfo]
    created : typing.Optional[str] 
    modified : typing.Optional[str]
    support : typing.Optional[str] 
    base : typing.Optional[str] 
    properties : typing.List[PropertyAffordance]
    actions : typing.List[ActionAffordance]
    events : typing.List[EventAffordance]
    links : typing.Optional[typing.List[Link]] 
    forms : typing.Optional[typing.List[Form]]
    security : typing.Union[str, typing.List[str]]
    securityDefinitions : SecurityScheme
    schemaDefinitions : typing.Optional[typing.List[DataSchema]]
    
    skip_properties = ['expose', 'httpserver_resources', 'zmq_resources', 'gui_resources',
                    'events', 'thing_description', 'GUI', 'object_info' ]

    skip_actions = ['_set_properties', '_get_properties', '_add_property', '_get_properties_in_db', 
                    'get_postman_collection', 'get_thing_description', 'get_our_temp_thing_description']

    # not the best code and logic, but works for now

    def __init__(self, instance : Thing, authority : typing.Optional[str] = None, 
                    allow_loose_schema : typing.Optional[bool] = False, ignore_errors : bool = False) -> None:
        super().__init__()
        self.instance = instance
        self.authority = authority
        self.allow_loose_schema = allow_loose_schema
        self.ignore_errors = ignore_errors

    def produce(self) -> JSON: 
        self.context = "https://www.w3.org/2022/wot/td/v1.1"
        self.id = f"{self.authority}/{self.instance.id}"
        self.title = self.instance.__class__.__name__ 
        self.description = Schema.format_doc(self.instance.__doc__) if self.instance.__doc__ else "no class doc provided" 
        self.properties = dict()
        self.actions = dict()
        self.events = dict()
        self.forms = NotImplemented
        self.links = NotImplemented
        
        # self.schemaDefinitions = dict(exception=JSONSchema.get_type(Exception))

        self.add_interaction_affordances()
        self.add_links()
        self.add_top_level_forms()
        self.add_security_definitions()
       
        return self
    

    def add_interaction_affordances(self):
        # properties 
        for prop in self.instance.properties.descriptors.values():
            if not isinstance(prop, Property) or not prop.remote or prop.name in self.skip_properties: 
                continue
            if prop.name == 'state' and (not hasattr(self.instance, 'state_machine') or 
                                not isinstance(self.instance.state_machine, StateMachine)):
                continue
            try:
                if (resource.isproperty and resource.obj_name not in self.properties and 
                    resource.obj_name not in self.skip_properties and hasattr(resource.obj, "_remote_info") and 
                    resource.obj._remote_info is not None): 
                    if (resource.obj_name == 'state' and (not hasattr(self.instance, 'state_machine') or 
                                not isinstance(self.instance.state_machine, StateMachine))):
                        continue
                    if resource.obj_name not in self.instance.properties:
                        continue 
                    self.properties[resource.obj_name] = PropertyAffordance.generate_schema(resource.obj, 
                                                                            self.instance, self.authority) 
                
                elif (resource.isaction and resource.obj_name not in self.actions and 
                    resource.obj_name not in self.skip_actions and hasattr(resource.obj, '_remote_info')):

                    if resource.bound_obj != self.instance or (resource.obj_name == 'exit' and 
                            self.instance._owner is not None) or (not hasattr(resource.bound_obj, 'db_engine') and
                            resource.obj_name == 'load_properties_from_DB'):
                        continue
                    self.actions[resource.obj_name] = ActionAffordance.generate_schema(resource.obj, 
                                                                                self.instance, self.authority)
                self.properties[prop.name] = PropertyAffordance.generate_schema(prop, self.instance, self.authority) 
            except Exception as ex:
                if not self.ignore_errors:
                    raise ex from None
                self.instance.logger.error(f"Error while generating schema for {prop.name} - {ex}")
        # actions       
        for name, resource in self.instance.actions.items():
            if name in self.skip_actions:
                continue    
            try:       
                self.actions[resource.obj_name] = ActionAffordance.generate_schema(resource.obj, self.instance, 
                                                                               self.authority)
            except Exception as ex:
                if not self.ignore_errors:
                    raise ex from None
                self.instance.logger.error(f"Error while generating schema for {name} - {ex}")
        # events
        for name, resource in self.instance.events.items():
            try:
                self.events[name] = EventAffordance.generate_schema(resource, self.instance, self.authority)
            except Exception as ex:
                if not self.ignore_errors:
                    raise ex from None
                self.instance.logger.error(f"Error while generating schema for {resource.obj_name} - {ex}")
        for name, resource in inspect._getmembers(self.instance, lambda o : isinstance(o, Thing), getattr_without_descriptor_read):
            if resource is self.instance or isinstance(resource, EventLoop):
                continue
            if self.links is None or self.links == NotImplemented:
    
    
    def add_links(self):
        for name, resource in self.instance.sub_things.items():
            if resource is self.instance: # or isinstance(resource, EventLoop):
                continue
            if self.links is None:
                self.links = []
            link = Link()
            link.build(resource, self.instance, self.authority)
            self.links.append(link.asdict())
    

    def add_top_level_forms(self):

        self.forms = []

        properties_end_point = f"{self.authority}{self.instance._full_URL_path_prefix}/properties"

        readallproperties = Form()
        readallproperties.href = properties_end_point
        readallproperties.op = "readallproperties"
        readallproperties.htv_methodName = "GET"
        readallproperties.contentType = "application/json"
        # readallproperties.additionalResponses = [AdditionalExpectedResponse().asdict()]
        self.forms.append(readallproperties.asdict())
        
        writeallproperties = Form() 
        writeallproperties.href = properties_end_point
        writeallproperties.op = "writeallproperties"   
        writeallproperties.htv_methodName = "PUT"
        writeallproperties.contentType = "application/json" 
        # writeallproperties.additionalResponses = [AdditionalExpectedResponse().asdict()]
        self.forms.append(writeallproperties.asdict())

        readmultipleproperties = Form()
        readmultipleproperties.href = properties_end_point
        readmultipleproperties.op = "readmultipleproperties"
        readmultipleproperties.htv_methodName = "GET"
        readmultipleproperties.contentType = "application/json"
        # readmultipleproperties.additionalResponses = [AdditionalExpectedResponse().asdict()]
        self.forms.append(readmultipleproperties.asdict())

        writemultipleproperties = Form() 
        writemultipleproperties.href = properties_end_point
        writemultipleproperties.op = "writemultipleproperties"   
        writemultipleproperties.htv_methodName = "PATCH"
        writemultipleproperties.contentType = "application/json"
        # writemultipleproperties.additionalResponses = [AdditionalExpectedResponse().asdict()]
        self.forms.append(writemultipleproperties.asdict())
  
        
    def add_security_definitions(self):
        self.security = 'unimplemented'
        self.securityDefinitions = SecurityScheme().build('unimplemented', self.instance)


    def json(self) -> JSON:
        return self.asdict()

__all__ = [
    ThingDescription.__name__,
    JSONSchema.__name__
]