import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from urllib.parse import unquote

from .partLib import lcscFromDb, lcscToDb


SOURCE_DB_FORMAT = "source-db-v2"


def _jsonDumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _jsonLoadsDict(value):
    if not value:
        return {}
    try:
        result = json.loads(value)
    except Exception:
        return {}
    return result if isinstance(result, dict) else {}


def _normalizeLibraryType(value):
    value = (value or "").lower()
    if value == "basic":
        return "base"
    if value == "extended":
        return "expand"
    return value


def _priceRangesToCsv(priceRanges):
    if not isinstance(priceRanges, list):
        return ""
    prices = []
    for priceRange in priceRanges:
        if not isinstance(priceRange, dict):
            continue
        qFrom = priceRange.get("startQuantity")
        unitPrice = priceRange.get("unitPrice")
        if qFrom is None or unitPrice is None:
            continue
        qTo = priceRange.get("endQuantity")
        qToText = "" if qTo in [None, "", -1, "-1"] else str(qTo)
        prices.append(f"{qFrom}-{qToText}:{unitPrice}")
    return ",".join(prices)


def _parsePrice(priceString):
    prices = []
    if len((priceString or "").strip()) == 0:
        return []
    for price in priceString.split(","):
        if not price:
            continue
        rangeText, priceText = tuple(price.split(":"))
        qFrom, qTo = rangeText.split("-")
        prices.append({
            "qFrom": int(qFrom),
            "qTo": int(qTo) if qTo else None,
            "price": float(priceText)
        })
    prices.sort(key=lambda x: x["qFrom"])
    return prices


def _parameterAttributes(parameters):
    attributes = {}
    if not isinstance(parameters, list):
        return attributes
    for parameter in parameters:
        if not isinstance(parameter, dict):
            continue
        name = parameter.get("parameterName")
        value = parameter.get("parameterValue")
        if not name or value in [None, "", "-"]:
            continue
        if name in attributes:
            existing = str(attributes[name])
            if str(value) not in existing.split(", "):
                attributes[name] = f"{existing}, {value}"
        else:
            attributes[name] = value
    return attributes


def _slugifyModel(value):
    value = re.sub(r"[^A-Za-z0-9]+", "-", value or "")
    return re.sub(r"-+", "-", value).strip("-").lower()


def _guessManufacturerFromManualUrl(url, model, code):
    if not url:
        return ""
    filename = unquote(url).rsplit("/", 1)[-1]
    if not filename.lower().endswith(".pdf") or f"_{code}" not in filename:
        return ""

    title = filename[:-4].rsplit(f"_{code}", 1)[0]
    title = re.sub(r"^(?:lcsc_datasheet_)?\d+_", "", title)
    modelSlug = _slugifyModel(model)
    titleSlug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-")
    if not modelSlug or not titleSlug.lower().endswith(f"-{modelSlug}"):
        return ""

    manufacturer = titleSlug[:-(len(modelSlug) + 1)]
    return manufacturer.replace("--", "/").replace("-", " ").strip()


def _datasheet(component):
    return (
        component.get("datasheetUrl")
        or component.get("dataManualUrl")
        or component.get("dataManualOfficialLink")
        or ""
    )


def _manufacturerFromLcsc(extra):
    manufacturer = extra.get("manufacturer", {})
    if isinstance(manufacturer, dict):
        return (
            manufacturer.get("name")
            or manufacturer.get("en")
            or manufacturer.get("abbr")
            or ""
        )
    if isinstance(manufacturer, str):
        return manufacturer
    return ""


def _lcscAttributes(extra):
    attr = extra.get("attributes", extra)
    return attr if isinstance(attr, dict) else {}


def _imageName(extra):
    images = extra.get("images")
    if not images:
        return None
    firstImage = images[0] if isinstance(images, list) and images else None
    if not isinstance(firstImage, dict):
        return None
    imageUrls = [value for value in firstImage.values() if isinstance(value, str)]
    if not imageUrls:
        return None
    return imageUrls[0].rsplit("/", 1)[1]


def _urlSlug(extra):
    url = extra.get("url")
    if not isinstance(url, str):
        return None
    try:
        return url[url.rindex("/") + 1:url.rindex("_")]
    except ValueError:
        return None


