import logging
from enum import Enum
from typing import Dict, List, Callable, Tuple, Optional
import scipy.interpolate

import numpy as np
import scipy

from autodj.backend.song import Song

TransitionDef = Dict[str, List[Tuple[float, float]]]
TransitionFunc = Dict[str, Callable[[np.ndarray], np.ndarray]]


def create_transition_func(mixer, trans: TransitionDef, start: float,
        end: float, inp: bool) -> TransitionFunc:
    """
    Computes the transition function for the given transition.
    """
    res = {}
    length = end - start

    for fx, data in trans.items():
        d = np.asarray(data).T
        # Set out of bounds value to default value (i.e. no effect)
        left_bound = mixer.all_effects[fx].DefaultValue
        right_bound = left_bound
        # Volume is special because we want to fade in/out completely
        if fx == 'vol':
            left_bound = 0.0 if inp else 1.0
            right_bound = 1.0 if inp else 0.0

        res[fx] = scipy.interpolate.interp1d(start + d[0] * length, d[1],
            fill_value=(left_bound, right_bound), bounds_error=False)
    return res


class TransitionStage(Enum):
    """
    Represents the stage of a transition in a channel.
    """
    # No transition stage if channel is not playing
    NONE = 0
    # Transition has not started yet
    PRE = 1
    # Active transition
    MIX = 2
    # Transition is finished
    POST = 3


class Channel:
    """
    Represents a channel in the mixer.
    """

    def __init__(self):
        self.time: float = 0.0
        self.song: Optional[Song] = None
        self.transient: np.ndarray = None
        self.transition: TransitionFunc = {}
        self.transition_bars: List[int] = None
        self.last: np.ndarray = None
        self.is_playing: bool = False

    def clear(self):
        self.__init__()

    def load(self, song: Song):
        self.clear()
        self.song = song
        logging.info(f'Channel load {song.file}')

    def clear_transition(self):
        self.transition = {}
        self.transition_bars = None

    def play(self, time: float):
        self.time = time
        self.is_playing = True

    def stage(self) -> TransitionStage:
        """
        Returns the stage of the transition.
        """
        if not self.is_playing or self.song is None:
            return TransitionStage.NONE
        if self.transition_bars is None:
            return TransitionStage.POST

        bar = self.song.time_to_bar(self.time)
        if bar < self.transition_bars[0]:
            return TransitionStage.PRE
        if bar >= self.transition_bars[1] + 1:
            return TransitionStage.POST
        return TransitionStage.MIX
