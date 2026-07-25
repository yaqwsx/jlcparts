from multiprocessing import Pool
import json
import os
import time

import click

from jlcparts.datatables import buildtables, normalizeAttribute
from jlcparts.lcsc import pullPreferredComponents
from jlcparts.partLib import (PartLibrary, PartLibraryDb, getLcscExtraNew,
                              loadJlcTable, loadJlcTableLazy, parsePrice)
from jlcparts.sourceDb import SourceDb, migrateCache
from jlcparts.webdb import buildwebdb


def fetchLcscData(lcsc):
    try:
        extra = getLcscExtraNew(lcsc)
        return (lcsc, extra, None)
    except Exception as e:
        return (lcsc, None, f"{type(e).__name__}: {e}")

def refreshExtraData(db, missing, age, limit):
    missing = set(missing)
    missing.update(db.getMissingExtra(max(0, limit - len(missing))))

    ageCount = min(age, max(0, limit - len(missing)))
    print(f"{ageCount} components will be aged and thus refreshed")
    missing = missing.union(db.getNOldest(ageCount))

    # Truncate the missing components to respect the limit:
    missing = list(missing)[:limit]
    if not missing:
        return

    with Pool(processes=10) as pool:
        for i, (lcsc, extra, error) in enumerate(pool.imap_unordered(fetchLcscData, missing)):
            if error is not None:
                print(f"  {lcsc} skipped. {((i+1) / len(missing) * 100):.2f} % ({error})")
                continue
            print(f"  {lcsc} fetched. {((i+1) / len(missing) * 100):.2f} %")
            db.updateExtra(lcsc, extra)

def apiComponentToDbComponent(component):
    from .jlcpcb import normalizeComponent

    c = normalizeComponent(component)
    return {
        "lcsc": c["lcscPart"],
        "category": c["firstCategory"],
        "subcategory": c["secondCategory"],
        "mfr": c["mfrPart"],
        "package": c["package"],
        "joints": int(c["solderJoint"]),
        "manufacturer": c["manufacturer"],
        "basic": c["libraryType"].lower() == "base",
        "description": c["description"],
        "datasheet": c["datasheet"],
        "stock": int(c["stock"]),
        "price": parsePrice(c["price"]),
        "jlc_extra": c["jlcExtra"],
        "jlc_raw": component,
    }

@click.command()
@click.argument("source", type=click.Path(dir_okay=False, exists=True))
@click.argument("db", type=click.Path(dir_okay=False, writable=True))
@click.option("--age", type=int, default=0,
    help="Automatically discard n oldest components and fetch them again")
@click.option("--limit", type=int, default=10000,
    help="Limit number of newly added components")
@click.option("--partial", is_flag=True,
    help="Do not remove DB components missing from SOURCE")
@click.option("--skip", type=int, default=0,
    help="Skip this many rows from SOURCE before importing")
def getLibrary(source, db, age, limit, partial, skip):
    """
    Download library inside OUTPUT (JSON format) based on SOURCE (csv table
    provided by JLC PCB).

    You can specify previously downloaded library as a cache to save requests to
    fetch LCSC extra data.
    """
    OLD = 0
    REFRESHED = 1

    db = PartLibraryDb(db)
    missing = set()
    total = 0
    skipped = 0
    with db.startTransaction():
        if not partial:
            db.resetFlag(value=OLD)
        with open(source, newline="") as f:
            jlcTable = loadJlcTableLazy(f)
            for component in jlcTable:
                if skipped < skip:
                    skipped += 1
                    continue
                total += 1
                if db.exists(component["lcsc"]):
                    db.updateJlcPart(component, flag=None if partial else REFRESHED)
                else:
                    component["extra"] = {}
                    db.addComponent(component, flag=None if partial else REFRESHED)
                    missing.add(component["lcsc"])
        if skipped != 0:
            print(f"Skipped {skipped} components")
        print(f"New {len(missing)} components out of {total} total")
        refreshExtraData(db, missing, age, limit)
        if not partial:
            db.removeWithFlag(value=OLD)
    # Temporary work-around for space-related issues in CI - simply don't rebuild the DB
    # db.vacuum()

