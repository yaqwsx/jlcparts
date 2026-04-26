import hashlib
import re
import os
import shutil
import json
import datetime
import gzip
from pathlib import Path

import click
from jlcparts.partLib import PartLibraryDb
from jlcparts.common import sha256file
from jlcparts import attributes, descriptionAttributes

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
    larr = lambda arr : map(lambda str : str.lower(), arr)
    normkey = normalizeAttributeKey(key)
    key = normkey.lower()
    if isinstance(value, str):
        value = normalizeUnicode(value)

    try:
        if key in larr(["Resistance", "Resistance in Ohms @ 25°C", "DC Resistance"]):
            value = attributes.resistanceAttribute(value)
        elif key in larr(["Balance Port Impedence", "Unbalance Port Impedence"]):
            value = attributes.impedanceAttribute(value)
        elif key in larr(["Voltage - Rated", "Voltage Rating - DC", "Allowable Voltage",
                "Clamping Voltage", "Varistor Voltage(Max)", "Varistor Voltage(Typ)",
                "Varistor Voltage(Min)", "Voltage - DC Reverse (Vr) (Max)",
                "Voltage - DC Spark Over (Nom)", "Voltage - Peak Reverse (Max)",
                "Voltage - Reverse Standoff (Typ)", "Voltage - Gate Trigger (Vgt) (Max)",
                "Voltage - Off State (Max)", "Voltage - Input (Max)", "Voltage - Output (Max)",
                "Voltage - Output (Fixed)", "Voltage - Output (Min/Fixed)",
                "Supply Voltage (Max)", "Supply Voltage (Min)", "Output Voltage",
                "Voltage - Input (Min)", "Drain Source Voltage (Vdss)"]):
            value = attributes.voltageAttribute(value)
        elif key in larr(["Rated current", "surge current", "Current - Average Rectified (Io)",
                    "Current - Breakover", "Current - Peak Output", "Current - Peak Pulse (10/1000μs)",
                    "Impulse Discharge Current (8/20us)", "Current - Gate Trigger (Igt) (Max)",
                    "Current - On State (It (AV)) (Max)", "Current - On State (It (RMS)) (Max)",
                    "Current - Supply (Max)", "Output Current", "Output Current (Max)",
                    "Output / Channel Current", "Current - Output",
                    "Saturation Current (Isat)"]):
            value = attributes.currentAttribute(value)
        elif key in larr(["Power", "Power Per Element", "Power Dissipation (Pd)"]):
            value = attributes.powerAttribute(value)
        elif key in larr(["Number of Pins", "Number of Resistors", "Number of Loop",
                    "Number of Regulators", "Number of Outputs", "Number of Capacitors"]):
            value = attributes.countAttribute(value)
        elif key in larr(["Capacitance"]):
            value = attributes.capacitanceAttribute(value)
        elif key in larr(["Inductance"]):
            value = attributes.inductanceAttribute(value)
        elif key == "Rds On (Max) @ Id, Vgs".lower():
            value = attributes.rdsOnMaxAtIdsAtVgs(value)
        elif key in larr(["Operating Temperature (Max)", "Operating Temperature (Min)"]):
            value = attributes.temperatureAttribute(value)
        elif key.startswith("Continuous Drain Current"):
            value = attributes.continuousTransistorCurrent(value, "Id")
        elif key == "Current - Collector (Ic) (Max)".lower():
            value = attributes.continuousTransistorCurrent(value, "Ic")
        elif key in larr(["Vgs(th) (Max) @ Id", "Gate Threshold Voltage (Vgs(th)@Id)"]):
            value = attributes.vgsThreshold(value)
        elif key.startswith("Drain to Source Voltage"):
            value = attributes.drainToSourceVoltage(value)
        elif key == "Drain Source On Resistance (RDS(on)@Vgs,Id)".lower():
            value = attributes.rdsOnMaxAtVgsAtIds(value)
        elif key == "Power Dissipation-Max (Ta=25°C)".lower():
            value = attributes.powerDissipation(value)
        elif key in larr(["Equivalent Series Resistance", "Impedance @ Frequency"]):
            value = attributes.esr(value)
        elif key == "Ripple Current".lower():
            value = attributes.rippleCurrent(value)
        elif key == "Size(mm)".lower():
            value = attributes.sizeMm(value)
        elif key == "Voltage - Forward (Vf) (Max) @ If".lower():
            value = attributes.forwardVoltage(value)
        elif key in larr(["Voltage - Breakdown (Min)", "Voltage - Zener (Nom) (Vz)",
            "Vf - Forward Voltage"]):
            value = attributes.voltageRange(value)
        elif key == "Voltage - Clamping (Max) @ Ipp".lower():
            value = attributes.clampingVoltage(value)
        elif key == "Voltage - Collector Emitter Breakdown (Max)".lower():
            value = attributes.vceBreakdown(value)
        elif key == "Vce(on) (Max) @ Vge, Ic".lower():
            value = attributes.vceOnMax(value)
        elif key in larr(["Input Capacitance (Ciss@Vds)",
                   "Reverse Transfer Capacitance (Crss@Vds)"]):
            value = attributes.capacityAtVoltage(value)
        elif key in larr(["Total Gate Charge (Qg@Vgs)"]):
            value = attributes.chargeAtVoltage(value)
        elif key in larr(["Frequency - self resonant", "Output frequency (max)"]):
            value = attributes.frequencyAttribute(value)
        else:
            value = attributes.stringAttribute(value)
    except: 
        print(f"Could not process key {normkey}; obj {value}")
        value = attributes.stringAttribute(value)   # fall back to string -- these values should have their patterns updated

    assert isinstance(value, dict)
    return normkey, value

