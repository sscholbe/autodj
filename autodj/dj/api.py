import glob
import json
import mimetypes
import os
import time
from typing import List

import eventlet
import socketio

from autodj.dj.audio import AudioFile
from autodj.dj.channel import TransitionDef
from autodj.dj.fsm import QueueData, MixerStage
from autodj.dj.mixer import Mixer
from autodj.dj.song import Song, get_artist_and_title

mixer: Mixer = None

sio = socketio.Server()


def start_api(mix):
    """
    Starts the web server and API.
    """
    global mixer
    mixer = mix

    static = {}
    for root, dirs, files in os.walk('web'):
        for file in files:
            path = os.path.join(root, file)
            static['/' + os.path.join(*(path.split(os.path.sep)[1:]))] = {
                'content_type': mimetypes.guess_type(path)[0], 'filename': path}

    app = socketio.WSGIApp(sio, static_files=static)
    eventlet.wsgi.server(eventlet.listen(('', 5000)), app, log_output=False)


################################################################################
# Transition management

def _invert_transition(trans: TransitionDef) -> TransitionDef:
    """
    Converts an "in" transition into an "out" transition and vice versa.
    """
    res = {}
    for fx, points in trans.items():
        res[fx] = [[1 - p[0], p[1]] for p in points]
    return res


@sio.event
def transition_list(sid) -> List[dict]:
    """
    Returns all transitions.
    """
    res = []
    for file in glob.glob('data/transitions/*.json'):
        with open(file) as j:
            js = json.load(j)
            js['file'] = file
            res.append(js)
    return res


################################################################################
# Song management

@sio.event
def song_list(sid) -> List[dict]:
    """
    Returns a list of all songs including their artist and title.
    """
    files = []
    for ext in ['*.wav', '*.mp3', '*.mp4']:
        files.extend(glob.glob(os.path.join('data/songs', ext)))
    songs = []
    for f in files:
        artist, title = get_artist_and_title(f)
        songs.append({'file': f, 'artist': artist, 'title': title})
    return songs


@sio.event
def song_info(sid, file: str) -> dict:
    """
    Returns detailed information about a song.
    """
    with mixer.lock:
        # Try to find song in the channels first
        song = None
        for channel in mixer.channels:
            if channel.song is not None and channel.song.file == file:
                song = channel.song

        # Otherwise load it
        if song is None:
            song = Song(file)

        return {'file': song.file, 'artist': song.artist, 'title': song.title,
                'bpm': song.bpm, 'offset': song.offset / AudioFile.SAMPLE_RATE,
                'length': song.length / AudioFile.SAMPLE_RATE,
                'wave_diagram': song.wave_diagram}


################################################################################
# Mixer management

@sio.event
def mixer_bpm(sid, bpm: str):
    """
    Sets the global BPM.
    """
    mixer.global_bpm = int(bpm)


@sio.event
def mixer_status(sid) -> dict:
    """
    Returns the global state of the mixer.
    """
    channels = []
    with mixer.lock:
        for channel in mixer.channels:
            channels.append({'time': channel.time,
                             'file': channel.song.file if channel.song is not
                                                          None else None,
                             'is_playing': channel.is_playing,
                             'transition_bars': channel.transition_bars})

    return {'time': mixer.global_time, 'bpm': mixer.global_bpm,
            'channels': channels,
            'actions': {'load': mixer.fsm.load(None, dry=True).name,
                        'cancel': mixer.fsm.cancel(dry=True).name,
                        'queue': mixer.fsm.queue(None, dry=True).name},
            'stage': mixer.fsm.stage.name, 'stamp': time.time(),
            'master': mixer.fsm.get_master_channel().name}


@sio.event
def mixer_load(sid, file: str):
    """
    Loads a song into the suitable channel.
    """
    with mixer.lock:
        mixer.fsm.load(file)


@sio.event
def mixer_cancel(sid):
    """
    Cancels the current transition.
    """
    with mixer.lock:
        mixer.fsm.cancel()


@sio.event
def mixer_queue(sid, a_trans: TransitionDef, b_trans: TransitionDef,
        a_sel: List[int], b_sel: List[int]):
    """
    Queues a transition.
    """
    with mixer.lock:
        dir = mixer.fsm.queue(None, dry=True)
        if dir == MixerStage.B_TO_A:
            qd = QueueData(_invert_transition(b_trans), a_trans, b_sel, a_sel)
        elif dir == MixerStage.A_TO_B:
            qd = QueueData(_invert_transition(a_trans), b_trans, a_sel, b_sel)
        else:
            qd = QueueData(a_trans, b_trans, a_sel, b_sel)
        mixer.fsm.queue(qd)
