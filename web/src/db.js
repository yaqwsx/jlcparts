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
db.version(1).stores({
    settings: 'key',
    components: 'lcsc, category, mfr, *indexWords',
    categories: 'id++,[category+subcategory], subcategory, category'
});

function extractCategoryKey(category) {
    return category.id;
}

const SOURCE_PATH = "data";

// Updates the whole component library, takes a callback for reporting progress:
// the progress is given as list of tuples (task, [statusMessage, finished])
export async function updateComponentLibrary(report) {
    await persist();
    report({"Component index": ["fetching", false]})
    let index = await fetchJson(`${SOURCE_PATH}/index.json`,
        "Cannot fetch categories index: ");
    let progress = {}
    let updateProgress = (name, status) => {
        progress[name] = status;
        report(progress);
    }
    db.settings.put({key: "lastDbUpdate", value: index.created})
    await updateCategories(index.categories,
        // onNew
        async (cName, sName, attr) => {
            let name = cName + ": " + sName;
            updateProgress(name, ["Adding components 1/2", false]);
            let category = await addCategory(cName, sName, attr);
            updateProgress(name, ["Updating stock 2/2", false]);
            await updateStock(category);
            updateProgress(name, ["Added", true]);
            return category;
        },
        // onUpdateExisting
        async (category, attr) => {
            let cName = category.category;
            let sName = category.subcategory;
            let name = cName + ": " + sName;
            updateProgress(name, ["Updating components 1/2", false]);
            await deleteCategory(category);
            let newCategory = await addCategory(cName, sName, attr);
            updateProgress(name, ["Updating stock 2/2", false]);
            await updateStock(newCategory);
            updateProgress(name, ["Update finished", true]);
            return newCategory;
        },
        // onUpdateStock
        async (category, _) => {
            let cName = category.category;
            let sName = category.subcategory;
            let name = cName + ": " + sName;
            updateProgress(name, ["Updating stock 1/1", false]);
            await updateStock(category);
            updateProgress(name, ["Stock updated", true]);
            return category;
        },
        // onExcessive
        async category => {
            let cName = category.category;
            let sName = category.subcategory;
            let name = cName + ": " + sName;
            updateProgress(name, ["Removing category", false]);
            await deleteCategory(category);
            updateProgress(name, ["Removed", true]);
        }
    );
}

// Check if the component library can be updated
export async function checkForComponentLibraryUpdate() {
    let index = await fetchJson(`${SOURCE_PATH}/index.json`,
        "Cannot fetch categories index: ");
    let updateAvailable = false;
    let onUpdate = (category) => { updateAvailable = true; return category; }
    await updateCategories(index.categories,
        // onNew
        onUpdate,
        // onUpdateExisting
        onUpdate,
        // onUpdateStock
        onUpdate,
        // onExcessive
        onUpdate
    );
    return updateAvailable;
}

// contains data from all-data.tar.gz
let allData = {
    filesPromise: null,
    fetchSingle: async function(url) {  // fetchs a single chunk of the combined files
        try {
            const resp = await fetch(url);
            if (resp.status === 200) {
                const compressedData = await resp.arrayBuffer();
                const data = pako.ungzip(compressedData);
                const files = await untar(data.buffer);                            
                const fileData = {};
                for (const file of files) {
                    fileData[`${SOURCE_PATH}/${file.name}`.toLowerCase()] = file.buffer;
                }
                return fileData;
            } else {
                return {};  // failed to download/unpack
            }
        } catch (ex) {
            console.log('Failed to fetch all-data.tar.gz', ex);
            return {};  // failed to download/unpack
        }
    },
    fetch: async function(path, expectJson) {  // returns promise; resolves as data on success, and null on failure
        return new Promise(async (resolve, reject) => {
            if (this.filesPromise === null) {
                this.filesPromise = new Promise(async (resolve, reject) => {
                    try {
                        const ChunkCount = 2;
                        let data = {};
                        for (let i = 0; i < ChunkCount; i++) {
                            Object.assign(data, await this.fetchSingle(`${SOURCE_PATH}/all-data-${i + 1}.tar.gz`));
                        }

                        if (Object.keys(data).length > 0) {
                            resolve(data);
                        } else {
                            resolve(null);
                        }
                    } catch(ex) {
                        resolve(null);
                    }                
                });
            }

            const files = await this.filesPromise;

            if (files) {
                const fileData = files[path.toLowerCase()];
                if (fileData){
                    if (expectJson) {
                        if (path.slice(-3) === '.gz') {
                            resolve(JSON.parse(pako.ungzip(fileData, {to: 'string'})));
                        } else {
                            const decoder = new TextDecoder();
                            resolve(JSON.parse(decoder.decode(fileData)));
                        }
                    } else {
                        const decoder = new TextDecoder();
                        resolve(decoder.decode(fileData));
                    }
                } else {
                    //reject(`${path} not found`);
                    resolve(null);
                }
            } else {
                //reject('All data not available');
                resolve(null);
            }
        });
    }
}; 

