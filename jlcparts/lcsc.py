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

if __name__ == "__main__":
    r = makeLcscRequest("https://ips.lcsc.com/rest/wmsc2agent/product/info/C7063")
    print(r.json())

