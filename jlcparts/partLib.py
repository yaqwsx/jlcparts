#!/usr/bin/env python3

import requests
from requests.exceptions import ConnectionError
import json
import sys
import click
import csv
import re
import time
import shutil
from pathlib import Path
from textwrap import indent
from bs4 import BeautifulSoup
import py_mini_racer

CACHE_PATH = "/tmp/jlcparts"

class PartLibrary:
    def __init__(self, filepath=None):
        if filepath is None:
            self.lib = {}
            self.index = {}
            return
        with open(filepath, "r") as f:
            self.lib = json.load(f)
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

def obtainCsrfTokenAndCookies():
    searchPage = requests.get("https://lcsc.com/products/Pre-ordered-Products_11171.html")
    return extractCsrfToken(searchPage.text), searchPage.cookies

def extractCsrfToken(pageText):
    m = re.search(r"'X-CSRF-TOKEN':\s*'(.*)'", pageText)
    if not m:
        return None
    return m.group(1)

def readLcscParamTable(lcscNumber, script):
    ctx = py_mini_racer.MiniRacer()
    ctx.eval("""
        let window = {};
        let result = () => window.__NUXT__.data[0].detail.paramVOList;
        let partialResult = () => window.__NUXT__;
        """)
    try:
        ctx.eval(script)
        data = ctx.call("result")
    except py_mini_racer.py_mini_racer.JSEvalException as e:
        if "Cannot read property 'paramVOList" in f"{e}":
            error = "No data table is provided"
        else:
            error = f"Cannot extract: {e}"
        print(indent(f"Warning {lcscNumber}: {error}", 8 * " "))
        return {}
    except Exception as e:
        print(indent(f"Failed {lcscNumber}: {e}", 8 * " "))
    if data is None:
        return {}
    params = {}
    for row in data:
        params[row["paramNameEn"]] = row["paramValueEn"]
    with open(f"{CACHE_PATH}/{lcscNumber}.json", "w") as f:
        json.dump(params, f)
    return params

def getLcscExtraNew(lcscNumber, onPause=None, initialUrl=None):
    cachePath = Path(CACHE_PATH)
    cachePath.mkdir(parents=True, exist_ok=True)
    try:
        with open(cachePath / f"{lcscNumber}.json") as f:
            return json.load(f)
    except:
        pass

    timeouts = [
        "502 Bad Gateway",
        "504 Gateway Time-out",
        "504 ERROR",
        "Too Many Requests",
        "Please try again in a few minutes"
    ]

    if initialUrl is not None:
        url = initialUrl
    else:
        try:
            res = None
            res = requests.get(f"https://wwwapi.lcsc.com/v1/search/global-search?keyword={lcscNumber}")
            resJson = res.json()
        except:
            if res is None or any([x in res.text for x in timeouts]):
                time.sleep(60)
                return getLcscExtraNew(lcscNumber, onPause)
            else:
                print(f"Failed {lcscNumber}:\n" + indent(res.text, 8 * " "))
            raise
        if isinstance(resJson, list):
            return {}
        ids = resJson["tipProductDetailUrlVO"]
        if ids is None:
            # The component is not available on LCSC
            return {}

        catalogName = ids["catalogName"].replace(" ", "-")
        man = ids["brandNameEn"].replace(" ", "-")
        product = ids["productModel"].replace(" ", "-")
        code = ids["productCode"]

        url = f"https://lcsc.com/product-detail/{catalogName}_{man}-{product}_{code}.html"

    try:
        res = requests.get(url)
        if any([x in res.text for x in timeouts]) or len(res.text) == 0:
            raise RuntimeError()
    except:
        time.sleep(60)
        return getLcscExtraNew(lcscNumber, onPause, url)
    soup = BeautifulSoup(res.text, "lxml")
    scripts = ["".join(x.find_all(text=True)) for x in soup.find_all("script")]
    filteredScripts = [x for x in scripts if "window.__NUXT__" in x]
    if len(filteredScripts) != 1:
        raise RuntimeError(f"Failed {lcscNumber}: No script")
    script = filteredScripts[0]
    return readLcscParamTable(lcscNumber, script)

def getLcscExtra(lcscNumber, token=None, cookies=None, onPause=None):
    if token is None or cookies is None:
        token, cookies = obtainCsrfTokenAndCookies()
    headers = {
        'pragma': 'no-cache',
        'cache-control': 'no-cache',
        'accept': 'application/json, text/javascript, */*; q=0.01',
        'x-csrf-token': token,
        'x-requested-with': 'XMLHttpRequest',
        'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4103.116 Safari/537.36',
        'isajax': 'true',
        'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'origin': 'https://lcsc.com',
        'sec-fetch-site': 'same-origin',
        'sec-fetch-mode': 'cors',
        'sec-fetch-dest': 'empty',
        'referer': 'https://lcsc.com',
        'accept-language': 'cs,en;q=0.9,sk;q=0.8,en-GB;q=0.7',
    }
    res = requests.post("https://lcsc.com/api/products/search",
                        headers=headers, cookies=cookies,
                        data={
                            "current_page": "1",
                            "in_stock": "false",
                            "is_RoHS": "false",
                            "show_icon": "false",
                            "search_content": lcscNumber
                        })
    try:
        failed = False
        failed = failed or "exceeded the maximum number of attempts" in res.text
        failed = failed or "try again" in res.text
        try:
            failed = failed or res.json()["code"] == 429
        except Exception as e:
            print(f"Cannot read code from response, {e}")
            failed = True
        if failed:
            if onPause:
                onPause()
            print("Too many requests! Waiting")
            time.sleep(10)
            return getLcscExtra(lcscNumber, token=None, cookies=None, onPause=onPause)
        results = res.json()["result"]["data"]
        if len(results) != 1:
            print(f"Warning, {lcscNumber} not found")
            return {}, token, cookies
        component = res.json()["result"]["data"][0]
        if component["number"] != lcscNumber:
            print(f"Warning, {lcscNumber} not found")
            return {}, token, cookies
        return component, token, cookies
    except Exception as e:
        print(f"  Cannot parse response for component {lcscNumber}")
        print(f"{type(e)}")
        print(f"  Error: {e}")
        print(f"  Response: {res.text}")
        if onPause:
            onPause()
        if "Bad Gateway" in res.text or isinstance(e, ConnectionError):
            print("Faulty connection")
            time.sleep(5)
            return getLcscExtra(lcscNumber, token=None, cookies=None, onPause=onPause)
    return None, token, cookies


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