import io
import subprocess
import wave

import numpy as np


class AudioFile:
    """
    Implements a streamable audio file.
    """
    SAMPLE_RATE = 48000

    def __init__(self, file: str):
        """
        Loads an audio file. Supports many file formats (e.g., mp3) as it
        uses ffmpeg to convert the file.
        """
        self.file = file

        # Convert into standard 16bit 48kHz stereo wave file using ffmpeg
        # Directly pipe the result into our memory
        pipe = subprocess.run(
            ['ffmpeg', '-y', '-i', file, '-fflags', '+bitexact', '-flags',
             '+bitexact', '-acodec', 'pcm_s16le', '-ar',
             str(AudioFile.SAMPLE_RATE), '-ac', '2', '-f', 'wav', 'pipe:1'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=2 ** 24,
            check=True)

        # Convert PCM output from pipe into numpy float array
        with wave.open(io.BytesIO(pipe.stdout), 'rb') as wav:
            self.signal = np.reshape(
                np.fromstring(wav.readframes(-1), dtype=np.int16).astype(
                    np.float32) / 32768, (-1, 2))

        self.length = self.signal.shape[0]

        # Normalize signal
        max_sig = np.max(np.abs(self.signal))
        if max_sig > 0:
            self.signal /= max_sig

    def stream(self, pos: int, length: int) -> np.ndarray:
        """
        Streams the signal at `pos` of with length `length`.
        Pads with zeros outside of bounds.
        """
        out = np.zeros((length, 2), dtype=np.float32)
        if length <= 0 or pos + length <= 0 or pos >= self.length:
            return out
        from_inp = min(max(pos, 0), self.length)
        to_inp = min(pos + length, self.length)
        from_out = min(max(-pos, 0), length)
        out[from_out:from_out + (to_inp - from_inp)] = self.signal[
                                                       from_inp:to_inp]
        return out
