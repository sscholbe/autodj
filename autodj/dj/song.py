# song: Contains functionality to handle songs.

import logging
import os
from tempfile import NamedTemporaryFile
from typing import Tuple

import numpy as np
import svgwrite

from autodj.dj.analysis import analyze_song
from autodj.dj.audio import AudioFile


def get_artist_and_title(file: str) -> Tuple[str, str]:
    """
    Determines artist and song title from file name by splitting at '-'.
    """
    name = os.path.basename(file)
    name = name[:name.rfind('.')]
    idx = name.find('-')
    if idx != -1:
        return name[:idx].strip(), name[idx + 1:].strip()
    else:
        return '', name


class Song(AudioFile):
    """
    Represents a song and stores additional metadata such as BPM and offset.
    """

    def __init__(self, file: str):
        """
        Loads a song from a file (wav/mp3).
        """
        super().__init__(file)

        # Determine artist and title from file name by splitting at '-'
        self.artist, self.title = get_artist_and_title(file)

        self.bpm, self.offset = analyze_song(self)
        self.wave_diagram = self.compute_wave_diagram()
        logging.info(f'{self.file} (BPM {self.bpm}, offset '
                     f'{self.offset / AudioFile.SAMPLE_RATE}, length '
                     f'{self.length / AudioFile.SAMPLE_RATE})')

    def time_to_bar(self, time: float) -> float:
        return (time - self.offset / AudioFile.SAMPLE_RATE) / (
                60 / self.bpm * 4)

    def bar_to_time(self, bar: float) -> float:
        return self.offset / AudioFile.SAMPLE_RATE + bar * 60 / self.bpm * 4

    def compute_wave_diagram(self, color: str = 'white') -> bytes:
        """
        Computes the wave diagram as SVG and returns the binary data.
        """
        with NamedTemporaryFile('rb') as file:
            # 25 pixels per second
            width = self.length / AudioFile.SAMPLE_RATE * 25

            # SVG has a height of 100 pixels
            svg = svgwrite.Drawing(file.name, size=(width, 100))

            # Use pooling to reduce the number of lines with quantile instead
            # of maximum to prevent over saturation
            sig = np.quantile(
                np.reshape(self.signal[:self.length - self.length % 4096:32, :],
                    (-1, 128, 2)), 0.95, axis=1)

            time = np.linspace(0, width, sig.shape[0], endpoint=False)

            # Zero-line
            svg.add(svg.line((0, 50), (time[-1], 50), stroke=color))

            # Signal line for both channels
            svg.add(svg.polyline(points=[(time[0], 50)] + list(
                zip(time, 50 - 50 * sig[:, 0])) + [(time[-1], 50)], fill=color))
            svg.add(svg.polyline(points=[(time[0], 50)] + list(
                zip(time, 50 + 50 * sig[:, 1])) + [(time[-1], 50)], fill=color))
            svg.save()

            return file.read()
