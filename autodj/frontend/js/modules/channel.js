import {formatTime, getBlob} from './util.js';

const OFF = 1_000_000;

export class Channel {
    /**
     * Gets the control component of the channel by its ID.
     */
    cnt(name) {
        return $(`#${name}-${this.id}`)[0];
    }

    /**
     * Updates an SVG element by its ID.
     */
    upd(id, v) {
        let el = this.svg.getElementById(id);
        if (el === null) {
            //console.log('Could not find SVG element ' + id);
            return;
        }
        for (let k in v) {
            el.setAttribute(k, v[k]);
        }
        return el;
    }

    constructor(id) {
        this.id = id;
        this.scrollLock = false;
        this.ignoreScroll = false;
        this.svg = this.cnt('sausage');

        this.svg.onpointermove = (e) => {
            if (this.selection.active) {
                this.selection.to = Math.floor(e.offsetX / 25);
                this.updateSelection();
            }
        };
        this.svg.onpointerdown = (e) => {
            this.selection.active = true;
            this.selection.from =
                this.selection.to = Math.floor(e.offsetX / 25);
            this.updateSelection();
        };
        this.svg.onpointerup = this.svg.onpointerleave = (e) => {
            this.selection.active = false;
            this.updateSelection();
        };
        this.svg.parentElement.onscroll = (e) => {
            if (!this.ignoreScroll) {
                this.scrollLock = false;
            }
            this.ignoreScroll = false;
        };

        this.song = null;
        this.channel = null;
        this.status = null;

        this.selection = {
            from: null, to: null, active: false
        };
        this.region = null;

        this.svg.parentElement.scrollTo(OFF, 0);

        this.last_file = undefined;


    }

    setup() {
        if (this.channel.file !== null) {
            sck.emit('song_info', this.channel.file, (song) => {
                this.song = song;
                this.updateSong();
            });
        } else {
            this.song = null;
            this.updateSong();
        }
    }


    clearSelection() {
        this.selection.from = null;
        this.selection.to = null;
        this.selection.active = false;
        this.updateSelection();
    }

    updateSong() {
        this.selection.from = null;
        this.selection.to = null;
        this.selection.active = false;
        this.region = null;
        this.upd('selection', {
            visibility: 'hidden'
        });

        $(this.cnt('song-transition')).toggle(this.song !== null);

        if (this.song === null) {
            this.upd('sausage', {width: 0});
            this.upd('cursor', {visibility: 'hidden'});
            return;
        }

        this.cnt('song-artist').innerText = this.song.artist;
        this.cnt('song-title').innerText = this.song.title;
        this.cnt('song-bpm').innerText = this.song.bpm + ' BPM';
        this.cnt('song-length').innerText = formatTime(this.song.length);

        this.t2p = 1 / ((60 / this.song.bpm) / 25 * 4);
        this.upd('sausage', {
            x: -this.song.offset * this.t2p + OFF,
            width: this.song.length * this.t2p,
            href: getBlob(this.song.wave_diagram, 'image/svg+xml')
        });

        this.upd('cursor', {
            visibility: 'visible'
        });
    }

    updateSelection() {
        if (this.song === null || this.selection.from === null ||
            this.selection.to === null) {
            this.upd('selection', {
                visibility: 'hidden'
            });
            return;
        }

        let from = Math.min(this.selection.from, this.selection.to);
        let to = Math.max(this.selection.from, this.selection.to);
        let len = to - from + 1;

        if (len >= 2 && len <= 8) {
            len = Math.ceil(len / 2) * 2;
        } else if (len > 8) {
            len = Math.ceil(len / 4) * 4;
        }

        if (this.selection.from <= this.selection.to) {
            to = from + len - 1;
        } else {
            from = to - len + 1;
        }

        this.region = [from, to];

        this.upd('selection', {
            visibility: 'visible', x: from * 25, width: len * 25
        });
    }

    updateCursor() {
        if (this.song !== null) {
            let time = this.channel.time +
                (new Date().getTime() / 1000 - this.status.stamp);
            // - this.status.stamp) * (this.status.bpm / this.song.bpm) - 1;
            this.upd('cursor', {x: OFF + time * this.t2p - 15});
            this.cnt('song-time').innerText = formatTime(time);

            if (this.scrollLock) {
                this.svg.parentElement.scrollTo(1000000 + time * this.t2p - 30,
                    0);
            }
        }
        if (this.channel !== null) {
            this.upd('cursor', {opacity: this.channel.is_playing * 1});
        }
    }

    update(status) {
        this.status = status;
        this.channel = status.channels[this.id];
        if (this.channel.file !== this.last_file) {
            this.last_file = this.channel.file;
            this.setup();
        }

        let queued = this.channel.transition_bars;
        if (queued !== null) {
            this.upd('queued', {
                visibility: 'visible',
                x: queued[0] * 25 + 1000000,
                width: (queued[1] - queued[0] + 1) * 25
            });
        } else {
            this.upd('queued', {
                visibility: 'hidden'
            });
        }

        if (status.master === ['A', 'B'][this.id]) {
            this.svg.setAttribute('opacity', 1);
            this.cnt('control').style.setProperty('opacity', 1);
        } else {
            this.svg.setAttribute('opacity', 0.75);
            this.cnt('control').style.setProperty('opacity', 0.75);
        }
    }
}
