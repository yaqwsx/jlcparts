#!/usr/bin/env python3

import json
import sys
import click
import csv
import re
import time
import shutil
import sqlite3
import os
from pathlib import Path
from textwrap import indent
import urllib.parse
from contextlib import contextmanager
from .lcsc import makeLcscRequest

if os.environ.get("JLCPARTS_DEV", "0") == "1":
    print("Using caching from /tmp/jlcparts")
    CACHE_PATH = Path("/tmp/jlcparts")
    CACHE_PATH.mkdir(parents=True, exist_ok=True)
else:
    CACHE_PATH = None

def normalizeCategoryName(catname):
    return catname
    # If you want to normalize category names, don't; you will break LCSC links!
    # return catname.replace("?", "")

def lcscToDb(val):
    return int(val[1:])

def lcscFromDb(val):
    return f"C{val}"

class PartLibraryDb:
    def __init__(self, filepath=None):
        self.conn = sqlite3.connect(filepath)
        self.transation = False
        self.categoryCache = {}
        self.manufacturerCache = {}

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS components (
                lcsc INTEGER PRIMARY KEY NOT NULL,
                category_id INTEGER NOT NULL,
                mfr TEXT NOT NULL,
                package TEXT NOT NULL,
                joints INTEGER NOT NULL,
                manufacturer_id INTEGER NOT NULL,
                basic INTEGER NOT NULL,
                description TEXT NOT NULL,
                datasheet TEXT NOT NULL,
                stock INTEGER NOT NULL,
                price TEXT NOT NULL,
                last_update INTEGER NOT NULL,
                extra TEXT
            )""")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS manufacturers (
                id INTEGER PRIMARY KEY NOT NULL,
                name TEXT NOT NULL,
            UNIQUE (id, name)
            )""")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT NOT NULL,
            UNIQUE (id, category, subcategory)
            )""")
        self.conn.commit()

    def _commit(self):
        """
        Commits automatically if no transation is opened
        """
        if not self.transation:
            self.conn.commit()

    @contextmanager
    def startTransaction(self):
        assert self.transation == False
        try:
            with self.conn:
                self.transation = True
                yield self
        finally:
            self.transation = False

    def close(self):
        self.conn.close()

    def getComponent(self, lcscNumber):
        result = self.conn.execute("""
            SELECT
                c.lcsc AS lcsc,
                cat.category AS category,
                cat.subcategory AS subcategory,
                c.mfr AS mfr,
                c.package AS package,
                c.joints AS joints,
                m.name AS manufacturer,
                c.basic AS basic,
                c.description AS description,
                c.datasheet AS datasheet,
                c.stock AS stock,
                c.price AS price
                c.extra AS extra
            FROM components c
            WHERE lcsc = ?
            LEFT JOIN manufacturers m ON c.manufacturer_id = m.id
            LEFT JOIN categories cat ON c.category_id = cat.id
            LIMIT 1
            """, (lcscToDb(lcscNumber),)).fetchone()
        result = [result[k] for k in result.keys()]
        result["lcsc"] = lcscFromDb(result["lcsc"])
        result["price"] = json.loads(result["price"])
        result["extra"] = json.loads(result["extra"])
        return result

    def addComponent(self, component):
        m = component["manufacturer"]
        manId = self.manufacturerCache.get(m, None)
        if manId is None:
            manId = self.conn.execute("""
                SELECT id FROM manufacturers WHERE name = ?
                """, (m,)).fetchone()
            if manId is not None:
                manId = manId[0]
        if manId is None:
            self.conn.execute("""
                INSERT INTO manufacturers (name) VALUES (?)
                """,(m,))
            manId = self.conn.lastrowid
        self.manufacturerCache[m] = manId

        c = (component["category"], component["subcategory"])
        catId = self.manufacturerCache.get(c, None)
        if catId is None:
            catId = self.conn.execute("""
                SELECT id FROM categories WHERE category = ? AND subcategory = ?
                """, c).fetchone()
            if catId is not None:
                catId = catId[0]
        if catId is None:
            self.conn.execute("""
                INSERT INTO categories (category, subcategory) VALUES (?, ?)
                """, c)
            catId = self.conn.lastrowid
        self.categoryCache[c] = catId

        c = component
        self.conn.execute("""
            INSERT INTO components (lcsc, category_id, mfr, package, joints, manufacturer_id, basic, description, datasheet, stock, price, last_update, extra)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                lcscToDb(c["lcsc"]), catId, c["mfr"], c["package"], c["joints"], manId,
                c["basic"], c["description"], c["datasheet"], c["stock"],
                json.dumps(c["price"]), int(time.time()), json.dumps(c["extra"])
            ))
        self._commit()

    def updateJlcPart(self, component):
        c = component
        self.conn.execute("""
            UPDATE components
            SET mfr = ?,
                package = ?,
                joints = ?,
                basic = ?,
                description = ?,
                datasheet = ?,
                stock = ?,
                price = ?
            WHERE lcsc = ?
            """, (
                c["mfr"],
                c["package"],
                c["joints"],
                c["basic"],
                c["description"],
                c["datasheet"],
                c["stock"],
                c["price"],
                lcscToDb(c["lcsc"])
            ))
        self._commit()

    def categories(self):
        res = {}
        for x in self.conn.execute("SELECT category, subcategory FROM categories"):
            category = x["category"]
            subcat = x["subcat"]
            if category in res[category]:
                res[category].append(subcat)
            else:
                res[category] = [subcat]
        return res

    def delete(self, lcscNumber):
        self.conn.execute("DELETE FROM components WHERE lcsc = ?", (lcscToDb(lcscNumber),))
        self._commit()

    def deleteNOldest(self, count):
        self.conn.execute("DELETE FROM components ORDER_BY last_update ASC LIMIT ?", (count,))
        self._commit()



