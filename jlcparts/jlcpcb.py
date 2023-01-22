import requests
import os
import csv
import time
from typing import Optional, List, Any, Callable

JLCPCB_KEY = os.environ.get("JLCPCB_KEY")
JLCPCB_SECRET = os.environ.get("JLCPCB_SECRET")

class JlcPcbInterface:
    def __init__(self, key: str, secret: str) -> None:
        self.key = key
        self.secret = secret
        self.token = None
        self.lastPage = None

    def _obtainToken(self) -> None:
        body = {
            "appKey": self.key,
            "appSecret": self.secret
        }
        headers = {
            "Content-Type": "application/json",
        }
        resp = requests.post("https://jlcpcb.com/external/genToken",
            json=body, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"Cannot obtain token {resp.json()}")
        data = resp.json()
        if data["code"] != 200:
            raise RuntimeError(f"Cannot obtain toke {data}")
        self.token = data["data"]

    def getPage(self) -> Optional[List[Any]]:
        if self.token is None:
            self._obtainToken()
        headers = {
            "externalApiToken": self.token,
        }
        if self.lastPage is None:
            body = {}
        else:
            body = {
                "lastKey": self.lastPage
            }
        resp = requests.post("https://jlcpcb.com/external/component/getComponentInfos",
            data=body, headers=headers)
        try:
            data = resp.json()["data"]
        except:
            raise RuntimeError(f"Cannot fetch page: {resp.text}")
        self.lastPage = data["lastKey"]
        return data["componentInfos"]

def dummyReporter(progress) -> None:
    return

def pullComponentTable(filename: str, reporter: Callable[[int], None] = dummyReporter,
                       retries: int = 10, retryDelay: int = 5) -> None:
    interf = JlcPcbInterface(JLCPCB_KEY, JLCPCB_SECRET)
    with open(filename, "w", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "LCSC Part",
            "First Category",
            "Second Category",
            "MFR.Part",
            "Package",
            "Solder Joint",
            "Manufacturer",
            "Library Type",
            "Description",
            "Datasheet",
            "Stock",
            "Price"
        ])
        count = 0
        while True:
            for i in range(retries):
                try:
                    page = interf.getPage()
                    break
                except Exception as e:
                    if i == retries - 1:
                        raise e from None
                    time.sleep(retryDelay)
            if page is None:
                break
            for c in page:
                writer.writerow([
                    c["lcscPart"],
                    c["firstCategory"],
                    c["secondCategory"],
                    c["mfrPart"],
                    c["package"],
                    c["solderJoint"],
                    c["manufacturer"],
                    c["libraryType"],
                    c["description"],
                    c["datasheet"],
                    c["stock"],
                    c["price"]
                ])
            count += len(page)
            reporter(count)
