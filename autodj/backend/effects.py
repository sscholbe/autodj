import ctypes
import math
import os
from abc import ABC
from typing import Callable, Tuple

import numpy as np
import scipy.interpolate
import scipy.signal
import scipy.signal.signaltools

from autodj.backend.audio import AudioFile


class Effect(ABC):
    ID = None
    DefaultValue = 0.0

    def apply(self, inp: np.ndarray, out: np.ndarray, param: np.ndarray,
            bpm: float):
        raise NotImplementedError('Abstract base class')


class IIR(Effect):
    """
    Implements an Infinite Impulse Response filter with a dynamic cutoff.
    This effect is partially written in C (see `iir.c`).

    The dynamic cutoff is implemented by precomputing a numerator/denumerator
    coefficients table for a fixed number of cutoffs and selecting them while
    traversing the samples.
    """

    def __init__(self,
            designer: Callable[[float], Tuple[np.ndarray, np.ndarray]],
            resolution: int = 256):
        """
        Initializes a dynamic IIR.

        `designer` is a function accepting a cutoff value between 0.0 and 1.0
        and returning a coefficients pair (numerators, denumerators).

        It is called many times to precompute the internal coefficients table.
        `resolution` defines the number of cutoff bins.
        """
        super().__init__()
        self.resolution = resolution
        # Load the C implementation of the IIR.
        self.lib = ctypes.CDLL(
            os.path.join(os.path.dirname(os.path.abspath(__file__)),
                'lib/libiir.so'))
        # Precompute the coefficient table on 0.0 to 1.0.
        self.coef_table = np.asarray(
            [designer(p) for p in np.linspace(0.0, 1.0, resolution)]).astype(
            np.float32)

    def apply(self, inp: np.ndarray, out: np.ndarray, param: np.ndarray,
            bpm: float):
        # Turn the continuous cutoff values into discrete indices for the
        # coefficient table.
        indices = np.rint(param * (self.resolution - 1)).astype(np.int32)
        # Call the external C function.
        self.lib.iir(
            self.coef_table.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            ctypes.c_int32(self.coef_table.shape[2]),
            indices.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)),
            inp.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            out.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            ctypes.c_int32(inp.shape[0]))


class LowPass(IIR):
    """
    Implements a dynamic 2nd-order Butterworth lowpass filter.
    """
    ID = 'lpf'
    DefaultValue = 1.0

    def __init__(self):
        # The lowpass should already have a strong effect when turning the
        # cutoff down just a little bit. So we use a rather exponential cutoff
        # to Herz function instead of linearly mapping 0.0 to 0 Hz
        # and 1.0 to 24kHz.
        cut_freq = np.asarray(
            [0, 30, 60, 120, 250, 500, 1000, 2000, 4000, 16000, 24000]) / 24000
        cut_interp = scipy.interpolate.interp1d(
            np.linspace(0.0, 1.0, len(cut_freq)), cut_freq)
        # Special case in designer if the critical frequency is 0 (no-pass)
        # or 1 (all-pass) since `butter` does not handle it.
        designer = lambda cut: (([0, 0, 0], [0, 0, 0]) if cut == 0.0 else (
            ([1, 0, 0], [0, 0, 0]) if cut == 1.0 else scipy.signal.butter(2,
                cut_interp(cut))))
        super().__init__(designer)

    def apply(self, inp: np.ndarray, out: np.ndarray, param: np.ndarray,
            bpm: float):
        super().apply(inp, out, param, bpm)


