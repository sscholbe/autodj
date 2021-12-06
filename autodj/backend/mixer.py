import inspect
import multiprocessing
from typing import Dict

import numpy as np
import pyaudio
import pyrubberband

import autodj.backend.effects
from autodj.backend.audio import AudioFile
from autodj.backend.channel import Channel
from autodj.backend.fsm import MixerFSM


def get_all_effects() -> Dict[str, autodj.backend.effects.Effect]:
    """
    Get an instance of all the effects defined in the `effects` module with a
    valid ID
    """
    is_valid = lambda m: inspect.isclass(m) and issubclass(m,
        autodj.backend.effects.Effect) and m.ID is not None
    return dict([(fx.ID, fx()) for _, fx in
                 inspect.getmembers(autodj.backend.effects, is_valid)])


class Mixer:
    """
    Implements the mixer that is responsible for playback and mixing.
    """
    BUFFER_SIZE = 12000
    TRANSIENT_SIZE = 1000

    def __init__(self):
        """
        Initializes the mixer.
        """
        self.global_time = 0
        self.global_bpm = 130

        self.channels = [Channel(), Channel()]

        self.lock = multiprocessing.Lock()

        # Square-rooted equal power cross-fade to reduce transients between
        # blocks
        self.fade_in = np.repeat(
            [np.sqrt(np.linspace(0, 1, Mixer.TRANSIENT_SIZE))], 2, axis=0).T
        self.fade_out = np.repeat(
            [np.sqrt(np.linspace(1, 0, Mixer.TRANSIENT_SIZE))], 2, axis=0).T

        # Setup the finite state machine that controls the mixer
        self.fsm = MixerFSM(self)

        self.all_effects = get_all_effects()

        # Setup audio driver
        self.audio = pyaudio.PyAudio()
        self.stream = self.audio.open(format=pyaudio.paFloat32, channels=2,
            rate=AudioFile.SAMPLE_RATE, frames_per_buffer=Mixer.BUFFER_SIZE,
            output=True, input=False, stream_callback=lambda x, y, z, w: (
                self.produce(), pyaudio.paContinue))

        self.stream.start_stream()

    def produce(self) -> np.ndarray:
        """
        Produces the next block for playback.
        """
        master = np.zeros((Mixer.BUFFER_SIZE, 2), dtype=np.float32)

        with self.lock:
            for channel in self.channels:
                if not channel.is_playing:
                    continue

                # Speedup of this song with respect to the global BPM
                # Find smartest BPM to fade (i.e., with closest speedup to 1)
                speeds = [self.global_bpm / channel.song.bpm,
                          self.global_bpm / channel.song.bpm / 2,
                          self.global_bpm / channel.song.bpm * 2]
                speed = speeds[np.abs(1 - np.asarray(speeds)).argmin()]

                # Stream twice the signal needed in buffer (in case of heavy
                # stretching)
                # Then stretch the signal using pyrubberband
                src = channel.song.stream(
                    int(channel.time * AudioFile.SAMPLE_RATE),
                    int(Mixer.BUFFER_SIZE * 2))

                stretched = pyrubberband.time_stretch(src,
                    AudioFile.SAMPLE_RATE, speed, {'-R': '-R'}).astype(
                    np.float32)

                inp = stretched[0:Mixer.BUFFER_SIZE]

                # Reduce transients by cross-fading the future signal of the
                # last block
                if channel.transient is not None:
                    inp[:Mixer.TRANSIENT_SIZE] *= self.fade_in
                    inp[
                    :Mixer.TRANSIENT_SIZE] += self.fade_out * channel.transient

                # Update transient for next block
                channel.transient = stretched[
                                    Mixer.BUFFER_SIZE:Mixer.BUFFER_SIZE +
                                                      Mixer.TRANSIENT_SIZE]

                # Apply the effect chain
                if channel.last is None:
                    channel.last = np.zeros_like(inp)

                tmp = np.concatenate((channel.last, inp))
                channel.last[:] = inp[:]
                inp = tmp

                t = np.linspace(channel.time,
                    channel.time + Mixer.BUFFER_SIZE * 2 /
                    AudioFile.SAMPLE_RATE * speed,
                    inp.shape[0], dtype=np.float32)

                out = np.empty_like(inp)
                for fx in channel.transition:
                    param = channel.transition[fx](t)
                    self.all_effects[fx].apply(inp, out, param, self.global_bpm)
                    out, inp = inp, out

                channel.time += Mixer.BUFFER_SIZE / AudioFile.SAMPLE_RATE * \
                                speed
                master += inp[Mixer.BUFFER_SIZE:]

            self.global_time += Mixer.BUFFER_SIZE / AudioFile.SAMPLE_RATE

            # Update the Finite State Machine
            self.fsm.update()

        return np.clip(master, -1, 1)
