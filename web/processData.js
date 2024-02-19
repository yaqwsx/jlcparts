
const fs = require('fs');
const path = require('path');
const zlib = require("zlib"); 
const process = require('process');
const { execSync } = require('child_process');

const directoryPath = 'public/data';

try{process.chdir('web');}catch(ex){}   // debug path is 'web/..'

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

// Call the function
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

// inverts the lut so that the object becomes an array, with the key being the value (values must be 0-based, numeric, and contiguous)
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
foreachJsonFile(directoryPath, (file, getObj) => {
    if (file.includes('.stock.json')) {
        Object.assign(database.stock, getObj());
    }
});

let processedCount = 0;
const totalCount = fs.readdirSync(directoryPath).filter(file => /\.json\.gz$/.test(file)).length;

foreachJsonFile(directoryPath, (file, getObj) => {
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
        const s = schemaToLookup(obj.schema);
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
    fs.writeFileSync(name, str);    
    fs.writeFileSync(name + '.gz', Buffer.from(zlib.gzipSync(str)));
}
writeOutputFile('subcategories.jsonlines', database.subcategories.map(d => JSON.stringify(d)).join('\n'));
writeOutputFile('components.jsonlines', database.components.map(d => JSON.stringify(d)).join('\n'));
writeOutputFile('attributes-lut.jsonlines', lutToArray(database.attributesLut).map(d => JSON.stringify(d)).join('\n'));

execSync('tar -cf all.jsonlines.tar *.jsonlines.gz');

console.log(`Processing took ${Math.round((new Date().getTime() - startTime) / 6000) / 10} minutes`);