@click.command()
@click.argument("db", type=click.Path(dir_okay=False, writable=True))
@click.option("--checkpoint", type=click.Path(dir_okay=False), default=None,
    help="Read/write a checkpoint JSON for resumable fetches")
@click.option("--max-seconds", type=int, default=None,
    help="Stop after roughly this many seconds and save the checkpoint")
@click.option("--age", type=int, default=0,
    help="Automatically discard n oldest components and fetch them again")
@click.option("--limit", type=int, default=10000,
    help="Limit number of newly added LCSC extra records")
@click.option("--retries", type=int, default=10,
    help="Retry failed JLCPCB API pages this many times")
@click.option("--retry-delay", type=int, default=5,
    help="Wait this many seconds between JLCPCB API retries")
@click.option("--verbose", is_flag=True,
    help="Be verbose")
def fetchDb(db, checkpoint, max_seconds, age, limit, retries, retry_delay, verbose):
    """
    Fetch JLC PCB component data directly into DB.
    """
    from .jlcpcb import (
        createComponentInterface,
        createWebsiteComponentInterface,
        enrichComponentsFromWebsite,
        loadCheckpoint,
    )

    if max_seconds is not None and checkpoint is None:
        raise RuntimeError("max-seconds requires a checkpoint so the fetch can resume")

    OLD = 0
    REFRESHED = 1

    lib = SourceDb(db)
    checkpointState = loadCheckpoint(checkpoint)
    count = int(checkpointState.get("count", 0))
    phase = checkpointState.get("phase", "openapi")
    missing = set()

    if checkpointState.get("done"):
        if checkpoint and os.path.exists(checkpoint):
            os.remove(checkpoint)
        return

    if not checkpointState:
        with lib.startTransaction():
            lib.resetFlag(value=OLD)

    start = time.monotonic()

    def writeFetchCheckpoint(lastKey=None, websiteSegment=0, websitePage=1):
        if checkpoint is None:
            return
        data = {
            "version": 2,
            "filename": db,
            "count": count,
            "phase": phase,
            "lastKey": lastKey,
            "websiteSegment": websiteSegment,
            "websitePage": websitePage,
            "done": False,
            "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        tmp = f"{checkpoint}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, checkpoint)

    def timeExpired():
        return (
            max_seconds is not None
            and time.monotonic() - start >= max_seconds
        )

    if phase == "openapi":
        interf = createComponentInterface(lastKey=checkpointState.get("lastKey"))
        while True:
            if timeExpired():
                writeFetchCheckpoint(lastKey=interf.lastPage)
                break

            for i in range(retries):
                try:
                    page = interf.getPage()
                    break
                except Exception as e:
                    if i == retries - 1:
                        raise e from None
                    time.sleep(retry_delay)
            if page is None:
                phase = "website"
                writeFetchCheckpoint()
                break

            page = enrichComponentsFromWebsite(page)

            with lib.startTransaction():
                for apiComponent in page:
                    isNew = not lib.exists(apiComponent["componentCode"])
                    lib.updateJlcPayload(apiComponent, flag=REFRESHED)
                    if isNew:
                        missing.add(apiComponent["componentCode"])

            count += len(page)
            if verbose:
                print(f"Fetched {count} OpenAPI components")
            writeFetchCheckpoint(lastKey=interf.lastPage)

    done = False
    if phase == "website" and not timeExpired():
        websiteInterf = createWebsiteComponentInterface(
            segmentIndex=int(checkpointState.get("websiteSegment", 0) or 0),
            currentPage=int(checkpointState.get("websitePage", 1) or 1),
        )
        while True:
            if timeExpired():
                writeFetchCheckpoint(
                    websiteSegment=websiteInterf.segmentIndex,
                    websitePage=websiteInterf.currentPage,
                )
                break

            for i in range(retries):
                try:
                    page = websiteInterf.getPage()
                    break
                except Exception as e:
                    if i == retries - 1:
                        raise e from None
                    time.sleep(retry_delay)
            if page is None:
                with lib.startTransaction():
                    lib.removeWithFlag(value=OLD)
                if checkpoint and os.path.exists(checkpoint):
                    os.remove(checkpoint)
                done = True
                break

            with lib.startTransaction():
                for component in page:
                    syncFlag = lib.getSyncFlag(component["componentCode"])
                    if syncFlag == REFRESHED:
                        continue
                    isNew = syncFlag is None
                    lib.updateJlcPayload(component, flag=REFRESHED)
                    if isNew:
                        missing.add(component["componentCode"])

            count += len(page)
            if verbose:
                print(f"Fetched {count} combined components")
            writeFetchCheckpoint(
                websiteSegment=websiteInterf.segmentIndex,
                websitePage=websiteInterf.currentPage,
            )

    refreshExtraData(lib, missing, age, limit)
    if verbose:
        print("Fetch complete" if done else "Fetch checkpointed")