def _jlcSourceFromPayload(payload, lcsc=None):
    code = payload.get("componentCode") or ""
    if lcsc is None:
        lcsc = lcscToDb(code)
    manufacturer = (
        payload.get("manufacturer")
        or _guessManufacturerFromManualUrl(
            payload.get("dataManualUrl"),
            payload.get("componentModel"),
            code
        )
        or ""
    )
    attrition = {
        key: payload.get(key)
        for key in ["lossNumber", "leastNumber", "leastPatchNumber", "minPurchaseNum"]
        if payload.get(key) is not None
    }
    return {
        "lcsc": lcsc,
        "category": payload.get("firstTypeName") or "",
        "subcategory": payload.get("secondTypeName") or "",
        "mfr": payload.get("componentModel") or "",
        "package": payload.get("componentSpecification") or "",
        "joints": int(payload.get("solderJointCount", 0) or 0),
        "manufacturer": manufacturer,
        "library_type": _normalizeLibraryType(payload.get("libraryType")),
        "description": payload.get("description") or "",
        "datasheet": _datasheet(payload),
        "stock": int(payload.get("stockCount", 0) or 0),
        "price": _priceRangesToCsv(payload.get("priceRanges", [])),
        "attributes": _parameterAttributes(payload.get("parameters", [])),
        "rohs": payload.get("rohsFlag"),
        "eccn": payload.get("eccnCode") or "",
        "assembly": payload.get("assemblyComponentFlag"),
        "assembly_process": payload.get("assemblyProcess"),
        "assembly_mode": payload.get("assemblyMode"),
        "component_product_type": payload.get("componentProductType"),
        "website_component_id": payload.get("websiteComponentId"),
        "attrition": attrition,
    }


def _lcscSourceFromExtra(lcsc, fetchedAt, extra):
    if not isinstance(extra, dict) or not extra:
        return None
    return {
        "lcsc": lcsc,
        "fetched_at": int(fetchedAt or 0),
        "manufacturer": _manufacturerFromLcsc(extra),
        "attributes": _lcscAttributes(extra),
        "image": _imageName(extra),
        "url_slug": _urlSlug(extra),
    }


def detectSourceDb(path):
    if not os.path.exists(path):
        return None
    conn = sqlite3.connect(path)
    try:
        row = conn.execute("""
            SELECT value FROM meta WHERE key = 'format' LIMIT 1
            """).fetchone()
        if row and row[0] == SOURCE_DB_FORMAT:
            return SOURCE_DB_FORMAT
    except sqlite3.Error:
        pass
    finally:
        conn.close()
    return "legacy"


def migrateCache(sourcePath, outputPath=None):
    sourceFormat = detectSourceDb(sourcePath)
    if sourceFormat == SOURCE_DB_FORMAT:
        print(f"{sourcePath} is already {SOURCE_DB_FORMAT}; nothing to migrate")
        return False
    if sourceFormat != "legacy":
        raise RuntimeError(f"Unknown cache format for {sourcePath}: {sourceFormat}")

    if outputPath is None:
        outputPath = f"{sourcePath}.v2.tmp"
        replaceSource = True
    else:
        replaceSource = False

    if os.path.exists(outputPath):
        raise RuntimeError(f"{outputPath} already exists")

    migrateLegacyCache(sourcePath, outputPath)

    if replaceSource:
        os.replace(outputPath, sourcePath)
    return True


