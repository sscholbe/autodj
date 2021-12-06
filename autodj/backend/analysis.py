from typing import List, Tuple

import numpy as np
import scipy.fft
import scipy.interpolate
import scipy.ndimage
import scipy.signal
import scipy.signal
import scipy.spatial

from autodj.backend.audio import AudioFile


def add_pw_functions(x1: List[float], y1: List[float], x2: List[float],
        y2: List[float]) -> Tuple[List[float], List[float]]:
    """
    Adds two piecewise linear functions.
    """
    a = scipy.interpolate.interp1d(x1, y1, fill_value=(0, 0),
        bounds_error=False)
    if x2.shape[0] > 0:
        b = scipy.interpolate.interp1d(x2, y2, fill_value=(0, 0),
            bounds_error=False)
    else:
        b = lambda x: 0
    abx = np.unique(np.concatenate((x1, x2)))
    ab = a(abx) + b(abx)
    ab = scipy.interpolate.interp1d(abx, ab, fill_value=(0, 0),
        bounds_error=False)
    return np.asarray(abx), np.asarray(ab(abx))


def normalize(x):
    """
    Subtracts the trend based on a 2nd degree polynomial and normalizes.
    """
    p = np.arange(x.shape[0])
    y = (x - np.polyval(np.polyfit(p, x, 2), p))
    l = np.linalg.norm(y, 2)
    if l == 0:
        return y
    else:
        return y / l


def _to_reasonable_bpm(bpm: float) -> List[float]:
    """
    Converts a BPM to more reasonable BPMs by doubling/halving.
    Returns a sorted list of suggested BPMs.
    """
    if bpm <= 0:
        raise ValueError()
    cands = []
    while bpm > 180 and bpm % 2 == 0:
        bpm //= 2
    while bpm < 70:
        bpm *= 2
    cands.append(bpm)
    if bpm % 2 == 0 and bpm >= 140:
        cands.append(bpm // 2)
    if bpm <= 90:
        cands.append(bpm * 2)
    return list(np.sort(cands))


def analyze_song(src: AudioFile) -> Tuple[float, float]:
    """
    Determines BPM and offset of the given song.
    Returns a tuple `bpm, offset`.
    """

    # Use one minute of the original signal
    inp = src.stream(0, AudioFile.SAMPLE_RATE * 60)[:, 0]
    b, a = scipy.signal.butter(2, 0.01)
    inp = scipy.signal.lfilter(b, a, inp)
    f, t, Sxx = scipy.signal.spectrogram(inp, AudioFile.SAMPLE_RATE)

    #
    # Detect BPM
    #

    Sxx_flat = np.sum(Sxx, axis=0)
    corr = np.correlate(Sxx_flat, Sxx_flat, mode='full')
    corr = scipy.ndimage.gaussian_filter(corr, 10)
    corr = corr[corr.shape[0] // 2:]
    x = np.arange(corr.shape[0])
    corr -= np.polyval(np.polyfit(x, corr, 3), x)
    f = np.abs(scipy.fft.fft(corr))
    f = f[:f.shape[0] // 2]
    abx = np.empty(0)
    aby = np.empty(0)
    l = f.shape[0]
    d = 1
    while l >= 2:
        abx, aby = add_pw_functions(np.arange(f.shape[0]) / d, f, abx, aby)
        l /= 2
        d += 1
    ind = (abx >= 30) & (abx <= 180)
    abx = abx[ind]
    aby = aby[ind]
    aby -= np.polyval(np.polyfit(abx, aby, 2), abx)
    bpms = abx[np.argmax(aby)]
    bpm = _to_reasonable_bpm(bpms)[-1]

    #
    # Detect offset
    #

    Sxx_bass = Sxx[0, :]
    bar = np.abs(t - (60 / bpm) * 4).argmin()
    acc = np.zeros_like(Sxx_bass[0:bar])
    for i in range(0, 2048):
        off = np.abs(t - (60 / bpm) * i * 4).argmin()
        if off + bar >= Sxx_bass.shape[0]:
            break
        acc += normalize(Sxx_bass[off:off + bar])
    offset = int((t[acc.argmax()] % (60 / bpm)) * AudioFile.SAMPLE_RATE)

    return bpm, offset