@click.command()
@click.argument("db", type=click.Path(dir_okay=False, writable=True))
def updatePreferred(db):
    """
    Download list of preferred components from JLC PCB and mark them into the DB.
    """
    preferred = pullPreferredComponents()
    lib = SourceDb(db)
    lib.setPreferred(preferred)


@click.command()
@click.argument("source", type=click.Path(dir_okay=False, exists=True))
@click.argument("output", type=click.Path(dir_okay=False), required=False)
def migratecache(source, output):
    """
    Migrate a legacy cache.sqlite3 into the compact source-db-v2 format.
    """
    migrateCache(source, output)


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

@click.command()
@click.argument("filename", type=click.Path(writable=True))
@click.option("--verbose", is_flag=True,
    help="Be verbose")
@click.option("--limit", type=int, default=None,
    help="Fetch at most this many components")
@click.option("--checkpoint", type=click.Path(dir_okay=False), default=None,
    help="Read/write a checkpoint JSON for resumable fetches")
@click.option("--max-seconds", type=int, default=None,
    help="Stop after roughly this many seconds and save the checkpoint")
def fetchTable(filename, verbose, limit, checkpoint, max_seconds):
    """
    Fetch JLC PCB component table
    """
    from .jlcpcb import pullComponentTable

    def report(count: int) -> None:
        if (verbose):
            print(f"Fetched {count}")

    pullComponentTable(filename, report, limit=limit, checkpoint=checkpoint,
                       maxSeconds=max_seconds)

@click.command()
@click.argument("lcsc")
def testComponent(lcsc):
    """
    Tests parsing attributes of given component
    """
    extra = getLcscExtraNew(lcsc)["attributes"]

    extra.pop("url", None)
    extra.pop("images", None)
    extra.pop("prices", None)
    extra.pop("datasheet", None)
    extra.pop("id", None)
    extra.pop("manufacturer", None)
    extra.pop("number", None)
    extra.pop("title", None)
    extra.pop("quantity", None)
    for i in range(10):
        extra.pop(f"quantity{i}", None)
    normalized = dict(normalizeAttribute(key, val) for key, val in extra.items())
    print(json.dumps(normalized, indent=4))


@click.group()
def cli():
    pass

cli.add_command(getLibrary)
cli.add_command(listcategories)
cli.add_command(listattributes)
cli.add_command(buildtables)
cli.add_command(buildwebdb)
cli.add_command(updatePreferred)
cli.add_command(migratecache)
cli.add_command(fetchDetails)
cli.add_command(fetchDb)
cli.add_command(fetchTable)
cli.add_command(testComponent)

if __name__ == "__main__":
    cli()
