import click
import shutil
import os
import time
import datetime
import sys
import json
from multiprocessing import Pool, TimeoutError
from requests.exceptions import ConnectionError
from jlcparts.partLib import PartLibrary, loadJlcTable, getLcscExtraNew
from jlcparts.datatables import buildtables

def fetchLcscData(component):
    lcsc = component['lcsc']
    extra = getLcscExtraNew(lcsc)
    return (component, extra)

@click.command()
@click.argument("source", type=click.Path(dir_okay=False, exists=True))
@click.argument("output", type=click.Path(dir_okay=False, writable=True))
@click.option("--cache", type=click.Path(dir_okay=False, exists=True),
    help="Previously generated JSON file serving as a cache for LCSC informatioon")
@click.option("--age", type=int, default=0,
    help="Automatically discard n oldest components and fetch them again")
@click.option("--limit", type=int, default=10000,
    help="Limit number of newly added components")
@click.option("--newLogFile", type=click.Path(dir_okay=False), default=None,
    help="Save a file with newly added components (one LCSC code per line")
def getLibrary(cache, source, output, age, newlogfile, limit):
    """
    Download library inside OUTPUT (JSON format) based on SOURCE (csv table
    provided by JLC PCB).

    Cou can specify previously downloaded library as a cache to save requests to
    fetch LCSC extra data.
    """
    cacheLib = PartLibrary(cache)
    lib = PartLibrary()

    with open(source, newline="") as f:
        jlcTable = loadJlcTable(f)

    # Make copy of the output in case we make a mistake
    if os.environ.get("JLCPARTS_DEV", "0") == "1":
        if os.path.exists(output):
            shutil.copy(output, output + ".bak")

    missing = set()
    for component in jlcTable.values():
        lcsc = component['lcsc']
        if not cacheLib.exists(lcsc):
            missing.add(lcsc)
    print(f"New {len(missing)} components out of {len(jlcTable.values())} total")

    ageCount = min(age, max(0, limit - len(missing)))
    print(f"{ageCount} components will be aged and thus refreshed")
    cacheLib.deleteNOldest(ageCount)

    newComponents = []
    # First, handle existing components, so we save it into the cache
    componentsToFetch = []
    for component in jlcTable.values():
        if len(componentsToFetch) >= limit:
            break
        lcsc = component['lcsc']
        cached = cacheLib.getComponent(lcsc)
        if cached:
            component["extra"] = cached["extra"]
            component["extraTimestamp"] = cached["extraTimestamp"] if "extraTimestamp" in cached else 0
            lib.addComponent(component)
        else:
            componentsToFetch.append(component)
    print(f"{len(componentsToFetch)} components will be fetched.")

    with Pool(processes=10) as pool:
        for i, (component, extra) in enumerate(pool.imap_unordered(fetchLcscData, componentsToFetch)):
            lcsc = component['lcsc']
            print(f"  {lcsc} fetched. {((i+1) / len(componentsToFetch) * 100):.2f} %")
            component["extra"] = extra
            component["extraTimestamp"] = int(time.time())
            lib.addComponent(component)
    lib.save(output)
    if newlogfile:
        with open(newlogfile, "w") as f:
            for c in newComponents:
                f.write(c + "\n")

@click.command()
@click.argument("newComponents", type=click.Path(exists=True, dir_okay=False))
@click.argument("changelog", type=click.Path(exists=True, dir_okay=False))
def updatechangelog(newcomponents, changelog):
    comps = [x.strip() for x in open(newcomponents).readlines()]

    with open(changelog) as f:
        logContent = f.read()
        if len(logContent) == 0:
            logContent = "{}"
        log = json.loads(logContent)
    print(log)

    today = datetime.date.today()
    todayStr = f'{today}'
    if todayStr not in changelog:
        log[todayStr] = comps
    else:
        log[todayStr] = list(set(comps) + set(log[todayStr]))

    with open(changelog, "w") as f:
        f.write(json.dumps(log))


@click.command()
@click.argument("libraryFilename")
def listcategories(libraryfilename):
    """
    Print all categories from library specified by LIBRARYFILENAMEto standard
    output
    """
    lib = PartLibrary(libraryfilename)
    for c, subcats in lib.categories().items():
        print(f"{c}:")
        for s in subcats:
            print(f"  {s}")

@click.command()
@click.argument("libraryFilename")
def listattributes(libraryfilename):
    """
    Print all keys in the extra["attributes"] arguments from library specified by
    LIBRARYFILENAMEto standard output
    """
    keys = set()
    lib = PartLibrary(libraryfilename)
    for subcats in lib.lib.values():
        for parts in subcats.values():
            for data in parts.values():
                if "extra" not in data:
                    continue
                extra = data["extra"]
                attr = extra.get("attributes", {})
                if not isinstance(attr, list):
                    for k in extra.get("attributes", {}).keys():
                        keys.add(k)
    for k in keys:
        print(k)

@click.command()
@click.argument("lcsc_code")
def fetchDetails(lcsc_code):
    """
    Fetch LCSC extra information for a given LCSC code
    """
    print(getLcscExtraNew(lcsc_code))


@click.group()
def cli():
    pass

cli.add_command(getLibrary)
cli.add_command(listcategories)
cli.add_command(listattributes)
cli.add_command(buildtables)
cli.add_command(updatechangelog)
cli.add_command(fetchDetails)

if __name__ == "__main__":
    cli()