def normalizeCapitalization(key):
    """
    Given a category name, normalize capitalization. We turn everything
    lowercase, but some known substring (such as MOQ or MHz) replace back to the
    correct capitalization
    """
    key = key.lower()
    CAPITALIZATIONS = [
        "Basic/Extended", "MHz", "GHz", "Hz", "MOQ"
    ]
    for capt in CAPITALIZATIONS:
        key = key.replace(capt.lower(), capt)
    key = key[0].upper() + key[1:]
    return key

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
    if key in ["ESR (Equivalent Series Resistance)", "Equivalent Series   Resistance(ESR)",
            "Equivalent Series Resistance(ESR)"] or key.startswith("Equivalent Series Resistance"):
        key = "Equivalent Series Resistance"
    if key in ["Allowable Voltage(Vdc)", "Voltage - Max", "Rated Voltage",
            "Voltage Rating"] or key.startswith("Voltage Rated"):
        key = "Allowable Voltage"
    if key in ["DC Resistance (DCR)", "DC Resistance (DCR) (Max)", "DCR( Ω Max )",
            "DC Resistance(DCR)"]:
        key = "DC Resistance"
    if key in ["Insertion Loss ( dB Max )", "Insertion Loss (Max)"]:
        key = "Insertion Loss (dB Max)"
    if key in ["Current Rating (Max)", "Rated Current", "Current Rating"]:
        key = "Rated current"
    if key == "Current - Saturation (Isat)":
        key = "Saturation Current (Isat)"
    if key == "Power - Max":
        key = "Power"
    if key == "Pd - Power Dissipation":
        key = "Power Dissipation (Pd)"
    if key == "Voltage - Breakover":
        key = "Voltage - Breakdown (Min)"
    if key == "Gate Threshold Voltage-VGE(th)":
        key = "Vgs(th) (Max) @ Id"
    if key in ["Gate Threshold Voltage (Vgs(th))", "Gate Threshold Voltage (Vgs(th)@Id)"]:
        key = "Gate Threshold Voltage (Vgs(th)@Id)"
    if key == "Current - Continuous Drain(Id)":
        key = "Continuous Drain Current (Id)"
    if key == "Rds(on)":
        key = "Drain Source On Resistance (RDS(on)@Vgs,Id)"
    if key == "Input Capacitance(Ciss)":
        key = "Input Capacitance (Ciss@Vds)"
    if key == "Output Capacitance(Coss)":
        key = "Output Capacitance (Coss@Vds)"
    if key == "Gate Charge(Qg)":
        key = "Total Gate Charge (Qg@Vgs)"
    if key == "Voltage - DC Reverse(Vr)":
        key = "Voltage - DC Reverse (Vr) (Max)"
    if key == "Voltage - Forward(Vf@If)":
        key = "Voltage - Forward (Vf) (Max) @ If"
    if key == "Current - Rectified":
        key = "Rectified Current"
    if key == "Impedance(Zzt)":
        key = "Zener Impedance (Zzt)"
    if key == "Zener Voltage(Nom)":
        key = "Zener Voltage (Nom)"
    if key == "Zener Voltage(Range)":
        key = "Zener Voltage (Range)"
    if key == "Pins Structure":
        key = "Pin Structure"
    if key.startswith("Lifetime @ Temp"):
        key = "Lifetime @ Temperature"
    if key.startswith("Q @ Freq"):
        key = "Q @ Frequency"
    return normalizeCapitalization(key)

