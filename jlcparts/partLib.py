#!/usr/bin/env python3

import requests
import json
import sys
import click
import csv
import re
import time
import shutil

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
        if "exceeded the maximum number of attempts" in res.text or res.json()["code"] == 429:
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
        if "Bad Gateway" in res.text:
            print("Bad gateway, try again in a second")
            time.sleep(5)
            return getLcscExtra(lcscNumber, token=None, cookies=None, onPause=onPause)
    return None, token, cookies


def loadJlcTable(file):
    reader = csv.DictReader(file, delimiter=';', quotechar='"')
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
