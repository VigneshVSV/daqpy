from hololinked.server import RemoteObject, remote_method, HTTPServer, Event
from hololinked.server.remote_parameters import String, ClassSelector
from seabreeze.spectrometers import Spectrometer
import numpy 

class OceanOpticsSpectrometer(RemoteObject):
    """
    Spectrometer example object 
    """

    serial_number = String(default=None, allow_None=True, constant=True, 
                        URL_path="/serial-number",
                        doc="serial number of the spectrometer")

    def __init__(self, instance_name, serial_number, connect, **kwargs):
        super().__init__(instance_name=instance_name, **kwargs)
        self.serial_number = serial_number
        if connect and self.serial_number is not None:
            self.connect()
        self.measurement_event = Event(name='intensity-measurement', 
                                URL_path='/intensity/measurement-event')

    @remote_method(URL_path='/connect', http_method="POST")
    def connect(self):
        self.device = Spectrometer.from_serial_number(self.serial_number)
              
    intensity = ClassSelector(class_=(numpy.ndarray, list), default=[], 
                    doc="captured intensity", readonly=True, 
                    URL_path='/intensity', fget=lambda self: self._intensity)       

    def capture(self):
        self._run = True 
        while self._run:
            self._intensity = self.device.intensities(
                                        correct_dark_counts=True,
                                        correct_nonlinearity=True
                                    )
            self.measurement_event.push(self._intensity.tolist())

    
if __name__ == '__main__':
    spectrometer = OceanOpticsSpectrometer(instance_name='spectrometer', 
                        serial_number='USB2+H15897', connect=True)
    spectrometer.run(
        http_server=HTTPServer(port=8080)
    )
