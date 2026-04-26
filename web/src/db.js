import Dexie from 'dexie';
import * as pako from 'pako';

if (!window.indexedDB) {
    alert("This page requires IndexedDB to work.\n" +
            "Your browser does not support it. Please upgrade your browser.");
}

async function persist() {
    return await navigator.storage?.persist?.();
}

export const db = new Dexie('jlcparts');
db.version(1).stores({
    settings: 'key',
    components: 'lcsc, category, mfr, *indexWords',
    categories: 'id++,[category+subcategory], subcategory, category'
});
db.version(2).stores({
    settings: 'key',
    files: 'name'
});

const SOURCE_PATH = "data";
const MANIFEST_PATH = `${SOURCE_PATH}/manifest.json`;
const parsedFileCache = new Map();
let manifestCache = undefined;

function dataUrl(name) {
    return `${SOURCE_PATH}/${name}`;
}

function normalizeBinary(data) {
    if (data instanceof ArrayBuffer) {
        return data;
    }
    if (ArrayBuffer.isView(data)) {
        return data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
    }
    return data;
}

function lineObjects(text, callback, checkAbort) {
    const lines = text.split(/\r?\n/);
    let idx = 0;
    for (const line of lines) {
        if (!line) {
            continue;
        }
        if (callback(JSON.parse(line), idx++) === 'abort') {
            return true;
        }
        if (checkAbort?.()) {
            return true;
        }
    }
    return false;
}

async function gunzipToText(buffer) {
    buffer = normalizeBinary(buffer);
    if (window.DecompressionStream && window.TextDecoderStream) {
        const stream = new Blob([buffer]).stream()
            .pipeThrough(new window.DecompressionStream('gzip'))
            .pipeThrough(new window.TextDecoderStream());
        const reader = stream.getReader();
        let text = '';
        try {
            while (true) {
                const { done, value } = await reader.read();
                if (done) {
                    break;
                }
                text += value;
            }
        } finally {
            reader.releaseLock();
        }
        return text;
    }
    return pako.ungzip(new Uint8Array(buffer), { to: 'string' });
}

async function streamJsonLines(name, callback, checkAbort) {
    const buffer = await ensureBinaryFile(name);
    if (window.DecompressionStream && window.TextDecoderStream) {
        const stream = new Blob([buffer]).stream()
            .pipeThrough(new window.DecompressionStream('gzip'))
            .pipeThrough(new window.TextDecoderStream());
        const reader = stream.getReader();
        let chunk = '';
        let idx = 0;
        try {
            while (true) {
                if (checkAbort?.()) {
                    return true;
                }
                const { done, value } = await reader.read();
                if (done) {
                    if (chunk && callback(JSON.parse(chunk), idx++) === 'abort') {
                        return true;
                    }
                    return false;
                }
                chunk += value;
                while (true) {
                    const newline = chunk.indexOf('\n');
                    if (newline === -1) {
                        break;
                    }
                    const line = chunk.slice(0, newline).trim();
                    chunk = chunk.slice(newline + 1);
                    if (!line) {
                        continue;
                    }
                    if (callback(JSON.parse(line), idx++) === 'abort') {
                        return true;
                    }
                    if (checkAbort?.()) {
                        return true;
                    }
                }
            }
        } finally {
            reader.releaseLock();
        }
    }
    return lineObjects(await gunzipToText(buffer), callback, checkAbort);
}

function decodeAttributes(attributeIds, attributeLut) {
    const attributes = {};
    for (const id of attributeIds || []) {
        const entry = attributeLut[id];
        if (!entry) {
            continue;
        }
        attributes[entry[0]] = entry[1];
    }
    return attributes;
}

function decodeComponentRow(row, schema, attributeLut) {
    return {
        lcsc: row[schema.lcsc],
        mfr: row[schema.mfr],
        joints: row[schema.joints],
        description: row[schema.description],
        datasheet: row[schema.datasheet],
        price: row[schema.price],
        img: row[schema.img],
        url: row[schema.url],
        stock: row[schema.stock],
        category: row[schema.subcategory],
        attributes: decodeAttributes(row[schema.attributes], attributeLut),
    };
}

function componentText(component) {
    return (
        component.lcsc + " " +
        component.mfr + " " +
        component.description
    ).toLocaleLowerCase();
}

function splitSearchWords(searchString) {
    return searchString.split(/\s+/)
        .filter(x => x.length > 0)
        .map(x => x.toLocaleLowerCase());
}

function matchesSearch(component, words) {
    if (words.length === 0) {
        return true;
    }
    const text = componentText(component);
    return words.every(word => text.includes(word));
}

export async function fetchJson(path, errorIntro = "Cannot fetch JSON: ") {
    const response = await fetch(path);
    if (!response.ok) {
        throw Error(errorIntro + response.statusText);
    }

    const contentType = response.headers.get('Content-Type') || '';
    try {
        if (contentType.includes("application/json") || path.endsWith(".json")) {
            return await response.json();
        }
        if (contentType.includes("application/gzip") || contentType.includes("application/x-gzip") ||
                path.endsWith(".json.gz")) {
            return JSON.parse(await gunzipToText(await response.arrayBuffer()));
        }
    } catch (error) {
        throw Error(errorIntro + `${error}: ` + path);
    }

    throw Error(errorIntro + `Unsupported response for ${path}: ${contentType}`);
}

async function getSetting(key) {
    return (await db.settings.get(key))?.value;
}

async function setSetting(key, value) {
    await db.settings.put({ key, value });
}

export async function getLocalManifest() {
    if (manifestCache !== undefined) {
        return manifestCache;
    }
    manifestCache = (await getSetting("manifest")) ?? null;
    return manifestCache;
}