// Fetch a JSON. If error occures,
export async function fetchJson(path, errorIntro) {
    if (path.indexOf('/index.json') < 0) {
        // try from all data combined file first
        const data = await allData.fetch(path, true);
        if (data) {
            return data;
        }
    }

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

async function fetchText(path, errorIntro) {
    // try from all data combined file first
    const data = await allData.fetch(path, false);
    if (data) {
        return data;
    }

    let response = await fetch(path);
    if (!response.ok) {
        throw Error(errorIntro + response.statusText);
    }
    return await response.text();
}

// Update categories. Fetched categoryIndex and 3 callback are supplied to
// perform the update.
async function updateCategories(categoryIndex, onNew, onUpdateExisting, onUpdateStock, onExcessive) {
    let updates = [];
    let usedCategories = new Set();
    for (const [categoryName, subcategories] of Object.entries(categoryIndex)) {
        for ( const [subcategoryName, attributes] of Object.entries(subcategories)) {
            let action = db.categories
                .where({category: categoryName, subcategory: subcategoryName})
                .first(async category => {
                    if (category === undefined) {
                        category = await onNew(categoryName, subcategoryName, attributes);
                    } else if (attributes.datahash !== category.datahash ||
                               attributes.sourcename !== category.sourcename)
                    {
                        category = await onUpdateExisting(category, attributes);
                    } else if (attributes.stockhash !== category.stockhash) {
                        category = await onUpdateStock(category);
                    }

                    if (category) {
                        usedCategories.add(extractCategoryKey(category));
                    }
                });
            updates.push(action);
        }
    }
    await Promise.all(updates);
    await db.categories.each(category => {
        if (usedCategories.has(extractCategoryKey(category))) {
            return;
        }
        onExcessive(category);
    });
}

// Takes an array containing schema and an array of values and turns them into
// dictionary
function restoreObject(schema, source) {
    return schema.reduce((obj, k, i) => {
        obj[k] = source[i];
        return obj;
    }, {});
}

// Takes a JSON fetched from server and adds them to the database for the
// corresponding category
function addComponents(category, components) {
    let schema = components.schema;
    let cObjects = components.components.map(src => {
        let obj = restoreObject(schema, src);
        obj.category = extractCategoryKey(category);
        return obj;
    });
    return db.components.bulkPut(cObjects);
}

// Add a single category and fetch all of its components
async function addCategory(categoryName, subcategoryName, attributes) {
    let components = await fetchJson(`${SOURCE_PATH}/${attributes.sourcename}.json.gz`,
        `Cannot fetch components for category ${categoryName}: ${subcategoryName}: `);
    return db.transaction("rw", db.categories, db.components, async () => {
        let key = await db.categories.put({
            category: categoryName,
            subcategory: subcategoryName,
            sourcename: attributes.sourcename,
            datahash: attributes.datahash,
            stockhash: attributes.stockhash
        });
        let category = await db.categories.get(key);
        await addComponents(category, components);
        return category;
    });
}

// Fetch and update stock
async function updateStock(category) {
    let stock = await fetchJson(`${SOURCE_PATH}/${category.sourcename}.stock.json`,
        `Cannot fetch stock for category ${category.category}: ${category.subcategory}: `);
    await db.components.where({category: category.id}).modify(component =>{
        component.stock = stock[component.lcsc];
    });
    // await db.transaction("rw", db.components, async () => {
    //     let actions = [];
    //     for (const [component, stockVal] of Object.entries(stock)) {
    //         actions.push(db.components.update(component, {"stock": stockVal }));
    //     }
    //     await Promise.all(actions);
    // });
    let hash = await fetchText(`${SOURCE_PATH}/${category.sourcename}.stock.json.sha256`,
        `Cannot fetch stock hash for category ${category.category}: ${category.subcategory}: `);
    await db.categories.update(extractCategoryKey(category), {stockhash: hash});
}

// Delete given category and all of its components
async function deleteCategory(category) {
    await db.transaction("rw", db.components, db.categories, async () => {
        await db.components.where({category: extractCategoryKey(category)}).delete();
        await db.categories.delete(extractCategoryKey(category));
    });
}


// See https://stackoverflow.com/questions/64114482/aborting-dexie-js-query
// export function cancellableDexieQuery(includedTables, querierFunction) {
//     let tx = null;
//     let cancelled = false;
//     const promise = db.transaction('r', includedTables, () => {
//         if (cancelled)
//             throw new Dexie.AbortError('Query was cancelled');
//         tx = Dexie.currentTransaction;
//         return querierFunction();
//     });
//     return [
//         promise,
//         () => {
//             cancelled = true; // In case transaction hasn't been started yet.
//             if (tx)
//                 tx.abort(); // If started, abort it.
//             tx = null; // Avoid calling abort twice.
//         }
//     ];
// }