class SourceDb:
    def __init__(self, filepath=None, create=True):
        self.conn = sqlite3.connect(filepath)
        self.conn.row_factory = sqlite3.Row
        self.transaction = False
        if create:
            self.createSchema()
        self._categoryCache = None

    def createSchema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY NOT NULL,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS jlc_components (
                lcsc INTEGER PRIMARY KEY NOT NULL,
                fetched_at INTEGER NOT NULL,
                present INTEGER NOT NULL,
                sync_seen INTEGER NOT NULL DEFAULT 0,
                category TEXT NOT NULL,
                subcategory TEXT NOT NULL,
                mfr TEXT NOT NULL,
                package TEXT NOT NULL,
                joints INTEGER NOT NULL,
                manufacturer TEXT NOT NULL,
                library_type TEXT NOT NULL,
                preferred INTEGER NOT NULL,
                last_on_stock INTEGER NOT NULL,
                description TEXT NOT NULL,
                datasheet TEXT NOT NULL,
                stock INTEGER NOT NULL,
                price TEXT NOT NULL,
                attributes TEXT NOT NULL,
                rohs INTEGER,
                eccn TEXT NOT NULL,
                assembly INTEGER,
                assembly_process TEXT,
                assembly_mode TEXT,
                component_product_type INTEGER,
                website_component_id TEXT,
                attrition TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS lcsc_components (
                lcsc INTEGER PRIMARY KEY NOT NULL,
                fetched_at INTEGER NOT NULL,
                manufacturer TEXT NOT NULL,
                attributes TEXT NOT NULL,
                image TEXT,
                url_slug TEXT
            );
        """)
        self._ensureColumn("jlc_components", "sync_seen", "INTEGER NOT NULL DEFAULT 0")
        self._ensureColumn("jlc_components", "component_product_type", "INTEGER")
        self.conn.execute("""
            INSERT INTO meta(key, value) VALUES ('format', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (SOURCE_DB_FORMAT,))
        self.conn.commit()

    def _ensureColumn(self, table, column, declaration):
        columns = [row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})")]
        if column not in columns:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    def _commit(self):
        if not self.transaction:
            self.conn.commit()

    @contextmanager
    def startTransaction(self):
        assert not self.transaction
        try:
            with self.conn:
                self.transaction = True
                yield self
        finally:
            self.transaction = False

    def close(self):
        self.conn.close()

    def vacuum(self):
        self.conn.execute("VACUUM")

    def prepareBuild(self):
        self.conn.executescript("""
            CREATE INDEX IF NOT EXISTS jlc_components_build_category
            ON jlc_components(present, category, subcategory, last_on_stock, lcsc);
        """)
        self.conn.commit()

    def finalizeBuild(self):
        self.conn.executescript("""
            DROP INDEX IF EXISTS jlc_components_build_category;
        """)
        self.conn.commit()
        self.conn.execute("VACUUM")

    def resetFlag(self, value=0):
        self.conn.execute("UPDATE jlc_components SET sync_seen = ?", (value,))
        self._commit()

    def removeWithFlag(self, value=0):
        self.conn.execute("""
            DELETE FROM lcsc_components
            WHERE lcsc IN (SELECT lcsc FROM jlc_components WHERE sync_seen = ?)
            """, (value,))
        self.conn.execute("DELETE FROM jlc_components WHERE sync_seen = ?", (value,))
        self._categoryCache = None
        self._commit()

    def exists(self, lcscNumber):
        return self.conn.execute("""
            SELECT lcsc FROM jlc_components WHERE lcsc = ? LIMIT 1
            """, (lcscToDb(lcscNumber),)).fetchone() is not None

    def updateJlcPayload(self, payload, flag=1):
        row = _jlcSourceFromPayload(payload)
        self._upsertJlc(row, present=1, syncSeen=flag)

    def _upsertJlc(self, row, present=1, syncSeen=1):
        now = int(time.time())
        lastOnStock = now if int(row["stock"]) != 0 else None
        self.conn.execute("""
            INSERT INTO jlc_components (
                lcsc, fetched_at, present, sync_seen, category, subcategory,
                mfr, package, joints, manufacturer, library_type, preferred,
                last_on_stock,
                description, datasheet, stock, price, attributes, rohs, eccn,
                assembly, assembly_process, assembly_mode, component_product_type,
                website_component_id, attrition
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(
                    (SELECT preferred FROM jlc_components WHERE lcsc = ?), 0),
                COALESCE(?, (SELECT last_on_stock FROM jlc_components WHERE lcsc = ?), 0),
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(lcsc) DO UPDATE SET
                fetched_at = excluded.fetched_at,
                present = excluded.present,
                sync_seen = excluded.sync_seen,
                category = excluded.category,
                subcategory = excluded.subcategory,
                mfr = excluded.mfr,
                package = excluded.package,
                joints = excluded.joints,
                manufacturer = CASE
                    WHEN excluded.manufacturer != '' THEN excluded.manufacturer
                    ELSE jlc_components.manufacturer
                END,
                library_type = excluded.library_type,
                last_on_stock = excluded.last_on_stock,
                description = excluded.description,
                datasheet = excluded.datasheet,
                stock = excluded.stock,
                price = excluded.price,
                attributes = excluded.attributes,
                rohs = excluded.rohs,
                eccn = excluded.eccn,
                assembly = excluded.assembly,
                assembly_process = excluded.assembly_process,
                assembly_mode = excluded.assembly_mode,
                component_product_type = excluded.component_product_type,
                website_component_id = excluded.website_component_id,
                attrition = excluded.attrition
            """, (
                row["lcsc"], now, present, syncSeen, row["category"], row["subcategory"],
                row["mfr"], row["package"], row["joints"], row["manufacturer"],
                row["library_type"], row["lcsc"], lastOnStock, row["lcsc"],
                row["description"], row["datasheet"], row["stock"], row["price"],
                _jsonDumps(row["attributes"]),
                None if row["rohs"] is None else int(bool(row["rohs"])),
                row["eccn"],
                None if row["assembly"] is None else int(bool(row["assembly"])),
                row["assembly_process"],
                row["assembly_mode"],
                row["component_product_type"],
                None if row["website_component_id"] is None else str(row["website_component_id"]),
                _jsonDumps(row["attrition"]),
            ))
        self._categoryCache = None
        self._commit()

    def updateExtra(self, lcscNumber, extra):
        lcsc = lcscToDb(lcscNumber)
        row = _lcscSourceFromExtra(lcsc, int(time.time()), extra)
        if row is None:
            self.conn.execute("DELETE FROM lcsc_components WHERE lcsc = ?", (lcsc,))
        else:
            self.conn.execute("""
                INSERT INTO lcsc_components (
                    lcsc, fetched_at, manufacturer, attributes, image, url_slug
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(lcsc) DO UPDATE SET
                    fetched_at = excluded.fetched_at,
                    manufacturer = excluded.manufacturer,
                    attributes = excluded.attributes,
                    image = excluded.image,
                    url_slug = excluded.url_slug
                """, (
                    row["lcsc"], row["fetched_at"], row["manufacturer"],
                    _jsonDumps(row["attributes"]), row["image"], row["url_slug"],
                ))
        self._commit()

    def getNOldest(self, count):
        cursor = self.conn.execute("""
            SELECT j.lcsc
            FROM jlc_components j
            LEFT JOIN lcsc_components l ON l.lcsc = j.lcsc
            ORDER BY COALESCE(l.fetched_at, 0) ASC
            LIMIT ?
            """, (count,))
        return map(lambda row: lcscFromDb(row["lcsc"]), cursor)

    def getMissingExtra(self, count):
        if count == 0:
            return []
        cursor = self.conn.execute("""
            SELECT j.lcsc
            FROM jlc_components j
            LEFT JOIN lcsc_components l ON l.lcsc = j.lcsc
            WHERE l.lcsc IS NULL OR l.attributes = '{}'
            ORDER BY COALESCE(l.fetched_at, 0) ASC
            LIMIT ?
            """, (count,))
        return map(lambda row: lcscFromDb(row["lcsc"]), cursor)

    def setPreferred(self, lcscSet):
        self.conn.execute("UPDATE jlc_components SET preferred = 0")
        if lcscSet:
            self.conn.execute(
                f"UPDATE jlc_components SET preferred = 1 WHERE lcsc IN ({','.join(len(lcscSet) * ['?'])})",
                [lcscToDb(x) for x in lcscSet]
            )
        self._commit()

    def categories(self):
        rows = self.conn.execute("""
            SELECT category, subcategory, COUNT(*) AS component_count
            FROM jlc_components
            WHERE present = 1
            GROUP BY category, subcategory
            ORDER BY category, subcategory
            """)
        result = {}
        self._categoryCache = {}
        for i, row in enumerate(rows, start=1):
            category = row["category"]
            subcategory = row["subcategory"]
            result.setdefault(category, []).append(subcategory)
            self._categoryCache[(category, subcategory)] = i
        return result

    def getCategoryId(self, category, subcategory):
        if self._categoryCache is None:
            self.categories()
        return self._categoryCache.get((category, subcategory))

    def countCategoryComponents(self, category, subcategory, stockNewerThan=None):
        params = [category, subcategory]
        stockFilter = ""
        if stockNewerThan is not None:
            stockFilter = "AND last_on_stock > ?"
            params.append(int(time.time()) - stockNewerThan * 24 * 3600)
        return self.conn.execute(f"""
            SELECT COUNT(*)
            FROM jlc_components
            WHERE present = 1
                AND category = ?
                AND subcategory = ?
                {stockFilter}
            """, params).fetchone()[0]

    def iterCategoryComponents(self, category, subcategory, stockNewerThan=None, fetchSize=1000):
        params = [category, subcategory]
        stockFilter = ""
        if stockNewerThan is not None:
            stockFilter = "AND j.last_on_stock > ?"
            params.append(int(time.time()) - stockNewerThan * 24 * 3600)
        cursor = self.conn.execute(f"""
            SELECT
                j.*,
                l.manufacturer AS lcsc_manufacturer,
                l.attributes AS lcsc_attributes,
                l.image AS lcsc_image,
                l.url_slug AS lcsc_url_slug
            FROM jlc_components j
            LEFT JOIN lcsc_components l ON l.lcsc = j.lcsc
            WHERE j.present = 1
                AND j.category = ?
                AND j.subcategory = ?
                {stockFilter}
            ORDER BY j.lcsc
            """, params)
        while True:
            rows = cursor.fetchmany(fetchSize)
            if not rows:
                break
            for row in rows:
                yield self._rowToComponent(row)

    def _rowToComponent(self, row):
        lcscAttrs = _jsonLoadsDict(row["lcsc_attributes"])
        jlcAttrs = _jsonLoadsDict(row["attributes"])
        jlcExtra = {
            "rohs": None if row["rohs"] is None else bool(row["rohs"]),
            "eccn": row["eccn"],
            "assembly": None if row["assembly"] is None else bool(row["assembly"]),
            "assemblyProcess": row["assembly_process"],
            "assemblyMode": row["assembly_mode"],
            "componentProductType": row["component_product_type"],
            "websiteComponentId": row["website_component_id"],
            "attrition": _jsonLoadsDict(row["attrition"]),
            "attributes": jlcAttrs,
        }
        extra = {"attributes": lcscAttrs}
        if row["lcsc_image"]:
            extra["images"] = [{"original": f"compact/{row['lcsc_image']}"}]
        if row["lcsc_url_slug"]:
            extra["url"] = f"https://lcsc.com/product-detail/{row['lcsc_url_slug']}_{lcscFromDb(row['lcsc'])}.html"
        if row["lcsc_manufacturer"]:
            extra["manufacturer"] = row["lcsc_manufacturer"]
        manufacturer = row["manufacturer"] or row["lcsc_manufacturer"] or ""
        return {
            "lcsc": lcscFromDb(row["lcsc"]),
            "category": row["category"],
            "subcategory": row["subcategory"],
            "mfr": row["mfr"],
            "package": row["package"],
            "joints": row["joints"],
            "manufacturer": manufacturer,
            "basic": row["library_type"] == "base",
            "preferred": bool(row["preferred"]),
            "description": row["description"],
            "datasheet": row["datasheet"],
            "stock": row["stock"],
            "last_on_stock": row["last_on_stock"],
            "price": _parsePrice(row["price"]),
            "extra": extra if extra != {"attributes": {}} else {},
            "jlc_extra": jlcExtra,
        }


