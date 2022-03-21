from multiprocessing import Pool

import click

from jlcparts.datatables import buildtables
from jlcparts.partLib import (PartLibrary, PartLibraryDb, getLcscExtraNew,
                              loadJlcTable, loadJlcTableLazy)


def fetchLcscData(lcsc):
    extra = getLcscExtraNew(lcsc)
    return (lcsc, extra)

@click.command()
@click.argument("source", type=click.Path(dir_okay=False, exists=True))
@click.argument("db", type=click.Path(dir_okay=False, writable=True))
@click.option("--age", type=int, default=0,
    help="Automatically discard n oldest components and fetch them again")
@click.option("--limit", type=int, default=10000,
    help="Limit number of newly added components")
def getLibrary(source, db, age, limit):
    """
    Download library inside OUTPUT (JSON format) based on SOURCE (csv table
    provided by JLC PCB).

    Cou can specify previously downloaded library as a cache to save requests to
    fetch LCSC extra data.
    """
    OLD = 0
    REFRESHED = 1

    db = PartLibraryDb(db)
    missing = set()
    total = 0
    with db.startTransaction():
        db.resetFlag(value=OLD)
        with open(source, newline="") as f:
            jlcTable = loadJlcTableLazy(f)
            for component in jlcTable:
                total += 1
                if db.exists(component["lcsc"]):
                    db.updateJlcPart(component, flag=REFRESHED)
                else:
                    component["extra"] = {}
                    db.addComponent(component, flag=REFRESHED)
                    missing.add(component["lcsc"])
        print(f"New {len(missing)} components out of {total} total")
        ageCount = min(age, max(0, limit - len(missing)))
        print(f"{ageCount} components will be aged and thus refreshed")
        missing = missing.union(db.getNOldest(ageCount))

        with Pool(processes=10) as pool:
            for i, (lcsc, extra) in enumerate(pool.imap_unordered(fetchLcscData, missing)):
                print(f"  {lcsc} fetched. {((i+1) / len(missing) * 100):.2f} %")
                db.updateExtra(lcsc, extra)
        db.removeWithFlag(value=OLD)
    db.vacuum()


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
    LIBRARYFILENAME to standard output
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
cli.add_command(fetchDetails)

if __name__ == "__main__":
    cli()
