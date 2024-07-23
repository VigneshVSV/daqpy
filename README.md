# hololinked - Pythonic Object-Oriented Supervisory Control & Data Acquisition / Internet of Things

### Description

For beginners - `hololinked` is a server side pythonic package suited for instrumentation control and data acquisition over network, especially with HTTP. If you have a requirement to control and capture data from your hardware/instrumentation, show the data in a browser/dashboard, provide a GUI or run automated scripts, `hololinked` can help. Even for isolated applications or a small lab setup without networking concepts, one can still separate the concerns of the tools that interact with the hardware & the hardware itself.
<br/> <br/>
For those familiar with RPC & web development - This package is an implementation of a ZeroMQ-based Object Oriented RPC with customizable HTTP end-points. A dual transport in both ZMQ and HTTP is provided to maximize flexibility in data type, serialization and speed, although HTTP is preferred for networked applications. If one is looking for an object oriented approach towards creating components within a control or data acquisition system, or an IoT device, one may consider this package. 
 
[![Documentation Status](https://readthedocs.org/projects/hololinked/badge/?version=latest)](https://hololinked.readthedocs.io/en/latest/?badge=latest) [![PyPI](https://img.shields.io/pypi/v/hololinked?label=pypi%20package)](https://pypi.org/project/hololinked/) [![PyPI - Downloads](https://img.shields.io/pypi/dm/hololinked)](https://pypistats.org/packages/hololinked) [![codecov](https://codecov.io/gh/VigneshVSV/hololinked/graph/badge.svg?token=JF1928KTFE)](https://codecov.io/gh/VigneshVSV/hololinked) [![Discord](https://img.shields.io/discord/1265289049783140464)](https://discord.gg//kEz87zqQXh)

### To Install

From pip - ``pip install hololinked``

Or, clone the repository (develop branch for latest codebase) and install `pip install .` / `pip install -e .`. The conda env ``hololinked.yml`` can also help to setup all dependencies. 

### Usage/Quickstart

`hololinked` is compatible with the [Web of Things](https://www.w3.org/WoT/) recommended pattern for developing hardware/instrumentation control software. 
Each device or thing can be controlled systematically when their design in software is segregated into properties, actions and events. In object oriented terms:
- the hardware is (generally) represented by a class 
- properties are validated get-set attributes of the class which may be used to model hardware settings, hold captured/computed data or generic network accessible quantities
- actions are methods which issue commands like connect/disconnect, execute a control routine, start/stop measurement, or run arbitray python logic
- events can asynchronously communicate/push (arbitrary) data to a client (say, a GUI), like alarm messages, streaming measured quantities etc.

It does not even matter whether you are controlling your hardware locally or remotely, what protocol you use, what is the nature of the client etc., 
one has to provide these three interactions with the hardware. In this package, the base class which enables this classification is the `Thing` class. Any class that inherits the `Thing` class 
can instantiate properties, actions and events which 
become visible to a client in this segragated manner. For example, consider an optical spectrometer, the following code is possible:

> This is a fairly mid-level intro focussed on HTTP. If you are beginner or looking for ZMQ, for another variant check [How-To](https://hololinked.readthedocs.io/en/latest/howto/index.html)

#### Import Statements

```python

from hololinked.server import Thing, Property, action, Event
from hololinked.server.properties import String, Integer, Number, List
from seabreeze.spectrometers import Spectrometer # device driver
```

#### Definition of one's own hardware controlling class

subclass from Thing class to "make a network accessible Thing":

```python 
class OceanOpticsSpectrometer(Thing):
    """
    OceanOptics spectrometers using seabreeze library. Device is identified by serial number. 
    """
    
```

#### Instantiating properties

Say, we wish to make device serial number, integration time and the captured intensity as properties. There are certain predefined properties available like `String`, `Number`, `Boolean` etc. 
or one may define one's own. To create properties:

```python

class OceanOpticsSpectrometer(Thing):
    """class doc"""
    
    serial_number = String(default=None, allow_None=True, URL_path='/serial-number', 
                        doc="serial number of the spectrometer to connect/or connected",
                        http_method=("GET", "PUT"))
    # GET and PUT is default for reading and writing the property respectively. 
    # Use other HTTP methods if necessary.  

    integration_time = Number(default=1000, bounds=(0.001, None), crop_to_bounds=True, 
                            URL_path='/integration-time', 
                            doc="integration time of measurement in milliseconds")

    intensity = List(default=None, allow_None=True, 
                    doc="captured intensity", readonly=True, 
                    fget=lambda self: self._intensity)     

    def __init__(self, instance_name, serial_number, **kwargs):
        super().__init__(instance_name=instance_name, serial_number=serial_number, **kwargs)

```

In non-expert terms, properties look like class attributes however their data containers are instantiated at object instance level by default.
For example, the `integratime_time` property defined above as `Number`, whenever set/written, will be validated as a float or int, cropped to bounds and assigned as an attribute to each instance of the `OceanOpticsSpectrometer` class with an internally generated name. It is not necessary to know this internally generated name as the property value can be accessed again in any python logic, say, `print(self.integration_time)`. 

To overload the get-set (or read-write) of properties, one may do the following:

```python
class OceanOpticsSpectrometer(Thing):

    integration_time = Number(default=1000, bounds=(0.001, None), crop_to_bounds=True, 
                            URL_path='/integration-time', 
                            doc="integration time of measurement in milliseconds")

    @integration_time.setter # by default called on http PUT method
    def apply_integration_time(self, value : float):
        self.device.integration_time_micros(int(value*1000))
        self._integration_time = int(value) 
      
    @integration_time.getter # by default called on http GET method
    def get_integration_time(self) -> float:
        try:
            return self._integration_time
        except AttributeError:
            return self.properties["integration_time"].default 

```

In this case, instead of generating a data container with an internal name, the setter method is called when `integration_time` property is set/written. One might add the hardware device driver (say, supplied by the manufacturer) logic here to apply the property onto the device. In the above example, there is not a way provided by lower level library to read the value from the device, so we store it in a variable after applying it and supply the variable back to the getter method. Normally, one would also want the getter to read from the device directly.
 
Those familiar with Web of Things (WoT) terminology may note that these properties generate the property affordance schema to become accessible by the [node-wot](https://github.com/eclipse-thingweb/node-wot) HTTP(s) client. An example of autogenerated property affordance for `integration_time` is as follows:

```JSON
"integration_time": {
    "title": "integration_time",
    "description": "integration time of measurement in milliseconds",
    "type": "number",
    "forms": [{
            "href": "https://example.com/spectrometer/integration-time",
            "op": "readproperty",
            "htv:methodName": "GET",
            "contentType": "application/json"
        },{
            "href": "https://example.com/spectrometer/integration-time",
            "op": "writeproperty",
            "htv:methodName": "PUT",
            "contentType": "application/json"
        }
    ],
    "minimum": 0.001
},
```
If you are not familiar with Web of Things or the term "property affordance", consider the above JSON as a description of 
what the property represents and how to interact with it from somewhere else. Such a JSON is both human-readable, yet consumable 
by a client provider to create a client object to interact with the property in the way the property demands. You, as the developer,
only need to use the client.  

The URL path segment `../spectrometer/..` in href field is taken from the `instance_name` which was specified in the `__init__`. 
This is a mandatory key word argument to the parent class `Thing` to generate a unique name/id for the instance. One should use URI compatible strings.

#### Specify methods as actions

decorate with `action` decorator on a python method to claim it as a network accessible method:

```python

class OceanOpticsSpectrometer(Thing):

    @action(URL_path='/connect', http_method="POST") # POST is default for actions
    def connect(self, serial_number = None):
        """connect to spectrometer with given serial number"""
        if serial_number is not None:
            self.serial_number = serial_number
        self.device = Spectrometer.from_serial_number(self.serial_number)
        self._wavelengths = self.device.wavelengths().tolist()
```

Methods that are neither decorated with action decorator nor acting as getters-setters of properties remain as plain python methods and are **not** accessible on the network.

In WoT Terminology, again, such a method becomes specified as an action affordance (or a description of what the action represents
and how to interact with it):

```JSON
"connect": {
    "title": "connect",
    "description": "connect to spectrometer with given serial number",
    "forms": [
        {
            "href": "https://example.com/spectrometer/connect",
            "op": "invokeaction",
            "htv:methodName": "POST",
            "contentType": "application/json"
        }
    ],
    "input": {
        "type": "object",
        "properties": {
            "serial_number": {
                "type": "string"
            }
        },
        "additionalProperties": false
    }
},
```
> input and output schema ("input" field above which describes the argument type `serial_number`) are optional and will be discussed in docs

#### Defining and pushing events

create a named event using `Event` object that can push any arbitrary data:

```python
class OceanOpticsSpectrometer(Thing):

    # only GET HTTP method possible for events
    intensity_measurement_event = Event(name='intensity-measurement-event', 
            URL_path='/intensity/measurement-event',
            doc="""event generated on measurement of intensity, 
            max 30 per second even if measurement is faster.""",
            schema=intensity_event_schema) 
            # schema is optional and will be discussed later,
            # assume the intensity_event_schema variable is valid
            
    def capture(self): # not an action, but a plain python method
        self._run = True 
        last_time = time.time()
        while self._run:
            self._intensity = self.device.intensities(
                                        correct_dark_counts=False,
                                        correct_nonlinearity=False
                                    )
            curtime = datetime.datetime.now()
            measurement_timestamp = curtime.strftime('%d.%m.%Y %H:%M:%S.') + '{:03d}'.format(
                                                            int(curtime.microsecond /1000))
            if time.time() - last_time > 0.033: # restrict speed to avoid overloading
                self.intensity_measurement_event.push({
                    "timestamp" : measurement_timestamp, 
                    "value" : self._intensity.tolist()
                })
                last_time = time.time()

    @action(URL_path='/acquisition/start', http_method="POST")
    def start_acquisition(self):
        if self._acquisition_thread is not None and self._acquisition_thread.is_alive():
            return
        self._acquisition_thread = threading.Thread(target=self.capture) 
        self._acquisition_thread.start()

    @action(URL_path='/acquisition/stop', http_method="POST")
    def stop_acquisition(self):
        self._run = False 
```
Events can stream live data without polling or push data to a client whose generation in time is uncontrollable. 

In WoT Terminology, such an event becomes specified as an event affordance (or a description of 
what the event represents and how to subscribe to it) with subprotocol SSE (HTTP-SSE):

```JSON
"intensity_measurement_event": {
    "title": "intensity-measurement-event",
    "description": "event generated on measurement of intensity, max 30 per second even if measurement is faster.",
    "forms": [
        {
          "href": "https://example.com/spectrometer/intensity/measurement-event",
          "subprotocol": "sse",
          "op": "subscribeevent",
          "htv:methodName": "GET",
          "contentType": "text/plain"
        }
    ],
    "data": {
        "type": "object",
        "properties": {
            "value": {
                "type": "array",
                "items": {
                    "type": "number"
                }
            },
            "timestamp": {
                "type": "string"
            }
        }
    }
}
```
> data schema ("data" field above which describes the event payload) are optional and discussed later

Although the code is the very familiar & age-old RPC server style, one can directly specify HTTP methods and URL path for each property, action and event. A configurable HTTP Server is already available (from `hololinked.server.HTTPServer`) which redirects HTTP requests to the object according to the specified HTTP API on the properties, actions and events. To plug in a HTTP server: 

```python
import ssl, os, logging
from multiprocessing import Process
from hololinked.server import HTTPServer

if __name__ == '__main__':
    ssl_context = ssl.SSLContext(protocol = ssl.PROTOCOL_TLS)
    ssl_context.load_cert_chain(f'assets{os.sep}security{os.sep}certificate.pem',
                        keyfile = f'assets{os.sep}security{os.sep}key.pem')
    
    O = OceanOpticsSpectrometer(
        instance_name='spectrometer',
        serial_number='S14155',
        log_level=logging.DEBUG
    )
    O.run_with_http_server(ssl_context=ssl_context)
```

Here one can see the use of `instance_name` and why it turns up in the URL path. See the detailed example of the above code [here](https://gitlab.com/hololinked-examples/oceanoptics-spectrometer/-/blob/simple/oceanoptics_spectrometer/device.py?ref_type=heads). 

##### NOTE - The package is under active development. Contributors welcome, please check CONTRIBUTING.md. 

- [example repository](https://github.com/VigneshVSV/hololinked-examples) - detailed examples for both clients and servers
- [helper GUI](https://github.com/VigneshVSV/hololinked-portal) - view & interact with your object's methods, properties and events. 
 
See a list of currently supported possibilities while using this package [below](#currently-supported). 

> You may use a script deployment/automation tool to remote stop and start servers, in an attempt to remotely control your hardware scripts. 

One may use the HTTP API according to one's beliefs (including letting the package auto-generate it), but it is mainly intended for web development and cross platform clients like the [node-wot](https://github.com/eclipse-thingweb/node-wot) HTTP(s) client. If your plan is to develop a truly networked system, it is recommended to learn more and use [Thing Descriptions](https://www.w3.org/TR/wot-thing-description11) to describe your hardware. A Thing Description will be automatically generated if absent as shown in JSON examples above or can be supplied manually. The node-wot HTTP(s) client will be able to consume such a description, validate it and abstract away the protocol level details so that one can invoke actions, read & write properties or subscribe to events in a technology agnostic manner. In this way, one can plugin code developed from this package to the rest of the IoT/data-acquisition tools, protocols & standardizations. To know more about client side scripting with node-wot, please look into the documentation [How-To](https://hololinked.readthedocs.io/en/latest/howto/clients.html#using-node-wot-http-s-client) section.

### Currently Supported

- control method execution and property write with a custom finite state machine.
- database (Postgres, MySQL, SQLite - based on SQLAlchemy) support for storing and loading properties when the object dies and restarts. 
- auto-generate Thing Description for Web of Things applications. 
- use serializer of your choice (except for HTTP) - MessagePack, JSON, pickle etc. & extend serialization to suit your requirement. HTTP Server will support only JSON serializer to maintain compatibility with node-wot. Default is JSON serializer based on msgspec.
- asyncio compatible - async RPC server event-loop and async HTTP Server - write methods in async 
- choose from multiple ZeroMQ transport methods. Some of the possibilities one can achieve by choosing ZMQ transport methods:
  - run HTTP Server & python object in separate processes or the same process
  - serve multiple objects with the same HTTP server
  - run direct ZMQ-TCP server without HTTP details
  - expose only a dashboard or web page on the network without exposing the hardware itself

Again, please check examples or the code for explanations. Documentation is being activety improved. 

### Currently being worked

- improving accuracy of Thing Descriptions 
- cookie credentials for authentication - as a workaround until credentials are supported, use `allowed_clients` argument on HTTP server which restricts access based on remote IP supplied with the HTTP headers.

### Some Day In Future

- mongo DB support for DB operations
- HTTP 2.0 

### Contact

Contributors welcome for all my projects related to hololinked including web apps. Please write to my contact email available at my [website](https://hololinked.dev). 
