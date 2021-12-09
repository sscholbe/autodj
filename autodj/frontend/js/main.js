import {Channel} from './modules/channel.js';

window.channels = [new Channel(0), new Channel(1)];

let lastStatus = null;
let transitions = {};

/**
 * Updates the general UI after a status update.
 */
function updateUI() {
    $('#queue').prop('disabled',
        lastStatus.actions.queue === 'INVALID' || !queue(true));
    $('#cancel').prop('disabled', lastStatus.actions.cancel === 'INVALID');
    if ($('#bpm')[0] !== document.activeElement) {
        $('#bpm').val(lastStatus.bpm);
    }
}

/**
 * Queues the transition. If `dry`, nothing is actually queued but
 * instead returns whether queueing is possible.
 */
function queue(dry) {
    let sel_A = null, sel_B = null;
    if (channels[0].region !== null) {
        sel_A = [channels[0].region[0] - 1000000 / 25,
            channels[0].region[1] - 1000000 / 25];
    }
    if (channels[1].region !== null) {
        sel_B = [channels[1].region[0] - 1000000 / 25,
            channels[1].region[1] - 1000000 / 25];
    }
    if ((lastStatus.actions.queue === 'INIT_A' && sel_A !== null) ||
        (lastStatus.actions.queue !== 'INIT_A' && sel_A !== null && sel_B !==
            null)) {
        if (dry) {
            return true;
        }
        sck.emit('mixer_queue', transitions[$('#song-transition-0').val()],
            transitions[$('#song-transition-1').val()], sel_A, sel_B);
        channels[0].clearSelection();
        channels[1].clearSelection();
    }
    if (dry) {
        return false;
    }
}

window.onload = (e) => {
    window.sck = io();

    sck.on('connect', () => {
        console.log('Connected.');
    });
    sck.on('disconnect', () => {
        console.log('Disconnected.');
    });

    $('#queue').on('click', () => {
        queue(false);
    });
    $('#cancel').on('click', () => {
        sck.emit('mixer_cancel');
    });

    // Get a status update twice a second
    window.setInterval((e) => {
        if (!sck.connected) {
            return;
        }
        sck.emit('mixer_status', (status) => {
            lastStatus = status;
            for (let i in status.channels) {
                channels[i].update(status);
            }
            updateUI();
        });
    }, 500);

    // Get all available songs
    sck.emit('song_list', (songs) => {
        let table = $('#songs')[0];
        songs.sort((a, b) => {
            return a.title.localeCompare(b.title);
        });
        songs.forEach(song => {
            let row = table.insertRow();
            $(row).data('file', song.file);
            let artist = row.insertCell(0);
            artist.innerText = song.artist;
            let title = row.insertCell(1);
            title.innerText = song.title;
            $(row).on('click', () => {
                sck.emit('mixer_load', $(row).data('file'));
            });
        });
    });

    // Get all available transitions
    sck.emit('transition_list', (trans) => {
        trans.forEach(t => {
            $('select').append(new Option(t.name, t.file));
            transitions[t.file] = t.fx;
        });
        console.log(transitions);
    });

    // Update the cursor more frequently than the status update by extrapolating
    window.setInterval((e) => {
        for (let c of channels) {
            c.updateCursor();
        }
        if (lastStatus !== null) {
            updateUI();
        }
    }, 100);

    // Update search bar
    $('#song-query').on('keyup', function () {
        let value = $(this).val().toLowerCase();
        $('#songs tr:not(.header)').filter(function () {
            $(this).toggle($(this).text().toLowerCase().indexOf(value) > -1);
        });
    });

    $('#bpm').on('change', function () {
        sck.emit('mixer_bpm', $(this).val());
    });
};
