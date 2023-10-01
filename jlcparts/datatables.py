import dataclasses
import gzip
import itertools
import json
import multiprocessing
from multiprocessing.shared_memory import SharedMemory
import os
import random
import shutil
import sqlite3
import struct
import textwrap
from pathlib import Path
from typing import Dict, Generator, Optional

import click
import pyzstd

from jlcparts import attributes, descriptionAttributes
from jlcparts.common import sha256file
from jlcparts.partLib import PartLibraryDb


def saveJson(object, filename, hash=False, pretty=False, compress=False):
    openFn = gzip.open if compress else open
    with openFn(filename, "wt", encoding="utf-8") as f:
        if pretty:
            json.dump(object, f, indent=4, sort_keys=True)
        else:
            json.dump(object, f, separators=(',', ':'), sort_keys=True)
    if hash:
        with open(filename + ".sha256", "w") as f:
            hash = sha256file(filename)
            f.write(hash)
        return hash

def weakUpdateParameters(attrs, newParameters):
    for attr, value in newParameters.items():
        if attr in attrs and attrs[attr] not in ["", "-"]:
            continue
        attrs[attr] = value

def extractAttributesFromDescription(description):
    if description.startswith("Chip Resistor - Surface Mount"):
        return descriptionAttributes.chipResistor(description)
    if (description.startswith("Multilayer Ceramic Capacitors MLCC") or
       description.startswith("Aluminum Electrolytic Capacitors")):
        return descriptionAttributes.capacitor(description)
    return {}

def normalizeUnicode(value):
    """
    Replace unexpected unicode sequence with a resonable ones
    """
    value = value.replace("（", " (").replace("）", ")")
    value = value.replace("，", ",")
    return value

def normalizeAttribute(key, value):
    """
    Takes a name of attribute and its value (usually a string) and returns a
    normalized attribute name and its value as a tuple. Normalized value is a
    dictionary in the format:
        {
            "format": <format string, e.g., "${Resistance} ${Power}",
            "primary": <name of primary value>,
            "values": <dictionary of values with units, e.g, { "resistance": [10, "resistance"] }>
        }
    The fallback is unit "string"
    """
    key = normalizeAttributeKey(key)
    if isinstance(value, str):
        value = normalizeUnicode(value)
    if key in ["Resistance", "Resistance in Ohms @ 25°C", "DC Resistance"]:
        value = attributes.resistanceAttribute(value)
    elif key in ["Balance Port Impedence", "Unbalance Port Impedence"]:
        value = attributes.impedanceAttribute(value)
    elif key in ["Voltage - Rated", "Voltage Rating - DC", "Allowable Voltage",
            "Clamping Voltage", "Varistor Voltage(Max)", "Varistor Voltage(Typ)",
            "Varistor Voltage(Min)", "Voltage - DC Reverse (Vr) (Max)",
            "Voltage - DC Spark Over (Nom)", "Voltage - Peak Reverse (Max)",
            "Voltage - Reverse Standoff (Typ)", "Voltage - Gate Trigger (Vgt) (Max)",
            "Voltage - Off State (Max)", "Voltage - Input (Max)", "Voltage - Output (Max)",
            "Voltage - Output (Fixed)", "Voltage - Output (Min/Fixed)",
            "Supply Voltage (Max)", "Supply Voltage (Min)", "Output Voltage",
            "Voltage - Input (Min)", "Drain Source Voltage (Vdss)"]:
        value = attributes.voltageAttribute(value)
    elif key in ["Rated current", "surge current", "Current - Average Rectified (Io)",
                 "Current - Breakover", "Current - Peak Output", "Current - Peak Pulse (10/1000μs)",
                 "Impulse Discharge Current (8/20us)", "Current - Gate Trigger (Igt) (Max)",
                 "Current - On State (It (AV)) (Max)", "Current - On State (It (RMS)) (Max)",
                 "Current - Supply (Max)", "Output Current", "Output Current (Max)",
                 "Output / Channel Current", "Current - Output",
                 "Saturation Current (Isat)"]:
        value = attributes.currentAttribute(value)
    elif key in ["Power", "Power Per Element", "Power Dissipation (Pd)"]:
        value = attributes.powerAttribute(value)
    elif key in ["Number of Pins", "Number of Resistors", "Number of Loop",
                 "Number of Regulators", "Number of Outputs", "Number of Capacitors"]:
        value = attributes.countAttribute(value)
    elif key in ["Capacitance"]:
        value = attributes.capacitanceAttribute(value)
    elif key in ["Inductance"]:
        value = attributes.inductanceAttribute(value)
    elif key == "Rds On (Max) @ Id, Vgs":
        value = attributes.rdsOnMaxAtIdsAtVgs(value)
    elif key in ["Operating Temperature (Max)", "Operating Temperature (Min)"]:
        value = attributes.temperatureAttribute(value)
    elif key.startswith("Continuous Drain Current"):
        value = attributes.continuousTransistorCurrent(value, "Id")
    elif key == "Current - Collector (Ic) (Max)":
        value = attributes.continuousTransistorCurrent(value, "Ic")
    elif key in ["Vgs(th) (Max) @ Id", "Gate Threshold Voltage (Vgs(th)@Id)"]:
        value = attributes.vgsThreshold(value)
    elif key.startswith("Drain to Source Voltage"):
        value = attributes.drainToSourceVoltage(value)
    elif key == "Drain Source On Resistance (RDS(on)@Vgs,Id)":
        value = attributes.rdsOnMaxAtVgsAtIds(value)
    elif key == "Power Dissipation-Max (Ta=25°C)":
        value = attributes.powerDissipation(value)
    elif key in ["Equivalent Series Resistance", "Impedance @ Frequency"]:
        value = attributes.esr(value)
    elif key == "Ripple Current":
        value = attributes.rippleCurrent(value)
    elif key == "Size(mm)":
        value = attributes.sizeMm(value)
    elif key == "Voltage - Forward (Vf) (Max) @ If":
        value = attributes.forwardVoltage(value)
    elif key in ["Voltage - Breakdown (Min)", "Voltage - Zener (Nom) (Vz)",
        "Vf - Forward Voltage"]:
        value = attributes.voltageRange(value)
    elif key == "Voltage - Clamping (Max) @ Ipp":
        value = attributes.clampingVoltage(value)
    elif key == "Voltage - Collector Emitter Breakdown (Max)":
        value = attributes.vceBreakdown(value)
    elif key == "Vce(on) (Max) @ Vge, Ic":
        value = attributes.vceOnMax(value)
    elif key in ["Input Capacitance (Ciss@Vds)",
               "Reverse Transfer Capacitance (Crss@Vds)"]:
        value = attributes.capacityAtVoltage(value)
    elif key in ["Total Gate Charge (Qg@Vgs)"]:
        value = attributes.chargeAtVoltage(value)
    else:
        value = attributes.stringAttribute(value)
    assert isinstance(value, dict)
    return key, value