def pullExtraAttributes(component):
    """
    Turn common properties (e.g., base/extended) into attributes. Return them as
    a dictionary
    """
    status = "Discontinued" if component["extra"] == {} and component.get("jlc_extra", {}) == {} else "Active"
    type = "Extended"
    if component["basic"]:
        type = "Basic"
    if component["preferred"]:
        type = "Preferred"
    return {
        "Basic/Extended": type,
        "Package": component["package"],
        "Status": status
    }

def crushImages(images):
    if not images:
        return None
    firstImg = images[0]
    imageUrls = [value for value in firstImg.values() if isinstance(value, str)]
    if not imageUrls:
        return None
    img = imageUrls[0].rsplit("/", 1)[1]
    # make sure every url ends the same
    assert all(i.rsplit("/", 1)[1] == img for i in imageUrls)
    return img

def trimLcscUrl(url, lcsc):
    if url is None:
        return None
    slug = url[url.rindex("/") + 1 : url.rindex("_")]
    if url.startswith("http"):
        assert url.endswith(f"/product-detail/{slug}_{lcsc}.html")
    return slug

def _extraAttributes(extra):
    if "attributes" in extra:
        attr = extra.get("attributes", {})
    else:
        attr = extra
    if isinstance(attr, list):
        return {}
    return attr or {}

def _jlcAttributes(jlcExtra):
    if not isinstance(jlcExtra, dict):
        return {}
    attr = jlcExtra.get("attributes", {})
    if isinstance(attr, list):
        return {}
    return attr or {}

def _mergeAttributes(component):
    attr = dict(_extraAttributes(component.get("extra", {})))
    for key, value in _jlcAttributes(component.get("jlc_extra", {})).items():
        if value in ["", "-"]:
            continue
        attr[key] = value
    return attr

def extractComponent(component, schema):
    try:
        propertyList = []
        for schItem in schema:
            if schItem == "attributes":
                attr = _mergeAttributes(component)
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
                propertyList.append(attr)
            elif schItem == "img":
                images = component.get("extra", {}).get("images", None)
                propertyList.append(crushImages(images))
            elif schItem == "url":
                url = component.get("extra", {}).get("url", None)
                propertyList.append(trimLcscUrl(url, component["lcsc"]))
            elif schItem in component:
                item = component[schItem]
                if isinstance(item, str):
                    item = item.strip()
                propertyList.append(item)
            else:
                propertyList.append(None)
        return propertyList
    except Exception as e:
        raise RuntimeError(f"Cannot extract {component['lcsc']}").with_traceback(e.__traceback__)

def buildDatatable(components):
    schema = ["lcsc", "mfr", "joints", "description",
              "datasheet", "price", "img", "url", "attributes"]
    return {
        "schema": schema,
        "components": [extractComponent(x, schema) for x in components]
    }

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


WEB_FILE_FORMAT_VERSION = 2
LOOKUP_BUCKET_SIZE_DEFAULT = 100000
MAX_COMPONENTS_PER_SHARD_DEFAULT = 20000
COMPONENT_ROW_SCHEMA = {
    "lcsc": 0,
    "mfr": 1,
    "joints": 2,
    "description": 3,
    "datasheet": 4,
    "price": 5,
    "img": 6,
    "url": 7,
    "attributes": 8,
    "stock": 9,
    "subcategory": 10,
}
COMPONENT_SOURCE_SCHEMA = [
    "lcsc",
    "mfr",
    "joints",
    "description",
    "datasheet",
    "price",
    "img",
    "url",
    "attributes",
    "stock",
]