class Noise(IIR):
    """
    Implements a noise effect that can be used to simulate a riser.
    """
    ID = 'noise'
    DefaultValue = 0.0

    def __init__(self):
        self.noise = AudioFile('data/fx/noise.mp3').signal
        cut_freq = np.asarray([1, 500, 1000, 2500, 5000]) / 24000
        cut_interp = scipy.interpolate.interp1d(
            np.linspace(0.0, 1.0, len(cut_freq)), cut_freq)
        designer = lambda cut: (([0, 0, 0], [0, 0, 0]) if cut == 0.0 else (
            ([1, 0, 0], [0, 0, 0]) if cut == 1.0 else scipy.signal.butter(2,
                cut_interp(cut))))
        super().__init__(designer)

    def apply(self, inp: np.ndarray, out: np.ndarray, param: np.ndarray,
            bpm: float):
        num_repeats = inp.shape[0] / self.noise.shape[0]
        noise_rep = np.tile(self.noise, (int(math.ceil(num_repeats)), 1))[
                    :out.shape[0]]
        noise_rep += np.flip(noise_rep, axis=0)
        noise_rep /= 2
        tmp = np.zeros_like(noise_rep)
        super().apply(noise_rep, tmp, param, bpm)
        out[:, 0] = tmp[:, 0] * param + inp[:, 0] * (1 - param)
        out[:, 1] = tmp[:, 1] * param + inp[:, 1] * (1 - param)


class HighPass(IIR):
    """
    Implements a dynamic 2nd-order Butterworth highpass filter.
    """
    ID = 'hpf'
    DefaultValue = 0.0

    def __init__(self):
        # The highpass should have a small effect when turning the
        # cutoff up just a little bit. So we use a rather exponential cutoff
        # to Herz function instead of linearly mapping 0.0 to 0 Hz and
        # 1.0 to 24kHz.
        cut_freq = np.asarray(
            [0, 30, 60, 120, 250, 500, 1000, 2000, 4000, 16000, 24000]) / 24000
        cut_interp = scipy.interpolate.interp1d(
            np.linspace(0.0, 1.0, len(cut_freq)), cut_freq)
        # Special case in designer if the critical frequency is
        # 0 (no-pass) or 1 (all-pass) since `butter` does not handle it.
        designer = lambda cut: (([1, 0, 0], [0, 0, 0]) if cut == 0.0 else (
            ([0, 0, 0], [0, 0, 0]) if cut == 1.0 else scipy.signal.butter(2,
                cut_interp(cut), 'high')))
        super().__init__(designer)

    def apply(self, inp: np.ndarray, out: np.ndarray, param: np.ndarray,
            bpm: float):
        super().apply(inp, out, param, bpm)


class Reverb(Effect):
    """
    Implements a convolution reverb.
    """
    ID = 'rev'
    DefaultValue = 0.0

    def __init__(self):
        super().__init__()
        self.ir = AudioFile('data/fx/reverb.wav').signal[0:48000]
        self.ir /= np.sum(self.ir)

    def apply(self, inp: np.ndarray, out: np.ndarray, param: np.ndarray,
            bpm: float):
        conv = scipy.signal.fftconvolve(inp, self.ir, mode='full', axes=[0])
        off = self.ir.shape[0] - 1
        par = np.repeat([param], 2, axis=0).T
        out[:] = conv[:-off] * par + (1 - par) * inp


class Volume(Effect):
    """
    Implements a basic volume control.
    """
    ID = 'vol'
    DefaultValue = 1.0

    def __init__(self):
        super().__init__()

    def apply(self, inp: np.ndarray, out: np.ndarray, param: np.ndarray,
            bpm: float):
        # Use square-rooted parameter to keep equal power in transitions
        par = np.repeat([np.sqrt(param)], 2, axis=0).T
        out[:] = inp * par


class Delay(HighPass):
    """
    Implements a simple delay effect (3/16).
    """
    ID = 'dly'
    DefaultValue = 0.0

    def __init__(self):
        super().__init__()

    def apply(self, inp: np.ndarray, out: np.ndarray, param: np.ndarray,
            bpm: float):
        tmp = np.zeros_like(out)

        # Highpass the signal first to reduce bass delay
        super().apply(inp, tmp, np.ones(param.shape[0], dtype=np.float32) * 0.5,
            bpm)
        
        par = np.repeat([param], 2, axis=0).T

        off = int(60 / bpm * AudioFile.SAMPLE_RATE / 2)
        tmp[off:, 0] += tmp[:-off, 0]
        tmp[off * 2:, 1] += tmp[:-off * 2, 1]

        out[:] = inp + tmp * par