def normalizeAttributeKey(key):
    """
    Takes a name of attribute and its value and returns a normalized key
    (e.g., strip unit name).
    """
    if "(Watts)" in key:
        key = key.replace("(Watts)", "").strip()
    if "(Ohms)" in key:
        key = key.replace("(Ohms)", "").strip()
    if key == "aristor Voltage(Min)":
        key = "Varistor Voltage(Min)"
    if key in ["ESR (Equivalent Series Resistance)", "Equivalent Series   Resistance(ESR)"] or key.startswith("Equivalent Series Resistance"):
        key = "Equivalent Series Resistance"
    if key in ["Allowable Voltage(Vdc)", "Voltage - Max", "Rated Voltage"] or key.startswith("Voltage Rated"):
        key = "Allowable Voltage"
    if key in ["DC Resistance (DCR)", "DC Resistance (DCR) (Max)", "DCR( Ω Max )"]:
        key = "DC Resistance"
    if key in ["Insertion Loss ( dB Max )", "Insertion Loss (Max)"]:
        key = "Insertion Loss (dB Max)"
    if key in ["Current Rating (Max)", "Rated Current"]:
        key = "Rated current"
    if key == "Power - Max":
        key = "Power"
    if key == "Voltage - Breakover":
        key = "Voltage - Breakdown (Min)"
    if key == "Gate Threshold Voltage-VGE(th)":
        key = "Vgs(th) (Max) @ Id"
    if key == "Pins Structure":
        key = "Pin Structure"
    if key.startswith("Lifetime @ Temp"):
        key = "Lifetime @ Temperature"
    if key.startswith("Q @ Freq"):
        key = "Q @ Frequency"
    return key

def pullExtraAttributes(component):
    """
    Turn common properties (e.g., base/extended) into attributes. Return them as
    a dictionary
    """
    status = "Discontinued" if component["extra"] == {} else "Active"
    return {
        "Basic/Extended": "Basic" if component["basic"] else "Extended",
        "Package": component["package"],
        "Status": status
    }

def crushImages(images):
    if not images:
        return None
    firstImg = images[0]
    img = firstImg.popitem()[1].rsplit("/", 1)[1]
    # make sure every url ends the same
    assert all(i.rsplit("/", 1)[1] == img for i in firstImg.values())
    return img