def _stableComponentFilebase(catName, subcatName):
    base = f"{catName}__{subcatName}"
    base = base.replace("&", "and").replace("/", "aka")
    base = re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_")
    digest = hashlib.sha1(f"{catName}\0{subcatName}".encode("utf-8")).hexdigest()[:8]
    return f"{base}__{digest}".lower()


def _writeJsonArtifact(data, filename, compress=False):
    openFn = gzip.open if compress else open
    with openFn(filename, "wt", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"), sort_keys=True)
    return sha256file(filename)


def _writeJsonLinesArtifact(rows, filename):
    with gzip.open(filename, "wt", encoding="utf-8") as f:
        for row in rows:
            json.dump(row, f, separators=(",", ":"), sort_keys=False)
            f.write("\n")
    return sha256file(filename)


def _lookupBucketForLcsc(lcsc, bucketSize):
    return int(lcsc[1:]) // bucketSize


def _isUsableCategory(catName, subcatName):
    return catName.strip() != "" and subcatName.strip() != ""


def _componentRows(components, subcategoryId, attributeLut):
    rows = [COMPONENT_ROW_SCHEMA]
    for component in components:
        values = extractComponent(component, COMPONENT_SOURCE_SCHEMA)
        attrIds = [
            updateLut(attributeLut, [name, value])
            for name, value in values[COMPONENT_ROW_SCHEMA["attributes"]].items()
        ]
        rows.append([
            values[COMPONENT_ROW_SCHEMA["lcsc"]],
            values[COMPONENT_ROW_SCHEMA["mfr"]],
            values[COMPONENT_ROW_SCHEMA["joints"]],
            values[COMPONENT_ROW_SCHEMA["description"]],
            values[COMPONENT_ROW_SCHEMA["datasheet"]],
            values[COMPONENT_ROW_SCHEMA["price"]],
            values[COMPONENT_ROW_SCHEMA["img"]],
            values[COMPONENT_ROW_SCHEMA["url"]],
            attrIds,
            values[COMPONENT_ROW_SCHEMA["stock"]],
            subcategoryId,
        ])
    return rows


def _flushComponentShard(chunk, shardName, outdir, subcategoryId, attributeLut,
                         files, lookupBuckets, lookupBucketSize):
    shardRows = _componentRows(chunk, subcategoryId, attributeLut)
    shardPath = os.path.join(outdir, shardName)
    shardHash = _writeJsonLinesArtifact(shardRows, shardPath)
    files[shardName] = {
        "name": shardName,
        "kind": "components",
        "sha256": shardHash,
        "componentCount": len(chunk),
        "subcategoryId": subcategoryId,
    }
    for component in chunk:
        bucket = _lookupBucketForLcsc(component["lcsc"], lookupBucketSize)
        lookupBuckets.setdefault(bucket, {})[component["lcsc"]] = shardName


def _lutToEntries(lutMap):
    entries = [None] * len(lutMap)
    for key, value in lutMap.items():
        entries[value] = json.loads(key)
    return entries


def updateLut(lutMap, item):
    key = json.dumps(item, separators=(",", ":"), sort_keys=True)
    if key not in lutMap:
        lutMap[key] = len(lutMap)
    return lutMap[key]

@click.command()
@click.argument("library", type=click.Path(dir_okay=False))
@click.argument("outdir", type=click.Path(file_okay=False))
@click.option("--ignoreoldstock", type=int, default=None,
    help="Ignore components that weren't on stock for more than n days")
@click.option("--jobs", type=int, default=1,
    help="Number of parallel processes. Defaults to 1, set to 0 to use all cores")
@click.option("--max-components-per-shard", type=int, default=MAX_COMPONENTS_PER_SHARD_DEFAULT,
    show_default=True,
    help="Maximum number of components stored in a single frontend shard")
@click.option("--lookup-bucket-size", type=int, default=LOOKUP_BUCKET_SIZE_DEFAULT,
    show_default=True,
    help="Number of LCSC numeric codes stored in a single lookup shard")
def buildtables(library, outdir, ignoreoldstock, jobs, max_components_per_shard, lookup_bucket_size):
    """
    Build datatables out of the LIBRARY and save them in OUTDIR
    """
    lib = PartLibraryDb(library)
    Path(outdir).mkdir(parents=True, exist_ok=True)
    clearDir(outdir)
    del jobs  # kept for CLI compatibility with the previous builder

    categories = lib.categories()
    sortedCategories = [
        (catName, sorted(subcategories))
        for catName, subcategories in sorted(categories.items())
    ]
    total = sum(
        1
        for catName, subcategories in sortedCategories
        for subcatName in subcategories
        if _isUsableCategory(catName, subcatName)
    )
    processed = 0

    files = {}
    categoryEntries = []
    attributeLut = {}
    lookupBuckets = {}
    totalComponents = 0
    categoryId = 0

    for catName, subcategories in sortedCategories:
        for subcatName in subcategories:
            if not _isUsableCategory(catName, subcatName):
                continue
            processed += 1
            componentCount = lib.countCategoryComponents(
                catName,
                subcatName,
                stockNewerThan=ignoreoldstock
            )
            if componentCount == 0:
                continue

            categoryId += 1
            categoryKey = _stableComponentFilebase(catName, subcatName)
            shardNames = []
            totalComponents += componentCount
            print(f"{((processed - 1) / max(total, 1) * 100):.2f} % {catName}: {subcatName} ({componentCount})")

            chunk = []
            shardIndex = 0
            for component in lib.iterCategoryComponents(
                    catName, subcatName, stockNewerThan=ignoreoldstock,
                    fetchSize=max(1000, min(max_components_per_shard, 5000))):
                chunk.append(component)
                if len(chunk) < max_components_per_shard:
                    continue
                shardIndex += 1
                shardName = f"components-{categoryKey}-{shardIndex:03d}.jsonl.gz"
                _flushComponentShard(
                    chunk, shardName, outdir, categoryId, attributeLut,
                    files, lookupBuckets, lookup_bucket_size
                )
                shardNames.append(shardName)
                chunk = []

            if chunk:
                shardIndex += 1
                shardName = f"components-{categoryKey}-{shardIndex:03d}.jsonl.gz"
                _flushComponentShard(
                    chunk, shardName, outdir, categoryId, attributeLut,
                    files, lookupBuckets, lookup_bucket_size
                )
                shardNames.append(shardName)

            categoryEntries.append({
                "id": categoryId,
                "category": catName,
                "subcategory": subcatName,
                "componentCount": componentCount,
                "shards": shardNames,
            })

    attributesLutFilename = "attributes-lut.json.gz"
    attributesLutPath = os.path.join(outdir, attributesLutFilename)
    attributesLutHash = _writeJsonArtifact(_lutToEntries(attributeLut), attributesLutPath, compress=True)
    files[attributesLutFilename] = {
        "name": attributesLutFilename,
        "kind": "attributes-lut",
        "sha256": attributesLutHash,
        "entryCount": len(attributeLut),
    }

    lookupFiles = {}
    for bucket, mapping in sorted(lookupBuckets.items()):
        lookupName = f"lookup-{bucket:05d}.json.gz"
        lookupPath = os.path.join(outdir, lookupName)
        lookupHash = _writeJsonArtifact(mapping, lookupPath, compress=True)
        files[lookupName] = {
            "name": lookupName,
            "kind": "lookup",
            "sha256": lookupHash,
            "bucket": bucket,
            "entryCount": len(mapping),
        }
        lookupFiles[str(bucket)] = lookupName

    manifest = {
        "version": WEB_FILE_FORMAT_VERSION,
        "created": datetime.datetime.now().astimezone().replace(microsecond=0).isoformat(),
        "totalComponents": totalComponents,
        "lookupBucketSize": lookup_bucket_size,
        "attributesLut": attributesLutFilename,
        "categories": categoryEntries,
        "lookupBuckets": lookupFiles,
        "files": files,
    }
    _writeJsonArtifact(manifest, os.path.join(outdir, "manifest.json"), compress=False)
