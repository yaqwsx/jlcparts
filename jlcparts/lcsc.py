import json
import requests
import os
import time
import random
import string
import urllib
import hashlib
from requests.exceptions import ConnectionError

LCSC_KEY = os.environ.get("LCSC_KEY")
LCSC_SECRET = os.environ.get("LCSC_SECRET")

def makeLcscRequest(url, payload=None):
    if payload is None:
        payload = {}
    payload = [(key, value) for key, value in payload.items()]
    payload.sort(key=lambda x: x[0])
    newPayload = {
        "key": LCSC_KEY,
        "nonce": "".join(random.choices(string.ascii_lowercase, k=16)),
        "secret": LCSC_SECRET,
        "timestamp": str(int(time.time())),
    }
    for k, v in payload:
        newPayload[k] = v
    payloadStr = urllib.parse.urlencode(newPayload).encode("utf-8")
    newPayload["signature"] = hashlib.sha1(payloadStr).hexdigest()

    return requests.get(url, params=newPayload)

def pullPreferredComponents():
    resp = requests.get("https://jlcpcb.com/api/overseas-pcb-order/v1/getAll")
    token = resp.cookies.get_dict()["XSRF-TOKEN"]

    headers = {
        "Content-Type": "application/json",
        "X-XSRF-TOKEN": token,
    }
    PAGE_SIZE = 1000

    currentPage = 1
    components = set()
    while True:
        body = {
            "currentPage": currentPage,
            "pageSize": PAGE_SIZE,
            "preferredComponentFlag": True
        }

        resp = requests.post(
            "https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList",
            headers=headers,
            json=body
        )

        body = resp.json()
        for c in [x["componentCode"] for x in body["data"]["componentPageInfo"]["list"]]:
            components.add(c)

        if not body["data"]["componentPageInfo"]["hasNextPage"]:
            break
        currentPage += 1

    return components

if __name__ == "__main__":
    r = makeLcscRequest("https://ips.lcsc.com/rest/wmsc2agent/product/info/C7063")
    print(r.json())