def trimLcscUrl(url, lcsc):
    if url is None:
        return None
    slug = url[url.rindex("/") + 1 : url.rindex("_")]
    assert f"https://lcsc.com/product-detail/{slug}_{lcsc}.html" == url
    return slug

def extractComponent(component, schema):
    try:
        result: Dict[str, Optional[str]] = {}
        for schItem in schema:
            if schItem == "attributes":
                # The cache might be in the old format
                if "attributes" in component.get("extra", {}):
                    attr = component.get("extra", {}).get("attributes", {})
                else:
                    attr = component.get("extra", {})
                if isinstance(attr, list):
                    # LCSC return empty attributes as a list, not dictionary
                    attr = {}
                attr.update(pullExtraAttributes(component))
                weakUpdateParameters(attr, extractAttributesFromDescription(component["description"]))

                # Remove extra attributes that are either not useful, misleading
                # or overridden by data from JLC
                attr.pop("url", None)
                attr.pop("images", None)
                attr.pop("prices", None)
                attr.pop("datasheet", None)
                attr.pop("id", None)
                attr.pop("manufacturer", None)
                attr.pop("number", None)
                attr.pop("title", None)
                attr.pop("quantity", None)
                for i in range(10):
                    attr.pop(f"quantity{i}", None)

                attr["Manufacturer"] = component.get("manufacturer", None)

                attr = dict([normalizeAttribute(key, val) for key, val in attr.items()])
                result[schItem] = json.dumps(attr)
            elif schItem == "img":
                images = component.get("extra", {}).get("images", None)
                result[schItem] = crushImages(images)
            elif schItem == "url":
                url = component.get("extra", {}).get("url", None)
                result[schItem] = trimLcscUrl(url, component["lcsc"])
            elif schItem in component:
                item = component[schItem]
                if isinstance(item, str):
                    item = item.strip()
                else:
                    item = json.dumps(item)
                result[schItem] = item
            else:
                result[schItem] = None
        return result
    except Exception as e:
        raise RuntimeError(f"Cannot extract {component['lcsc']}").with_traceback(e.__traceback__)


def buildDatatable(components) -> Generator[Dict[str, str], None, None]:
    schema = ["lcsc", "mfr", "joints", "description",
              "datasheet", "price", "img", "url", "attributes", "stock"]
    return (extractComponent(component, schema) for component in components)

def buildStocktable(components):
    return {component["lcsc"]: component["stock"] for component in components }

def clearDir(directory):
    """
    Delete everything inside a directory
    """
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        if os.path.isfile(file_path) or os.path.islink(file_path):
            os.unlink(file_path)
        elif os.path.isdir(file_path):
            shutil.rmtree(file_path)


def _sqlite_fast_cur(path: str) -> sqlite3.Cursor:
    conn = sqlite3.connect(path, isolation_level=None)
    cursor = conn.cursor()
    # very dangerous, but we don't care about data integrity here. Recovery is to
    # delete the whole database and rebuild.
    cursor.execute("PRAGMA journal_mode=OFF;")
    cursor.execute("PRAGMA synchronous=OFF;")
    return cursor


INIT_TABLES_SQL = textwrap.dedent("""\
    CREATE TABLE categories
    (
        id          INTEGER PRIMARY KEY NOT NULL,
        category    TEXT NOT NULL,
        subcategory TEXT NOT NULL,
        UNIQUE (category, subcategory)
    );
    CREATE TABLE component
    (
        lcsc        TEXT PRIMARY KEY NOT NULL,
        category_id INTEGER          NOT NULL REFERENCES categories (id),
        mfr         TEXT             NOT NULL,
        joints      INTEGER          NOT NULL,
        description TEXT             NOT NULL,
        datasheet   TEXT             NOT NULL,
        price       TEXT             NOT NULL, -- JSON
        img         TEXT,
        url         TEXT,
        attributes  TEXT             NOT NULL, -- JSON
        stock       INTEGER          NOT NULL
    );""")

@dataclasses.dataclass
class MapCategoryParams:
    libraryPath: str
    outdir: str
    ignoreoldstock: int

    catName: str
    subcatName: str


