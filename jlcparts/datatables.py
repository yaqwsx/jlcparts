import click
import re
import os
import json
import datetime
import sys
from jlcparts.partLib import PartLibrary
from jlcparts.common import sha256file
from jlcparts import attributes
from pathlib import Path

def saveJson(object, filename, hash=False, pretty=False):
    with open(filename, "w") as f:
        if pretty:
            json.dump(object, f, indent=4, sort_keys=True)
        else:
            json.dump(object, f)
    if hash:
        with open(filename + ".sha256", "w") as f:
            hash = sha256file(filename)
            f.write(hash)
        return hash

def normalizeAttribute(key, value):
    """
    Takes a name of attribute and its value (usually a string) and returns a
    normalized attribute name and its value as a tuple. Normalized value is a
    dictionary in the format:
        {
            "format": <format string, e.g., "${Resistance} ${Power}",
            "primary": <name of primary value>,
            "values": <dictinary of values with units, e.g, { "resistance": [10, "resistance"] }>
        }
    The fallback is unit "string"
    """
    key = normalizeAttributeKey(key)
    if key == "Resistance":
        value = attributes.resistanceAttribute(value)
    elif key == "Rds On (Max) @ Id, Vgs":
        value = attributes.rdsOnMaxAtIdsAtVgs(value)
    elif key == "Continuous Drain Current (Id) @ 25°C":
        value = attributes.continuousDrainCurrent(value)
    elif key == "Vgs(th) (Max) @ Id":
        value = attributes.vgsThreshold(value)
    elif key == "Drain to Source Voltage(Vdss)":
        value = attributes.drainToSourceVoltage(value)
    elif key == "Power Dissipation-Max (Ta=25°C)":
        value = attributes.powerDissipation(value)
    elif key == "Power":
        value = attributes.power(value)
    else:
        value = attributes.stringAttribute(value)
    assert(isinstance(value, dict))
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
    return key

def pullExtraAttributes(component):
    """
    Turn common properties (e.g., base/extended) into attributes. Return them as
    a dictionary
    """
    return {
        "Basic/Extended": "Basic" if component["basic"] else "Extended",
        "Package": component["package"]
    }

def extractComponent(component, schema):
    propertyList = []
    for schItem in schema:
        if schItem == "attributes":
            attr = component.get("extra", {}).get("attributes", {})
            if isinstance(attr, list):
                # LCSC return empty attributes as a list, not dictionary
                attr = {}
            attr.update(pullExtraAttributes(component))
            attr = dict([normalizeAttribute(key, val) for key, val in attr.items()])
            propertyList.append(attr)
        elif schItem == "images":
            images = component.get("extra", {}).get("images", {})
            if len(images) > 0:
                images = images[0]
            else:
                images = None
            propertyList.append(images)
        elif schItem == "url":
            url = component.get("extra", {}).get("url", None)
            if url is not None:
                url = "https://lcsc.com" + url
            propertyList.append(url)
        elif schItem in component:
            propertyList.append(component[schItem])
        else:
            propertyList.append(None)
    return propertyList

def buildDatatable(components):
    schema = ["lcsc", "mfr", "joints", "manufacturer", "description",
              "datasheet", "price", "images", "url", "attributes"]
    return {
        "schema": schema,
        "components": [extractComponent(x, schema) for x in components.values()]
    }

def buildStocktable(components):
    return {component["lcsc"]: component["stock"] for component in components.values() }

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
def buildtables(library, outdir):
    """
    Build datatables out of the LIBRARY and save them in OUTDIR
    """
    lib = PartLibrary(library)
    Path(outdir).mkdir(parents=True, exist_ok=True)
    clearDir(outdir)

    categoryIndex = {}
    for catName, subcats in lib.categories().items():
        subcatIndex = {}
        for subcatName in subcats:
            filebase = re.sub('[^A-Za-z0-9]', '_', catName + subcatName)

            dataTable = buildDatatable(lib.lib[catName][subcatName])
            dataTable.update({"category": catName, "subcategory": subcatName})
            dataHash = saveJson(dataTable, os.path.join(outdir, f"{filebase}.json"), hash=True)

            stockTable = buildStocktable(lib.lib[catName][subcatName])
            stockHash = saveJson(stockTable, os.path.join(outdir, f"{filebase}.stock.json"), hash=True)

            assert(subcatName not in subcatIndex)
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