class PartLibrary:
    def __init__(self, filepath=None):
        if filepath is None:
            self.lib = {}
            self.index = {}
            return
        with open(filepath, "r") as f:
            self.lib = json.load(f)

        # Normalize category names
        for _, category in self.lib.items():
            keys = list(category.keys())
            for k in keys:
                category[normalizeCategoryName(k)] = category.pop(k)
        keys = list(self.lib.keys())
        for k in keys:
            self.lib[normalizeCategoryName(k)] = self.lib.pop(k)

        self.buildIndex()
        self.checkLibraryStructure()

    def buildIndex(self):
        index = {}
        for catName, category in self.lib.items():
            for subCatName, subcategory in category.items():
                for component in subcategory.keys():
                    if component in index:
                        raise RuntimeError(f"Component {component} is in multiple categories")
                    index[component] = (catName, subCatName)
        self.index = index

    def checkLibraryStructure(self):
        # ToDo
        pass

    def getComponent(self, lcscNumber):
        if lcscNumber not in self.index:
            return None
        cat, subcat = self.index[lcscNumber]
        return self.lib[cat][subcat][lcscNumber]

    def exists(self, lcscNumber):
        return lcscNumber in self.index

    def addComponent(self, component):
        cat = component["category"]
        subcat = component["subcategory"]
        if cat not in self.lib:
            self.lib[cat] = {}
        if subcat not in self.lib[cat]:
            self.lib[cat][subcat] = {}
        self.lib[cat][subcat][component["lcsc"]] = component
        self.index[component["lcsc"]] = (cat, subcat)

    def categories(self):
        """
        Return a dict with list of available categories in form category ->
        [subcategory]
        """
        return { category: subcategories.keys() for category, subcategories in self.lib.items()}

    def delete(self, lcscNumber):
        cat, subcat = self.index[lcscNumber]
        del self.lib[cat][subcat][lcscNumber]
        del self.index[lcscNumber]

    def deleteNOldest(self, count):
        if count == 0:
            return set()
        components = [self.getComponent(x) for x in self.index.keys()]
        components.sort(key=lambda x: x["extraTimestamp"] if "extraTimestamp" in x else 0)
        deleted = []
        for i in range(count):
            deleted.append(components[i]["lcsc"])
            self.delete(components[i]["lcsc"])
        return set(deleted)

    def save(self, filename):
        with open(filename, "w") as f:
            json.dump(self.lib, f)

def loadPartLibrary(file):
    lib = json.load(file)
    checkLibraryStructure(lib)
    return lib

