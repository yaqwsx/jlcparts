import click
import re
import os
import json
import datetime
import gzip
from jlcparts.partLib import PartLibraryDb
from jlcparts.common import sha256file
from jlcparts import attributes, descriptionAttributes
from pathlib import Path

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
        propertyList = []
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

@click.command()
@click.argument("library", type=click.Path(dir_okay=False))
@click.argument("outdir", type=click.Path(file_okay=False))
@click.option("--ignoreoldstock", type=int, default=None,
    help="Ignore components that weren't on stock for more than n days")
def buildtables(library, outdir, ignoreoldstock):
    """
    Build datatables out of the LIBRARY and save them in OUTDIR
    """
    lib = PartLibraryDb(library)
    Path(outdir).mkdir(parents=True, exist_ok=True)
    clearDir(outdir)

    categoryIndex = {}
    with lib.startTransaction():
        currentIdx = 0
        total = lib.countCategories()
        for catName, subcats in lib.categories().items():
            # Sometimes, JLC PCB doesn't fill in the category names. Ignore such
            # components.
            if catName.strip() == "":
                continue
            subcatIndex = {}
            for subcatName in subcats:
                # The same...
                if subcatName.strip() == "":
                    continue
                currentIdx += 1
                print(f"{((currentIdx) / total * 100):.2f} % {catName}: {subcatName}")
                filebase = catName + subcatName
                filebase = filebase.replace("&", "and").replace("/", "aka")
                filebase = re.sub('[^A-Za-z0-9]', '_', filebase)

                components = lib.getCategoryComponents(catName, subcatName, stockNewerThan=ignoreoldstock)

                dataTable = buildDatatable(components)
                dataTable.update({"category": catName, "subcategory": subcatName})
                dataHash = saveJson(dataTable, os.path.join(outdir, f"{filebase}.json.gz"),
                                    hash=True, compress=True)

                stockTable = buildStocktable(components)
                stockHash = saveJson(stockTable, os.path.join(outdir, f"{filebase}.stock.json"), hash=True)

                assert subcatName not in subcatIndex
                subcatIndex[subcatName] = {
                    "sourcename": filebase,
                    "datahash": dataHash,
                    "stockhash": stockHash
                }
            categoryIndex[catName] = subcatIndex
    index = {
        "categories": categoryIndex,
        "created": datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()
    }
    saveJson(index, os.path.join(outdir, "index.json"), hash=True)
