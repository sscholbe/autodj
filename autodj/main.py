import atexit
import logging
from ctypes import *

from dj.api import start_api
from dj.mixer import Mixer


def py_error_handler(filename, line, function, err, fmt):
    pass


if __name__ == "__main__":
    # Disable messages by PyAudio
    ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int,
        c_char_p)
    c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)
    asound = cdll.LoadLibrary('libasound.so')
    asound.snd_lib_error_set_handler(c_error_handler)

    # Setup logging
    logging.basicConfig(level=logging.INFO,
        format="(%(asctime)s) [%(levelname)s] %(message)s", datefmt='%H:%M:%S',
        handlers=[logging.FileHandler("debug.log"), logging.StreamHandler()])

    # Start mixer and server
    logging.info('Initializing mixer')
    mix = Mixer()


    # Kill the mixer on exit
    def exit_handler():
        mix.stream.stop_stream()


    atexit.register(exit_handler)

    logging.info('Initializing web server')
    start_api(mix)