def parsePrice(priceString):
    prices = []
    if len(priceString.strip()) == 0:
        return []
    for price in priceString.split(","):
        if len(price) == 0:
            continue
        range, p = tuple(price.split(":"))
        qFrom, qTo = range.split("-")
        prices.append({
            "qFrom": int(qFrom),
            "qTo": int(qTo) if qTo else None,
            "price": float(p)
        })
    prices.sort(key=lambda x: x["qFrom"])
    return prices


def normalizeUrlPart(part):
    return (part
        .replace("(", "")
        .replace(")", "")
        .replace(" ", "-")
        .replace("/", "-")
    )

class FetchError(RuntimeError):
    def __init__(self, message, reason=None):
        super().__init__(message)
        self.reason = reason

def getLcscExtraNew(lcscNumber, retries=10):
    timeouts = [
        "502 Bad Gateway",
        "504 Gateway Time-out",
        "504 ERROR",
        "Too Many Requests",
        "Please try again in a few minutes",
        "403 Forbidden"
    ]

    try:
        if retries == 0:
            raise FetchError("Too many retries", None)
        # Try to load fetched data from cache - useful when developing (saves time
        # to fetch)
        try:
            if CACHE_PATH is None:
                raise RuntimeError("Cache not used")
            with open(CACHE_PATH / f"{lcscNumber}.json") as f:
                resJson = json.load(f)
            params = resJson["result"]
        except:
            # Not in cache, fetch
            res = None
            resJson = None
            try:
                res = makeLcscRequest(f"https://wwwapi.lcsc.com/v1/agents/products/info/{lcscNumber}")
                if res.status_code != 200:
                    if any([x in res.text for x in timeouts]):
                        raise TimeoutError(res.text)
                resJson = res.json()
                if resJson["code"] in [563, 564]:
                    # The component was not found on LCSC - probably discontinued
                    return {}
                if resJson["code"] != 200:
                    raise RuntimeError(f"{resJson['code']}: {resJson['message']}")
                params = resJson["result"]
            except TimeoutError as e:
                raise e from None
            except Exception as e:
                message = f"{res.status_code}: {res.text}"
                raise FetchError(message, e) from None
            # Save to cache, make development more pleasant
            if CACHE_PATH is not None:
                with open(CACHE_PATH / f"{lcscNumber}.json", "w") as f:
                    json.dump(resJson, f)

        catalogName = urllib.parse.quote_plus(normalizeUrlPart(params["category"]["name2"]))
        man = urllib.parse.quote_plus(normalizeUrlPart(params["manufacturer"]["name"]))
        product = urllib.parse.quote_plus(normalizeUrlPart(params["title"]))
        code = urllib.parse.quote_plus(params["number"])
        params["url"] = f"https://lcsc.com/product-detail/{catalogName}_{man}-{product}_{code}.html"

        return params
    except TimeoutError as e:
        time.sleep(60)
        return getLcscExtraNew(lcscNumber, retries=retries-1)
    except FetchError as e:
        reason = f"{e}: \n{e.reason}"
        print(f"Failed {lcscNumber}:\n" + indent(reason, 8 * " "))
        raise e from None

def loadJlcTable(file):
    reader = csv.DictReader(file, delimiter=',', quotechar='"')
    return { x["LCSC Part"]: {
                "lcsc": x["LCSC Part"],
                "category": x["First Category"],
                "subcategory": x["Second Category"],
                "mfr": x["MFR.Part"],
                "package": x["Package"],
                "joints": int(x["Solder Joint"]),
                "manufacturer": x["Manufacturer"],
                "basic": x["Library Type"] == "Basic",
                "description": x["Description"],
                "datasheet": x["Datasheet"],
                "stock": int(x["Stock"]),
                "price": parsePrice(x["Price"])
            }   for x in reader }

def loadJlcTableLazy(file):
    reader = csv.DictReader(file, delimiter=',', quotechar='"')
    return map( lambda x: {
                "lcsc": x["LCSC Part"],
                "category": x["First Category"],
                "subcategory": x["Second Category"],
                "mfr": x["MFR.Part"],
                "package": x["Package"],
                "joints": int(x["Solder Joint"]),
                "manufacturer": x["Manufacturer"],
                "basic": x["Library Type"] == "Basic",
                "description": x["Description"],
                "datasheet": x["Datasheet"],
                "stock": int(x["Stock"]),
                "price": parsePrice(x["Price"])
            }, reader )
