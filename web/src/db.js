import Dexie from 'dexie';

async function persist() {
return await navigator.storage && navigator.storage.persist &&
    navigator.storage.persist();
}

export const db = new Dexie('jlcparts');
db.version(1).stores({
    settings: 'key',
    components: 'lcsc, category, mfr, *indexWords',
    categories: 'id++,[category+subcategory], subcategory, category'
});

function extractCategoryKey(category) {
    return category["id"];
}

const SOURCE_PATH = "data";

// Updates the whole component library, takes a callback for reporting progress:
// the progress is given as list of tuples (task, status)
export async function updateComponentLibrary(report) {
    await persist();
    report({"Component index": "fetching"})
    let index = await fetchJson(`${SOURCE_PATH}/index.json`,
        "Cannot fetch categories index: ");
    let progress = {}
    let updateProgress = (name, status) => {
        progress[name] = status;
        report(progress);
    }
    await updateCategories(index,
        // onNew
        async (cName, sName, attr) => {
            let name = cName + ": " + sName;
            updateProgress(name, "Updating components (new) 1/2");
            let category = await addCategory(cName, sName, attr);
            updateProgress(name, "Updating stock (new) 2/2");
            await updateStock(category);
            updateProgress(name, "Finished (new)");
            return category;
        },
        // onUpdateExisting
        async (category, attr) => {
            let cName = category["category"];
            let sName = category["subcategory"];
            let name = cName + ": " + sName;
            updateProgress(name, "Updating components 1/2");
            await deleteCategory(category);
            let newCategory = await addCategory(cName, sName, attr);
            updateProgress(name, "Updating stock 2/2");
            await updateStock(newCategory);
            updateProgress(name, "Finished (updateExisting)");
            return newCategory;
        },
        // onUpdateStock
        async (category, _) => {
            let cName = category["category"];
            let sName = category["subcategory"];
            let name = cName + ": " + sName;
            updateProgress(name, "Updating stock 1/1");
            await updateStock(category);
            updateProgress(name, "Finished (stock update)");
            return category;
        },
        // onExcessive
        async (category) => {
            let cName = category["category"];
            let sName = category["subcategory"];
            let name = cName + ": " + sName;
            updateProgress(name, "Removing category");
            await deleteCategory(category);
            updateProgress(name, "Removed");
        }
    );
    updateProgress("All", "Finished");
}

// Check if the component library can be updated
export async function checkForComponentLibraryUpdate() {
    let index = await fetchJson(`${SOURCE_PATH}/index.json`,
        "Cannot fetch categories index: ");
    let updateAvailable = false;
    let onUpdate = (category) => { updateAvailable = true; return category; }
    await updateCategories(index,
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

// Fetch a JSON. If error occures,
async function fetchJson(path, errorIntro) {
    let response = await fetch(path);
    if (!response.ok) {
        throw Error(errorIntro + response.statusText);
    }
    let contentType = response.headers.get('Content-Type');
    if (!contentType || contentType.indexOf("application/json") === -1) {
        throw Error(errorIntro + `Response is not JSON, but ${contentType}: ` + path);
    }
    return await response.json();
}

async function fetchText(path, errorIntro) {
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
                .where({"category": categoryName, "subcategory": subcategoryName})
                .first(async category => {
                    if (category === undefined) {
                        category = await onNew(categoryName, subcategoryName, attributes);
                    } else if (attributes["datahash"] !== category["datahash"] ||
                               attributes["sourcename"] !== category["sourcename"])
                    {
                        category = await onUpdateExisting(category, attributes);
                    } else if (attributes["stockhash"] !== category["stockhash"]) {
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
    const all = await db.categories.toArray();
    await Promise.all(all.map(async category => {
        if (usedCategories.has(extractCategoryKey(category))) {
            return;
        }
        onExcessive(category);
    }));
}

// Takes an array containing schema and an array of values and turns them into
// dictionary
function restoreObject(schema, source) {
    return schema.reduce((obj, k, i) => ({...obj, [k]: source[i] }), {})
}

// Takes a JSON fetched from server and adds them to the database for the
// corresponding category
async function addComponents(category, components) {
    let schema = components["schema"];
    let cObjects = components["components"].map(src => {
        let obj = restoreObject(schema, src);
        obj["category"] = extractCategoryKey(category);
        return obj;
    });
    await db.components.bulkPut(cObjects);
}

// Add a single category and fetch all of its components
async function addCategory(categoryName, subcategoryName, attributes) {
    let components = await fetchJson(`${SOURCE_PATH}/${attributes["sourcename"]}.json`,
        `Cannot fetch components for category ${categoryName}: ${subcategoryName}: `);
    let c = await db.transaction("rw", db.categories, db.components, async () => {
        let key = await db.categories.put({
            "category": categoryName,
            "subcategory": subcategoryName,
            "sourcename": attributes["sourcename"],
            "datahash": attributes["datahash"],
            "stockhash": attributes["stockhash"]
        });
        let category = await db.categories.get(key);
        await addComponents(category, components);
        return category;
    });
    return c;
}

// Fetch and update stock
async function updateStock(category) {
    let stock = await fetchJson(`${SOURCE_PATH}/${category["sourcename"]}.stock.json`,
        `Cannot fetch stock for category ${category["category"]}: ${category["subcategory"]}: `);
    await db.transaction("rw", db.components, async () => {
        let actions = [];
        for (const [component, stockVal] of Object.entries(stock)) {
            actions.push(db.components.update(component, {"stock": stockVal }));
        }
        await Promise.all(actions);
    });
    let hash = await fetchText(`${SOURCE_PATH}/${category["sourcename"]}.stock.json.sha256`,
        `Cannot fetch stock hash for category ${category["category"]}: ${category["subcategory"]}: `);
    await db.categories.update(extractCategoryKey(category), {"stockhash": hash});
}

// Delete given category and all of its components
async function deleteCategory(category) {
    await db.transaction("rw", db.components, db.categories, async () => {
        await db.components.where({"category": extractCategoryKey(category)}).delete();
        await db.categories.delete(extractCategoryKey(category));
    });
}
