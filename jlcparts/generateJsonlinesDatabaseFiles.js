/*
This program loads all the category/stock *.json.gz and *.stock.json files and combines them
into three files, whose contents are a single JSON object per line:
    - attributes-lut.jsonlines  - each line is an attribute, and components will contain a list of attribute indices (the index is the line number)
    - subcategories.jsonlines   - each line is a subcategory
    - components.jsonlines      - each line is a component; references attributes and subcategory by their line number

These files are then packaged into a .tar file, allowing a single file to be downloaded to update the entire database with new components and stock levels.
*/

const fs = require('fs');
const path = require('path');
const zlib = require("zlib"); 
const process = require('process');
const { execSync } = require('child_process');


const dataPath = ['web/build/data', 'web/public/data', '../web/public/data'].filter(f => fs.existsSync(f))[0];

function foreachJsonFile(directory, processFunc) {
    try {
        // Read the directory
        const filenames = fs.readdirSync(directory);

        // Filter .json files
        const jsonFiles = filenames.filter(file => /(\.stock\.json$|\.json\.gz$)/.test(file));

        // Iterate through .json files
        for (const file of jsonFiles) {
            const filePath = path.join(directory, file);

            // Read and process the JSON file
            const getJson = () => {
                let data = fs.readFileSync(filePath);
                if (/\.gz$/.test(file)) {   // decompress if required
                    data = zlib.gunzipSync(data);
                }

                const json = JSON.parse(data);
                return json;
            };

            processFunc(file, getJson);

            //break;
        }
    } catch (error) {
        console.error('Error processing JSON files:', error);
    }
}

// this contains the output database table contents
let database = {
    subcategories: [schemaToLookup(['subcategory', 'category', 'sourcename'])],
    components: [schemaToLookup(['lcsc', 'mfr', 'description', 'attrsIdx', 'stock', 'subcategoryIdx', 'joints', 'datasheet', 'price', 'img', 'url'])],

    attributesLut: new Map(),  // this is a list of unique attributes; each new entry gets a new index. Using a Map here instead of an object gives 40x processing speedup
    stock: {}   // this is just a temporary lookup to help generate the components table
};

// adds the obj to the lut, and returns the index
function updateLut(entryMap, entry) {
    const entryKey = JSON.stringify(entry);
    if (!entryMap.has(entryKey)) {
        const index = entryMap.size;
        entryMap.set(entryKey, index);
        return index;
    }
    return entryMap.get(entryKey);
  }

// Inverts the lut so that the Map becomes an array, with the key being the value.
// Values must be 0-based, numeric, and contiguous, or everything will be wrong.
function lutToArray(lutMap) {
    return Array.from(lutMap.entries()).sort((a, b) => a[1] - b[1]).map(x => x[0]);
}

function schemaToLookup(arr) {
    let lut = {};
    arr.forEach((key, i) => lut[key] = i);
    return lut;
}

const startTime = new Date().getTime();

// populate the stock lookup
foreachJsonFile(dataPath, (file, getObj) => {
    if (file.includes('.stock.json')) {
        Object.assign(database.stock, getObj());
    }
});

let processedCount = 0;
const totalCount = fs.readdirSync(dataPath).filter(file => /\.json\.gz$/.test(file)).length;

foreachJsonFile(dataPath, (file, getObj) => {
    if (file.includes('.stock.json')) {
        return;
    }

    const obj = getObj();

    // subcategories schema: ['subcategory', 'category', 'sourcename']
    database.subcategories.push([obj.subcategory, obj.category, file.split('.')[0]]);
    const subcategoryIdx = database.subcategories.length - 1;
    
    try {
        //input schema = ["lcsc", "mfr", "joints", "description","datasheet", "price", "img", "url", "attributes"]
        // components schema ['lcsc', 'mfr', 'description', 'attrsIdx', 'stock', 'subcategoryIdx', 'joints', 'datasheet', 'price', 'img', 'url']
        const s = schemaToLookup(obj.schema);       // input schema
        obj.components.forEach(comp => {
            let entry = [
                comp[s.lcsc], 
                comp[s.mfr], 
                comp[s.description], 
                Object.entries(comp[s.attributes]).map(attr => updateLut(database.attributesLut, attr)),
                database.stock[comp[s.lcsc]],
                subcategoryIdx,
                comp[s.joints],
                comp[s.datasheet],
                comp[s.price],
                comp[s.img],
                comp[s.url]
            ];
            database.components.push(entry);
        });

        console.log(`Processed ${++processedCount} / ${totalCount} (${Math.round(processedCount / totalCount * 100)}%)`, file);
    } catch (ex) {
        console.log(`Failed on ${file}`, ex);
    }
});

console.log('Writing jsonlines files');
function writeOutputFile(name, str) {
    //fs.writeFileSync(name, str);    
    fs.writeFileSync(name + '.gz', Buffer.from(zlib.gzipSync(str)));
}
writeOutputFile(`${dataPath}/subcategories.jsonlines`, database.subcategories.map(d => JSON.stringify(d)).join('\n'));
writeOutputFile(`${dataPath}/components.jsonlines`, database.components.map(d => JSON.stringify(d)).join('\n'));
writeOutputFile(`${dataPath}/attributes-lut.jsonlines`, lutToArray(database.attributesLut).join('\n'));

execSync(`(cd ${dataPath} && tar -cf all.jsonlines.tar *.jsonlines.gz)`);

console.log(`Reprocessing took ${Math.round((new Date().getTime() - startTime) / 1000)} seconds`);