_map_category_cur = None
def _map_category(val: MapCategoryParams):
    # Sometimes, JLC PCB doesn't fill in the category names. Ignore such
    # components.
    if val.catName.strip() == "":
        return None
    if val.subcatName.strip() == "":
        return None

    # each process gets its own database, then we merge them at the end and add indexes
    # we do this because SQLite doesn't do a good job with concurrent writes and ends up
    # getting stuck on locks
    global _map_category_cur
    if _map_category_cur is None:
        _map_category_cur = _sqlite_fast_cur(os.path.join(val.outdir, f"part_${os.getpid()}.sqlite3"))
        _map_category_cur.executescript(INIT_TABLES_SQL)
    cur = _map_category_cur

    lib = PartLibraryDb(val.libraryPath)
    components = lib.getCategoryComponents(val.catName, val.subcatName,
                                           stockNewerThan=val.ignoreoldstock)

    categoryId = random.randint(0, 2**31 - 1)
    insertCategory = textwrap.dedent("""\
        INSERT INTO categories (id, category, subcategory)
        VALUES ($id, $category, $subcategory)""")
    cur.execute(
        insertCategory,
        {
            "id": categoryId,
            "category": val.catName,
            "subcategory": val.subcatName
        })

    insertComponent = textwrap.dedent("""\
        INSERT INTO component (lcsc, category_id, mfr, joints, description, datasheet, price, img, url,
                               attributes, stock)
        VALUES ($lcsc, $category_id, $mfr, $joints, $description, $datasheet, $price, $img, $url,
                $attributes, $stock)""")
    dataIter = ({
        **component,
        "category_id": categoryId,
    } for component in buildDatatable(components))

    while batch := list(itertools.islice(dataIter, 200)):
        cur.executemany(insertComponent, batch)
        cur.connection.commit()

    return {
        "catName": val.catName,
        "subcatName": val.subcatName,
    }

def compressChunkGzip(c):
    return (c, gzip.compress(c))

def pagedCompressFileGzip(inputPath, pageSize=1024, jobs=1):
    with open(inputPath, 'rb') as infile, \
            open(f"{inputPath}.gzpart", 'wb') as outfile, \
            open(f"{inputPath}.gzindex", 'wb') as indexfile:
        dataPos = 0
        compPos = 0

        # magic number to indicate index format.
        indexfile.write(struct.pack('<QQ', 0xb6d881b0d2f0408e, 0x9c7649381fe30e8c))

        totalChunks = os.path.getsize(inputPath) // pageSize
        with multiprocessing.Pool(jobs or multiprocessing.cpu_count()) as pool:

            chunkIter = iter(lambda: infile.read(pageSize), b'')
            for i, (chunk, compressedChunk) in enumerate(pool.imap(compressChunkGzip, chunkIter, chunksize=100)):
                if i % (16*1024) == 0:
                    print(f"{i / totalChunks * 100:.0f} % compressed")
                outfile.write(compressedChunk)
                indexfile.write(struct.pack('<LL', dataPos, compPos))
                dataPos += len(chunk)
                compPos += len(compressedChunk)

            # write last index entry to simplify index reading logic.
            indexfile.write(struct.pack('<LL', dataPos, compPos))

def compressChunkZstd(args):
    c, sharedDictName = args
    try:
        sharedDict = SharedMemory(name=sharedDictName)
        zstdDict = pyzstd.ZstdDict(sharedDict.buf)
        return (c, pyzstd.compress(c,  6, zstd_dict=zstdDict))
    finally:
        sharedDict.close()


def pagedCompressFileZstd(inputPath, pageSize=1024, jobs=1, dictSize=16*1024):
    def trainDict():
        fileSize = os.path.getsize(inputPath)
        trainingChunkSize = 256 * 1024
        trainingSamplesCount = 32
        step = (fileSize - trainingChunkSize) // (trainingSamplesCount - 1)
        trainingSamples = []

        with open(inputPath, 'rb') as file:
            for offset in range(0, fileSize, step):
                file.seek(offset)
                trainingSamples.append(file.read(trainingChunkSize))

        zstdDict = pyzstd.train_dict(trainingSamples, dict_size=dictSize)
        zstdDict = pyzstd.finalize_dict(zstdDict, trainingSamples, dict_size=dictSize, level=6)
        return zstdDict


    with open(inputPath, 'rb') as infile, \
            open(f"{inputPath}.zstpart", 'wb') as outfile, \
            open(f"{inputPath}.zstindex", 'wb') as indexfile:
        dataPos = 0
        compPos = 0

        print("Training dictionary...")
        zstdDict = trainDict()

        # magic number to indicate index format.
        indexfile.write(struct.pack('<QQ', 0x0f4b462afc1e47fc, 0xb6ee9b384955469b))
        indexfile.write(zstdDict.dict_content)

        try:
            sharedDict = SharedMemory(create=True, size=len(zstdDict.dict_content))
            sharedDict.buf[:] = zstdDict.dict_content
            sharedDictName = sharedDict.name

            totalChunks = os.path.getsize(inputPath) // pageSize
            with multiprocessing.Pool(jobs or multiprocessing.cpu_count()) as pool:

                args = ((chunk, sharedDictName) for chunk in iter(lambda: infile.read(pageSize), b''))
                for i, (chunk, compressedChunk) in enumerate(pool.imap(compressChunkZstd, args, chunksize=100)):
                    if i % (16*1024) == 0:
                        print(f"{i / totalChunks * 100:.0f} % compressed")
                    outfile.write(compressedChunk)
                    indexfile.write(struct.pack('<LL', dataPos, compPos))
                    dataPos += len(chunk)
                    compPos += len(compressedChunk)

                # write last index entry to simplify index reading logic.
                indexfile.write(struct.pack('<LL', dataPos, compPos))
        finally:
            sharedDict.close()
            sharedDict.unlink()


