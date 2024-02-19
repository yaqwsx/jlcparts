/*
This program loads all the category/stock *.json.gz and *.stock.json files and combines them
into three files, whose contents are a single JSON object per line:
    - attributes-lut.jsonlines  - each line is an attribute, and components will contain a list of attribute indices (the index is the line number)
    - subcategories.jsonlines   - each line is a subcategory
    - components.jsonlines      - each line is a component; references attributes and subcategory by their line number

These files are then packaged into a .tar file, allowing a single file to be downloaded to update the entire database with new components and stock levels.
This reprocessing program is a bit slow, and takes of the order of 10 minutes.
*/

const fs = require('fs');
const path = require('path');
const zlib = require("zlib"); 
const process = require('process');
const { execSync } = require('child_process');

const dataPath = 'web/public/data';

try{process.chdir('web/..');}catch(ex){}   // debug path is 'web/..'

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

    attributesLut: [],  // this is a list of unique attributes; position is used as the attribute index
    stock: {}   // this is just a temporary lookup to help generate the components table
};

// adds the obj to the lut, and returns the index
function updateLut(lut, obj) {
    return lut[JSON.stringify(obj)] ??= Object.keys(lut).length;
}

// Inverts the lut so that the object becomes an array, with the key being the value.
// Values must be 0-based, numeric, and contiguous, or everything will be wrong.
function lutToArray(lut) {
    return Object.entries(lut).sort((a, b) => a[1] - b[1]).map(x => x[0] ? JSON.parse(x[0]) : null);
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
writeOutputFile(`${dataPath}/attributes-lut.jsonlines`, lutToArray(database.attributesLut).map(d => JSON.stringify(d)).join('\n'));

execSync(`(cd ${dataPath} && tar -cf all.jsonlines.tar *.jsonlines.gz)`);

console.log(`Reprocessing took ${Math.round((new Date().getTime() - startTime) / 6000) / 10} minutes`);
