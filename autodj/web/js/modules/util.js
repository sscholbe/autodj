/**
 * Formats seconds into the time format H:SS.
 */
export function formatTime(secs) {
    let out = '';
    if (secs < 0) {
        out += '-';
        secs = -secs;
    }
    let ds = Math.floor(secs % 1 * 10);
    let s = Math.floor(secs) % 60;
    let m = Math.floor(secs / 60);
    /*if(m < 10) {
     out += '0';
     }*/
    out += m;
    out += ':';
    if (s < 10) {
        out += '0';
    }
    out += s;
    //out += '.';
    //out += ds;
    return out;
}

/**
 * Converts a byte array to a blob.
 */
export function getBlob(arr, type) {
    var view = new Uint8Array(arr);
    var blob = new Blob([view], {type: type});
    return URL.createObjectURL(blob);
}