def migrateLegacyCache(sourcePath, outputPath):
    if os.path.exists(outputPath):
        raise RuntimeError(f"{outputPath} already exists")

    source = sqlite3.connect(sourcePath)
    source.row_factory = sqlite3.Row
    dest = SourceDb(outputPath)
    started = time.monotonic()
    count = 0
    lcscCount = 0
    query = """
        SELECT
            c.lcsc, c.preferred, c.last_on_stock, c.flag,
            c.extra, c.last_update,
            d.fetched_at AS jlc_fetched_at,
            d.payload AS jlc_payload
        FROM components c
        LEFT JOIN jlcpcb_component_details d ON d.lcsc = c.lcsc
        ORDER BY c.lcsc
    """
    with dest.startTransaction():
        for row in source.execute(query):
            if row["jlc_payload"]:
                payload = _jsonLoadsDict(row["jlc_payload"])
                if payload:
                    jlc = _jlcSourceFromPayload(payload, row["lcsc"])
                    dest._upsertJlc(
                        jlc,
                        present=1,
                        syncSeen=1 if int(row["flag"] or 0) != 0 else 0
                    )
                    dest.conn.execute("""
                        UPDATE jlc_components
                        SET fetched_at = ?, preferred = ?, last_on_stock = ?
                        WHERE lcsc = ?
                        """, (
                            int(row["jlc_fetched_at"] or 0),
                            int(row["preferred"] or 0),
                            int(row["last_on_stock"] or 0),
                            row["lcsc"],
                        ))
            extra = _jsonLoadsDict(row["extra"])
            lcsc = _lcscSourceFromExtra(row["lcsc"], row["last_update"], extra)
            if lcsc is not None:
                lcscCount += 1
                dest.conn.execute("""
                    INSERT INTO lcsc_components (
                        lcsc, fetched_at, manufacturer, attributes, image, url_slug
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(lcsc) DO UPDATE SET
                        fetched_at = excluded.fetched_at,
                        manufacturer = excluded.manufacturer,
                        attributes = excluded.attributes,
                        image = excluded.image,
                        url_slug = excluded.url_slug
                    """, (
                        lcsc["lcsc"], lcsc["fetched_at"], lcsc["manufacturer"],
                        _jsonDumps(lcsc["attributes"]), lcsc["image"], lcsc["url_slug"],
                    ))
            count += 1
            if count % 50000 == 0:
                print(f"{count} rows", flush=True)
        dest.conn.executemany("""
            INSERT INTO meta(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, [
                ("format", SOURCE_DB_FORMAT),
                ("migrated_from", sourcePath),
                ("jlc_components", str(count)),
                ("lcsc_components", str(lcscCount)),
                ("migration_seconds", f"{time.monotonic() - started:.2f}"),
            ])
    source.close()
    dest.conn.execute("VACUUM")
    dest.close()