async function storeManifest(manifest) {
    manifestCache = manifest;
    await Promise.all([
        setSetting("manifest", manifest),
        setSetting("lastUpdate", manifest.created),
        setSetting("formatVersion", manifest.version),
    ]);
}

async function fetchRemoteManifest() {
    return await fetchJson(MANIFEST_PATH, "Cannot fetch component manifest: ");
}

async function pruneCachedFiles(manifest) {
    const expectedHashes = new Map(
        Object.entries(manifest.files).map(([name, info]) => [name, info.sha256])
    );
    const deletions = [];
    await db.files.each(record => {
        if (expectedHashes.get(record.name) !== record.sha256) {
            parsedFileCache.delete(record.name);
            deletions.push(db.files.delete(record.name));
        }
    });
    await Promise.all(deletions);
}

async function ensureBinaryFile(name) {
    const manifest = await getLocalManifest();
    if (!manifest) {
        throw Error("Component manifest is not cached locally");
    }
    const fileInfo = manifest.files[name];
    if (!fileInfo) {
        throw Error(`Unknown cached file ${name}`);
    }

    const cached = await db.files.get(name);
    if (cached && cached.sha256 === fileInfo.sha256) {
        return normalizeBinary(cached.data);
    }

    const response = await fetch(dataUrl(name));
    if (!response.ok) {
        throw Error(`Cannot fetch ${name}: ${response.statusText}`);
    }
    const data = await response.arrayBuffer();
    await db.files.put({
        name,
        sha256: fileInfo.sha256,
        data
    });
    parsedFileCache.delete(name);
    return data;
}

async function ensureJsonFile(name) {
    if (parsedFileCache.has(name)) {
        return await parsedFileCache.get(name);
    }
    const promise = (async () => {
        return JSON.parse(await gunzipToText(await ensureBinaryFile(name)));
    })();
    parsedFileCache.set(name, promise);
    try {
        return await promise;
    } catch (error) {
        parsedFileCache.delete(name);
        throw error;
    }
}

export async function getCategories() {
    return (await getLocalManifest())?.categories ?? [];
}

export async function hasLocalComponentLibrary() {
    return (await getLocalManifest()) !== null;
}

export async function getComponentCount() {
    return (await getLocalManifest())?.totalComponents ?? 0;
}

export async function updateComponentLibrary(report) {
    await persist();
    const progress = {};
    const updateProgress = (name, status) => {
        progress[name] = status;
        report(progress);
    };

    updateProgress("Manifest", ["Fetching", false]);
    const manifest = await fetchRemoteManifest();
    updateProgress("Manifest", ["Fetched", true]);

    updateProgress("Cache", ["Pruning stale files", false]);
    await pruneCachedFiles(manifest);
    updateProgress("Cache", ["Ready", true]);

    await storeManifest(manifest);

    updateProgress("Metadata", ["Caching attributes", false]);
    await ensureJsonFile(manifest.attributesLut);
    updateProgress("Metadata", ["Ready", true]);
}

export async function checkForComponentLibraryUpdate() {
    try {
        const [localManifest, remoteManifest] = await Promise.all([
            getLocalManifest(),
            fetchRemoteManifest()
        ]);
        if (!localManifest) {
            return true;
        }
        return localManifest.version !== remoteManifest.version ||
            localManifest.created !== remoteManifest.created;
    } catch (error) {
        console.warn(error);
        return false;
    }
}

export async function queryComponents({ categoryIds, allCategories, searchString, checkAbort }) {
    const manifest = await getLocalManifest();
    if (!manifest) {
        return [];
    }

    if (allCategories && searchString.trim().length < 3) {
        return [];
    }

    const selectedCategories = new Set(categoryIds || []);
    const shardNames = [];
    for (const category of manifest.categories) {
        if (allCategories || selectedCategories.has(category.id)) {
            shardNames.push(...category.shards);
        }
    }
    if (shardNames.length === 0) {
        return [];
    }

    const attributeLut = await ensureJsonFile(manifest.attributesLut);
    const words = splitSearchWords(searchString);
    const results = [];

    for (const shardName of Array.from(new Set(shardNames))) {
        let schema = null;
        const aborted = await streamJsonLines(shardName, (row, idx) => {
            if (idx === 0) {
                schema = row;
                return;
            }
            const component = decodeComponentRow(row, schema, attributeLut);
            if (matchesSearch(component, words)) {
                results.push(component);
            }
            if (checkAbort?.()) {
                return 'abort';
            }
        }, checkAbort);
        if (aborted) {
            return null;
        }
    }

    return checkAbort?.() ? null : results;
}

function lookupFileForLcsc(manifest, lcsc) {
    const numeric = Number.parseInt(lcsc.slice(1), 10);
    if (!Number.isFinite(numeric)) {
        return null;
    }
    const bucket = Math.floor(numeric / manifest.lookupBucketSize);
    return manifest.lookupBuckets[String(bucket)] ?? null;
}

export async function getComponentByLcsc(lcsc) {
    const manifest = await getLocalManifest();
    if (!manifest) {
        return undefined;
    }

    const lookupFile = lookupFileForLcsc(manifest, lcsc);
    if (!lookupFile) {
        return undefined;
    }

    const lookup = await ensureJsonFile(lookupFile);
    const shardName = lookup[lcsc];
    if (!shardName) {
        return undefined;
    }

    const attributeLut = await ensureJsonFile(manifest.attributesLut);
    let schema = null;
    let found = undefined;
    await streamJsonLines(shardName, (row, idx) => {
        if (idx === 0) {
            schema = row;
            return;
        }
        if (row[schema.lcsc] !== lcsc) {
            return;
        }
        found = decodeComponentRow(row, schema, attributeLut);
        return 'abort';
    });
    return found;
}
