import click
import shutil
import os
import time
import datetime
import sys
import json
from requests.exceptions import ConnectionError
from jlcparts.partLib import PartLibrary, loadJlcTable, getLcscExtra, obtainCsrfTokenAndCookies
from jlcparts.datatables import buildtables

@click.command()
@click.argument("source", type=click.Path(dir_okay=False, exists=True))
@click.argument("output", type=click.Path(dir_okay=False, writable=True))
@click.option("--cache", type=click.Path(dir_okay=False, exists=True),
    help="Previously generated JSON file serving as a cache for LCSC informatioon")
@click.option("--age", type=int, default=0,
    help="Automatically discard n oldest components and fetch them again")
@click.option("--newLogFile", type=click.Path(dir_okay=False), default=None,
    help="Save a file with newly added components (one LCSC code per line")
def getLibrary(cache, source, output, age, newlogfile):
    """
    Download library inside OUTPUT (JSON format) based on SOURCE (csv table
    provided by JLC PCB).

    Cou can specify previously downloaded library as a cache to save requests to
    fetch LCSC extra data.
    """
    cacheLib = PartLibrary(cache)
    deletedComponents = cacheLib.deleteNOldest(age)
    lib = PartLibrary()

    with open(source, newline="") as f:
        jlcTable = loadJlcTable(f)

    # Make copy of the output in case we make a mistake
    if os.path.exists(output):
        shutil.copy(output, output + ".bak")

    missing = set()
    for component in jlcTable.values():
        lcsc = component['lcsc']
        if cacheLib.getComponent(lcsc) is None:
            missing.add(lcsc)
    print(f"Missing {len(missing)} components out of {len(jlcTable.values())}")

    token, cookies = obtainCsrfTokenAndCookies()
    newComponents = []
    total = len(jlcTable)
    fetched = 0
    lastSavedWhen = 0
    def saveOnPause(lib=lib, output=output):
        nonlocal fetched
        nonlocal lastSavedWhen
        if fetched != lastSavedWhen:
            print(f"Automatically saving")
            lib.save(output)
            lastSavedWhen = fetched
    for i, component in enumerate(jlcTable.values()):
        lcsc = component['lcsc']
        cached = cacheLib.getComponent(lcsc)
        newlyFetched = False
        if not cached:
            if lcsc not in deletedComponents:
                newComponents.append(lcsc)
            newlyFetched = True
            print(f"  {lcsc} not in cache, fetching...")
            while True:
                try:
                    extra, token, cookies = getLcscExtra(lcsc, token, cookies,
                        onPause=saveOnPause)
                    break
                except ConnectionError as e:
                    print(f"Connection failed; retrying: {e}")
                    time.sleep(5)
            fetched += 1
            if fetched % 10 == 0:
                print(f"Pulling - {((fetched+1) / len(missing) * 100):.2f} %")
            if extra is None:
                sys.exit("Invalid extra data fetched, aborting")
            fetchedAt = int(time.time())
        else:
            extra = cached["extra"]
            fetchedAt = cached["extraTimestamp"] if "extraTimestamp" in cached else 0
        component["extra"] = extra
        component["extraTimestamp"] = fetchedAt
        lib.addComponent(component)
        if newlyFetched and fetched % 200 == 0:
            saveOnPause()
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


@click.group()
def cli():
    pass

cli.add_command(getLibrary)
cli.add_command(listcategories)
cli.add_command(listattributes)
cli.add_command(buildtables)
cli.add_command(updatechangelog)

if __name__ == "__main__":
    cli()