@click.command()
@click.argument("library", type=click.Path(dir_okay=False))
@click.argument("outdir", type=click.Path(file_okay=False))
@click.option("--ignoreoldstock", type=int, default=None,
              help="Ignore components that weren't on stock for more than n days")
@click.option("--jobs", type=int, default=1,
              help="Number of parallel processes. Set to 0 to use all cores")
@click.option("--pagesize", type=int, default=1024,
              help="Page size for the compressed database")
@click.option("--dictsize", type=int, default=16 * 1024,
              help="Dictionary size for the compressed database")
@click.option('--compression-algorithm', type=click.Choice(['zstd', 'gzip', 'none']),
              default='zstd',
              help="Compression algorithm to use")
def buildtables(library, outdir, ignoreoldstock, jobs, pagesize, dictsize,
                compression_algorithm):
    """
    Build datatables out of the LIBRARY and save them in OUTDIR
    """
    lib = PartLibraryDb(library)
    Path(outdir).mkdir(parents=True, exist_ok=True)
    clearDir(outdir)

    outputDb = _sqlite_fast_cur(os.path.join(outdir, "index.sqlite3"))
    outputDb.executescript(INIT_TABLES_SQL)

    params = []
    for (catName, subcategories) in lib.categories().items():
        for subcatName in subcategories:
            params.append(MapCategoryParams(
                libraryPath=library, outdir=outdir, ignoreoldstock=ignoreoldstock,
                catName=catName, subcatName=subcatName))

    total = lib.countCategories()

    def report_progress(i, result):
        if result is None:
            return
        catName, subcatName = result["catName"], result["subcatName"]
        print(f"{((i) / total * 100):.1f} % {catName}: {subcatName}")

    if jobs == 1:
        # do everything in the main thread in this case to make debugging easier
        for i, param in enumerate(params):
            report_progress(i, _map_category(param))
    else:
        with multiprocessing.Pool(jobs or multiprocessing.cpu_count()) as pool:
            for i, result in enumerate(pool.imap_unordered(_map_category, params)):
                report_progress(i, result)

    outputDb.execute(f"pragma page_size = {pagesize};")

    # merge all databases
    print("Merging databases...")
    for i, filename in enumerate(os.listdir(outdir)):
        if not filename.startswith("part_"):
            continue
        filepath = os.path.join(outdir, filename)
        outputDb.execute(f"ATTACH DATABASE '{filepath}' AS db{i};")
        # happens fully in native code and is very fast
        outputDb.execute(f"INSERT INTO main.categories SELECT * FROM db{i}.categories;")
        outputDb.execute(f"INSERT INTO main.component SELECT * FROM db{i}.component;")
        outputDb.execute(f"DETACH DATABASE db{i};")
        os.unlink(filepath)

    print("Building indexes...")
    # create indexes after all data is inserted to speed up the process
    outputDb.executescript("""\
CREATE INDEX component_mfr ON component (mfr);
CREATE INDEX categories_category ON categories (category);
CREATE INDEX categories_subcategory ON categories (subcategory);
""")

    # optimize db: https://github.com/phiresky/sql.js-httpvfs#usage
    print("Optimizing database...")
    outputDb.execute("pragma journal_mode = delete;")
    outputDb.execute("vacuum;")
    outputDb.connection.close()

    print("Compressing database...")
    if compression_algorithm == 'gzip':
        pagedCompressFileGzip(
            os.path.join(outdir, "index.sqlite3"),
            pageSize=pagesize)
    elif compression_algorithm == 'zstd':
        pagedCompressFileZstd(
            os.path.join(outdir, "index.sqlite3"),
            pageSize=pagesize,
            jobs=jobs,
            dictSize=dictsize)
