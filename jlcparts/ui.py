import click
import shutil
import os
import time
import sys
from jlcparts.partLib import PartLibrary, loadJlcTable, getLcscExtra, obtainCsrfTokenAndCookies
from jlcparts.datatables import buildtables

@click.command()
@click.argument("source", type=click.Path(dir_okay=False, exists=True))
@click.argument("output", type=click.Path(dir_okay=False, writable=True))
@click.option("--cache", type=click.Path(dir_okay=False, exists=True),
    help="Previously generated JSON file serving as a cache for LCSC informatioon")
@click.option("--age", type=int, default=0,
    help="Automatically discard n oldest components and fetch them again")
def getLibrary(cache, source, output, age):
    """
    Download library inside OUTPUT (JSON format) based on SOURCE (csv table
    provided by JLC PCB).

    Cou can specify previously downloaded library as a cache to save requests to
    fetch LCSC extra data.
    """
    cacheLib = PartLibrary(cache)
    cacheLib.deleteNOldest(age)
    lib = PartLibrary()

    with open(source, newline="") as f:
        jlcTable = loadJlcTable(f)

    # Make copy of the output in case we make a mistake
    if os.path.exists(output):
        shutil.copy(output, output + ".bak")

    token, cookies = obtainCsrfTokenAndCookies()
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
        if i % 1000 == 0:
            print(f"Processing - {((i+1) / total * 100):.2f} %")
        cached = cacheLib.getComponent(component["lcsc"])
        newlyFetched = False
        if not cached:
            newlyFetched = True
            print(f"  {component['lcsc']} not in cache, fetching...")
            extra, token, cookies = getLcscExtra(component["lcsc"], token, cookies,
                onPause=saveOnPause)
            fetched += 1
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

if __name__ == "__main__":
    cli()
