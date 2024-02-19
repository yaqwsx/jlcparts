import Dexie from 'dexie';
import * as pako from 'pako';
import untar from "js-untar";

if (!window.indexedDB) {
    alert("This page requires IndexedDB to work.\n" +
        "Your browser does not support it. Please upgrade your browser.");
}

async function persist() {
    return await navigator.storage?.persist?.();
}

export const db = new Dexie('jlcparts');
db.version(2).stores({
    settings: 'key',
    jsonlines: 'name'
});


const SOURCE_PATH = "data";
const dbWebPath = `${SOURCE_PATH}/all.jsonlines.tar`;

let jsonlines = {}; // copy of the database in memory so we only access the database once (doesn't really matter - it would be pretty fast anyway)
async function getJsonlines() {
    if (Object.keys(jsonlines).length === 0) {
        (await db.jsonlines.toArray()).forEach(obj => {
            jsonlines[obj.name] = obj.compressedData
        });
    }
    return jsonlines;
}

export async function unpackLinesAsArray(name) {
    let arr = [];
    await unpackAndProcessLines(name, (val, idx) => arr.push(val));
    return arr;
}

async function yieldExec() {
    return new Promise((resolve, reject) => {
        setTimeout(() => resolve(), 0);
    });
}

export async function unpackAndProcessLines(name, callback, checkAbort) {
    await getJsonlines();

    if (jsonlines[name] === undefined) {
        return;
    }

    let time = new Date().getTime();

    if (!window.DecompressionStream) {
        console.error("DecompressionStream is not supported in this environment.");
        return;
    }

    // Step 1: Create a DecompressionStream for gzip
    const decompressionStream = new window.DecompressionStream('gzip');

    // Convert the ArrayBuffer to a ReadableStream
    const inputStream = new ReadableStream({
        start(controller) {
            controller.enqueue(jsonlines[name]);
            controller.close();
        },
    });

    // Pipe the input stream through the decompression stream
    const decompressedStream = inputStream.pipeThrough(decompressionStream);

    // Step 2: Convert the stream into text
    const textStream = decompressedStream.pipeThrough(new window.TextDecoderStream());

    // Step 3: Create a reader to read the stream line by line
    const reader = textStream.getReader();
    let chunk = '';
    let idx = 0;
    let lastYield = new Date().getTime();

    try {
        while (true) {

            // Periodically allow UI to do what it needs to, including updating any abort flag.
            // This does slow down the this function a variable amount (could be <100ms, could be a few seconds) 
            const now = new Date().getTime();
            if (now - lastYield > 300) {
                await yieldExec();
                console.log('yielded for ', new Date().getTime() - now, 'ms');
                lastYield = new Date().getTime();

                if (checkAbort && checkAbort()) {   // check abort flag
                    break;
                }
            }


            const { done, value } = await reader.read();
            if (done) {
                // If there's any remaining line, process it as well -- should never happen
                if (chunk) {
                    callback(chunk, idx++);
                }
                break;
            }

            // Decode the chunk to a string
            chunk += value;

            let start = 0;
            while (true) {
                let pos = chunk.indexOf('\n', start);
                if (pos >= 0) {
                    if (callback(chunk.slice(start, pos), idx++) === 'abort') {
                        break;  // quit early
                    }
                    start = pos + 1;
                } else {
                    chunk = chunk.slice(start); // dump everything that we've processed
                    break;  // no more lines in our chunk
                }
            }
        }

        console.log(`Time to gunzip & segment ${name}: ${new Date().getTime() - time}`);
    } finally {
        reader.releaseLock();
    }
}

// Updates the whole component library, takes a callback for reporting progress:
// the progress is given as list of tuples (task, [statusMessage, finished])
export async function updateComponentLibrary(report) {
    await persist();

    let progress = {};
    let updateProgress = (name, status) => {
        progress[name] = status;
        report(progress);
    };

    // get new db files
    const downloadingTitle = `Downloading ${dbWebPath}`;
    updateProgress(downloadingTitle, ["In progress", false]);
    const resp = await fetch(dbWebPath);
    if (resp.status === 200) {
        const data = await resp.arrayBuffer();
        updateProgress(downloadingTitle, ["OK", false]);

        const untarTitle = `Updating database`;
        updateProgress(untarTitle, ["In progress", false]);

        const files = await untar(data);
        for (const file of files) {
            const basename = file.name.split('.')[0];
            let result = await db.jsonlines.put({ name: basename, compressedData: file.buffer });
            console.log(result);

            // store copy in memory (we can load from indexeddb on startup)
            jsonlines[basename] = file.buffer;
        }

        updateProgress(untarTitle, ["OK", true]);

        db.settings.put({
            key: "lastUpdate",
            value: resp.headers.get('Last-Modified') || new Date().toUTCString()
        });

    } else {
        updateProgress(downloadingTitle, ["Download failed", false]);
    }
}

// Check if the component library can be updated
export async function checkForComponentLibraryUpdate() {
    let lastUpdate = (await db.settings.get("lastUpdate"))?.value || new Date(0).toUTCString();

    let head = await fetch(dbWebPath, {
        method: 'HEAD',
        headers: {
            'If-Modified-Since': lastUpdate
        }
    });

    let updateAvailable = head.status === 200;   // 304 if not modified; any error means we don't know if there's an update
    return updateAvailable;
}

// Fetch a JSON. If error occures,
export async function fetchJson(path, errorIntro) {
    let response = await fetch(path);
    if (!response.ok) {
        throw Error(errorIntro + response.statusText);
    }

    let contentType = response.headers.get('Content-Type');
    if (!contentType) {
        throw Error(errorIntro + 'Missing "Content-Type" header for: ' + path);
    }

    try {
        if (contentType.includes("application/json")) {
            return await response.json();
        }
        if (contentType.includes("application/gzip")) {
            let data = await response.arrayBuffer();
            let text = pako.ungzip(data, { to: 'string' });
            return JSON.parse(text);
        }
    }
    catch (error) {
        throw Error(errorIntro + `${error}: ` + path);
    }

    throw Error(errorIntro + `Response is not a (compressed) JSON, but ${contentType}: ` + path);
}
