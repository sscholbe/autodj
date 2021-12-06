from enum import Enum
from typing import Optional, List

from attr import dataclass

from autodj.backend.channel import TransitionStage, create_transition_func, Channel, \
    TransitionDef
from autodj.backend.song import Song


class TargetChannel(Enum):
    INVALID = 0
    A = 1
    B = 2


class MixerStage(Enum):
    INVALID = 0,
    # No song or just one song (in channel A) is active
    INIT_A = 1,
    # If we queue, then for a transition from A to B
    A_TO_B = 2,
    # If we queue, then for a transition from B to A
    B_TO_A = 3


@dataclass
class QueueData:
    transition_src: TransitionDef
    transition_dst: TransitionDef
    selection_src: List[int]
    selection_dst: List[int]


class MixerFSM:
    """
    Implements the Finite State Machine that controls the mixer via three
    operations: load a song, queue a transition and cancel a queued transition.
    """

    def __init__(self, mixer):
        self.mixer = mixer
        self.stage = MixerStage.INIT_A

    def update(self):
        channel_a = self.mixer.channels[0]
        stage_a = channel_a.stage()
        channel_b = self.mixer.channels[1]

        if self.stage == MixerStage.INIT_A and stage_a == \
                TransitionStage.POST and channel_b.song is not None:
            # A has faded in and we can now enable transitions from A to B
            self.stage = MixerStage.A_TO_B

    def get_master_channel(self) -> TargetChannel:
        channel_a = self.mixer.channels[0]
        stage_a = channel_a.stage()
        channel_b = self.mixer.channels[1]
        stage_b = channel_b.stage()

        if self.stage == MixerStage.INIT_A:
            return TargetChannel.A
        elif self.stage == MixerStage.A_TO_B:
            if stage_b in [TransitionStage.NONE, TransitionStage.PRE]:
                return TargetChannel.A
            else:
                return TargetChannel.B
        elif self.stage == MixerStage.B_TO_A:
            if stage_a in [TransitionStage.NONE, TransitionStage.PRE]:
                return TargetChannel.B
            else:
                return TargetChannel.A

    def _apply_transition(self, qd: QueueData, channel_src: Channel,
            channel_dst: Channel):
        song_src = channel_src.song
        song_dst = channel_dst.song

        pa = song_src.bar_to_time(qd.selection_src[0])
        pb = song_dst.bar_to_time(qd.selection_dst[0])

        qa = song_src.bar_to_time(qd.selection_src[1] + 1)
        qb = song_dst.bar_to_time(qd.selection_dst[1] + 1)

        channel_src.transition_bars = qd.selection_src
        channel_dst.transition_bars = qd.selection_dst

        # Compute the transition function
        channel_src.transition = create_transition_func(self.mixer,
            qd.transition_src, pa, qa, inp=False)
        channel_dst.transition = create_transition_func(self.mixer,
            qd.transition_dst, pb, qb, inp=True)

        # Match both selections
        bars_to_transition = qd.selection_src[0] - song_src.time_to_bar(
            channel_src.time)
        channel_dst.play(
            song_dst.bar_to_time(qd.selection_dst[0] - bars_to_transition))

    def load(self, file: str, dry: bool = False) -> Optional[TargetChannel]:
        """
        Plays the song in the suitable channel. If `dry` the channel is
        returned without executing the operation.
        """
        # Try to find song in the channels first
        song = None
        if not dry:
            for channel in self.mixer.channels:
                if channel.song is not None and channel.song.file == file:
                    song = channel.song

            # Otherwise load it
            if song is None:
                song = Song(file)

        channel_a = self.mixer.channels[0]
        stage_a = channel_a.stage()
        channel_b = self.mixer.channels[1]
        stage_b = channel_b.stage()

        if self.stage == MixerStage.INIT_A:
            if channel_a.song is None:
                if dry:
                    return TargetChannel.A
                # No song loaded yet
                channel_a.load(song)
            else:
                # A is loaded but B is missing
                if stage_a == TransitionStage.NONE:
                    if dry:
                        return TargetChannel.A
                    # A is not queued so we reload A instead of loading B
                    channel_a.load(song)
                else:
                    if dry:
                        return TargetChannel.B
                    # A is queued, now we load B
                    channel_b.load(song)
                    if stage_a == TransitionStage.POST:
                        # A has faded in, we can now enable transitions A to B
                        self.stage = MixerStage.A_TO_B
        elif self.stage == MixerStage.A_TO_B:
            if stage_a == TransitionStage.POST:
                if stage_b == TransitionStage.NONE:
                    if dry:
                        return TargetChannel.B
                    # B is not playing so we can still load other songs in B
                    channel_b.load(song)
                elif stage_b == TransitionStage.POST:
                    if dry:
                        return TargetChannel.A
                    # We transitioned from A to B, now A can be loaded again
                    channel_a.load(song)
                    self.stage = MixerStage.B_TO_A
        elif self.stage == MixerStage.B_TO_A:
            if stage_b == TransitionStage.POST:
                if stage_a == TransitionStage.NONE:
                    if dry:
                        return TargetChannel.A
                    # A is not playing so we can still load other songs in A
                    channel_a.load(song)
                elif stage_a == TransitionStage.POST:
                    if dry:
                        return TargetChannel.B
                    # We transitioned from B to A, now B can be loaded
                    channel_b.load(song)
                    self.stage = MixerStage.A_TO_B
        if dry:
            # No load possible
            return TargetChannel.INVALID

    def cancel(self, dry: bool = False) -> Optional[TargetChannel]:
        """
        Cancels the queued transition in the suitable channel. If `dry`
        the channel is returned without executing the operation.
        """
        channel_a = self.mixer.channels[0]
        stage_a = channel_a.stage()
        channel_b = self.mixer.channels[1]
        stage_b = channel_b.stage()

        if self.stage == MixerStage.INIT_A:
            # We can't cancel in init (theres at most one song playing)
            pass
        elif self.stage == MixerStage.A_TO_B:
            if stage_a == TransitionStage.PRE:
                if dry:
                    return TargetChannel.B
                # A has not started mixing yet so we can still cancel B
                channel_a.clear_transition()
                channel_b.load(channel_b.song)
        elif self.stage == MixerStage.B_TO_A:
            if stage_b == TransitionStage.PRE:
                if dry:
                    return TargetChannel.A
                # B has not started mixing yet so we can still cancel A
                channel_b.clear_transition()
                channel_a.load(channel_a.song)
        if dry:
            return TargetChannel.INVALID

    def queue(self, qd: QueueData, dry: bool = False) -> Optional[MixerStage]:
        """
        Queues the transition. If `dry` the direction of the transition is
        returned without executing the operation.
        """
        channel_a = self.mixer.channels[0]
        stage_a = channel_a.stage()
        channel_b = self.mixer.channels[1]
        stage_b = channel_b.stage()

        song_a = channel_a.song
        song_b = channel_b.song

        if self.stage == MixerStage.INIT_A:
            if song_a is not None and song_b is None and stage_a == \
                    TransitionStage.NONE:
                if dry:
                    return MixerStage.INIT_A
                # Only A is loaded and not playing yet, so we play it and
                # transition from "nothing" immediately
                p = song_a.bar_to_time(qd.selection_src[0])
                q = song_a.bar_to_time(qd.selection_src[1] + 1)
                channel_a.transition_bars = qd.selection_src
                channel_a.transition = create_transition_func(self.mixer,
                    qd.transition_src, p, q, inp=True)
                print(qd)
                channel_a.play(p)
        elif self.stage == MixerStage.A_TO_B:
            if stage_a == TransitionStage.POST and stage_b == \
                    TransitionStage.NONE:
                if dry:
                    return MixerStage.A_TO_B
                # A is playing and B is not, so we transition from A to B
                # and start playing B
                self._apply_transition(qd, channel_a, channel_b)
            elif stage_a == TransitionStage.POST and stage_b == \
                    TransitionStage.POST:
                if dry:
                    return MixerStage.B_TO_A
                # Both A and B are playing and we transitioned from A to B
                # We therefore transition back from B to A
                self._apply_transition(qd, channel_b, channel_a)
                self.stage = MixerStage.B_TO_A
        elif self.stage == MixerStage.B_TO_A:
            if stage_a == TransitionStage.NONE and stage_b == \
                    TransitionStage.POST:
                if dry:
                    return MixerStage.B_TO_A
                # B is playing and A is not, so we transition from B to A
                # and start playing A
                self._apply_transition(qd, channel_b, channel_a)
            elif stage_a == TransitionStage.POST and stage_b == \
                    TransitionStage.POST:
                if dry:
                    return MixerStage.A_TO_B
                # Both A and B are playing and we transitioned from B to A
                # We therefore transition back from A to B
                self._apply_transition(qd, channel_a, channel_b)
                self.stage = MixerStage.A_TO_B
        if dry:
            return MixerStage.INVALID
