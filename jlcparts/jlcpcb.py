import base64
import hashlib
import hmac
import json
import os
import csv
import random
import re
import string
import time
from typing import Optional, List, Any, Callable
from urllib.parse import unquote

import requests

JLCPCB_APP_ID = os.environ.get("JLCPCB_APP_ID")
JLCPCB_ACCESS_KEY = os.environ.get("JLCPCB_ACCESS_KEY")
JLCPCB_SECRET_KEY = os.environ.get("JLCPCB_SECRET_KEY")

JLCPCB_API_HOST = "https://open.jlcpcb.com"
JLCPCB_COMPONENT_LIST_PATH = "/overseas/openapi/component/getComponentLibraryList"
JLCPCB_COMPONENT_DETAIL_PATH = "/overseas/openapi/component/getComponentDetailByCode"

JLC_COMPONENT_TABLE_HEADER = [
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
    "Price",
    "JLCPCB Extra"
]


def _jsonBody(payload: dict) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def _chunks(values, size):
    for i in range(0, len(values), size):
        yield values[i:i + size]


def _priceRangesToCsv(priceRanges) -> str:
    if not priceRanges:
        return ""

    prices = []
    for priceRange in priceRanges:
        qFrom = priceRange.get("startQuantity")
        unitPrice = priceRange.get("unitPrice")
        if qFrom is None or unitPrice is None:
            continue
        qTo = priceRange.get("endQuantity")
        qToText = "" if qTo in [None, "", -1, "-1"] else str(qTo)
        prices.append(f"{qFrom}-{qToText}:{unitPrice}")
    return ",".join(prices)


def _parameterAttributes(parameters) -> dict:
    attributes = {}
    if not isinstance(parameters, list):
        return attributes
    for parameter in parameters:
        name = parameter.get("parameterName")
        value = parameter.get("parameterValue")
        if not name or value is None:
            continue
        if name in attributes and attributes[name] not in ["", "-"]:
            existing = attributes[name]
            if value not in existing.split(", "):
                attributes[name] = f"{existing}, {value}"
        else:
            attributes[name] = value
    return attributes


def _normalizeLibraryType(libraryType) -> str:
    libraryType = (libraryType or "").lower()
    if libraryType == "basic":
        return "base"
    if libraryType == "extended":
        return "expand"
    return libraryType


def _slugifyModel(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "-", value or "")
    return re.sub(r"-+", "-", value).strip("-").lower()


def _guessManufacturerFromManualUrl(url: str, model: str, code: str) -> str:
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


def _datasheet(component) -> str:
    return (
        component.get("datasheetUrl")
        or component.get("dataManualUrl")
        or component.get("dataManualOfficialLink")
        or ""
    )


def _jlcExtra(component) -> dict:
    return {
        "source": "jlcpcb_openapi",
        "rohs": component.get("rohsFlag"),
        "eccn": component.get("eccnCode") or "",
        "assembly": component.get("assemblyComponentFlag"),
        "attributes": _parameterAttributes(component.get("parameters", [])),
    }


def normalizeComponent(component) -> dict:
    jlcExtra = _jlcExtra(component)
    manufacturer = (
        component.get("manufacturer", "")
        or _guessManufacturerFromManualUrl(
            component.get("dataManualUrl"),
            component.get("componentModel"),
            component.get("componentCode")
        )
    )
    return {
        "lcscPart": component.get("componentCode") or "",
        "firstCategory": component.get("firstTypeName") or "",
        "secondCategory": component.get("secondTypeName") or "",
        "mfrPart": component.get("componentModel") or "",
        "package": component.get("componentSpecification") or "",
        "solderJoint": component.get("solderJointCount", 0) or 0,
        "manufacturer": manufacturer,
        "libraryType": _normalizeLibraryType(component.get("libraryType")),
        "description": component.get("description") or "",
        "datasheet": _datasheet(component),
        "stock": component.get("stockCount", 0) or 0,
        "price": _priceRangesToCsv(component.get("priceRanges", [])),
        "jlcExtra": jlcExtra
    }


def _requireCredential(name: str, value: Optional[str]) -> str:
    if not value:
        raise RuntimeError(f"Missing JLCPCB OpenAPI credential: {name}")
    return value

def createComponentInterface(lastKey: Optional[str] = None) -> "JlcPcbInterface":
    return JlcPcbInterface(
        _requireCredential("JLCPCB_APP_ID", JLCPCB_APP_ID),
        _requireCredential("JLCPCB_ACCESS_KEY", JLCPCB_ACCESS_KEY),
        _requireCredential("JLCPCB_SECRET_KEY", JLCPCB_SECRET_KEY),
        lastKey=lastKey
    )

class JlcPcbInterface:
    def __init__(self, appId: str, accessKey: str, secretKey: str,
                 pageSize: int = 100, detailBatchSize: int = 1000,
                 lastKey: Optional[str] = None) -> None:
        self.appId = appId
        self.accessKey = accessKey
        self.secretKey = secretKey
        self.pageSize = pageSize
        self.detailBatchSize = detailBatchSize
        self.lastPage = lastKey
        self.seenLastKeys = set()
        if lastKey is not None:
            self.seenLastKeys.add(lastKey)
        self.done = False

    def _authorization(self, method: str, path: str, body: str) -> str:
        timestamp = str(int(time.time()))
        nonceAlphabet = string.ascii_letters + string.digits
        nonce = "".join(random.SystemRandom().choice(nonceAlphabet) for _ in range(32))
        stringToSign = f"{method}\n{path}\n{timestamp}\n{nonce}\n{body}\n"
        signature = base64.b64encode(
            hmac.new(
                self.secretKey.encode("utf-8"),
                stringToSign.encode("utf-8"),
                hashlib.sha256
            ).digest()
        ).decode("ascii")
        return (
            f"JOP appid=\"{self.appId}\","
            f"accesskey=\"{self.accessKey}\","
            f"nonce=\"{nonce}\","
            f"timestamp=\"{timestamp}\","
            f"signature=\"{signature}\""
        )

    def _post(self, path: str, payload: dict) -> dict:
        body = _jsonBody(payload)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": self._authorization("POST", path, body),
        }
        resp = requests.post(JLCPCB_API_HOST + path, data=body.encode("utf-8"),
                             headers=headers, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"Cannot fetch {path}: HTTP {resp.status_code}: {resp.text}")

        try:
            data = resp.json()
        except Exception:
            raise RuntimeError(f"Cannot decode {path}: {resp.text}") from None
        successful = data.get("successful", data.get("success", True))
        if data["code"] != 200 or successful is False or data.get("data") is None:
            raise RuntimeError(f"Cannot fetch {path}: {data}")
        return data

    def _getComponentDetails(self, codes: List[str]) -> List[Any]:
        details = []
        for batch in _chunks(codes, self.detailBatchSize):
            data = self._post(JLCPCB_COMPONENT_DETAIL_PATH, {
                "componentCodes": batch
            })["data"]
            if isinstance(data, dict):
                details += data.get("componentDetailResponseVOList", [])
            elif isinstance(data, list):
                details += data
            else:
                raise RuntimeError(f"Unexpected component detail response: {data}")
        detailsByCode = {component["componentCode"]: component for component in details}
        missing = [code for code in codes if code not in detailsByCode]
        if missing:
            raise RuntimeError(f"Missing component details for: {missing[:10]}")
        return [detailsByCode[code] for code in codes]

    def getPage(self, limit: Optional[int] = None) -> Optional[List[Any]]:
        if self.done:
            return None
        if self.lastPage is None:
            body = {
                "pageSize": self.pageSize
            }
        else:
            body = {
                "pageSize": self.pageSize,
                "lastKey": self.lastPage
            }
        data = self._post(JLCPCB_COMPONENT_LIST_PATH, body)["data"]
        componentList = data["componentLibraryInfoVOS"]
        nextLastPage = data.get("lastKey")
        if nextLastPage is not None:
            if nextLastPage in self.seenLastKeys:
                raise RuntimeError(f"Repeated component list lastKey: {nextLastPage}")
            self.seenLastKeys.add(nextLastPage)
        self.lastPage = nextLastPage
        self.done = self.lastPage is None
        if not componentList:
            return None

        if limit is not None:
            componentList = componentList[:limit]
        codes = [component["componentCode"] for component in componentList]
        details = self._getComponentDetails(codes)
        detailsByCode = {component["componentCode"]: component for component in details}
        return [
            {
                **componentSummary,
                **detailsByCode[componentSummary["componentCode"]],
            }
            for componentSummary in componentList
        ]

def dummyReporter(progress) -> None:
    return

def loadCheckpoint(checkpoint: Optional[str]) -> dict:
    if checkpoint is None or not os.path.exists(checkpoint):
        return {}
    with open(checkpoint, "r", encoding="utf-8") as f:
        return json.load(f)

def writeCheckpoint(checkpoint: Optional[str], filename: str,
                    lastKey: Optional[str], count: int, done: bool) -> None:
    if checkpoint is None:
        return
    data = {
        "version": 1,
        "filename": filename,
        "count": count,
        "lastKey": lastKey,
        "done": done,
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    tmp = f"{checkpoint}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, checkpoint)

def _countCsvRows(filename: str) -> int:
    with open(filename, "r", encoding="utf-8", newline="") as f:
        return max(0, sum(1 for _ in csv.reader(f)) - 1)

def _normalizeCheckpointState(filename: str, checkpoint: Optional[str]) -> dict:
    state = loadCheckpoint(checkpoint)
    if not state:
        return {}

    count = int(state.get("count", 0))
    if count > 0:
        if not os.path.exists(filename):
            raise RuntimeError(
                f"Checkpoint {checkpoint} expects {count} existing rows, "
                f"but {filename} does not exist"
            )
        actual = _countCsvRows(filename)
        if actual != count:
            raise RuntimeError(
                f"Checkpoint {checkpoint} expects {count} existing rows in "
                f"{filename}, but found {actual}"
            )
    return state

def pullComponentTable(filename: str, reporter: Callable[[int], None] = dummyReporter,
                       limit: Optional[int] = None,
                       retries: int = 10, retryDelay: int = 5,
                       checkpoint: Optional[str] = None,
                       maxSeconds: Optional[int] = None) -> None:
    if limit is not None and checkpoint is not None:
        raise RuntimeError(
            "limit cannot be combined with checkpoint because the API cursor "
            "advances by full pages"
        )
    if maxSeconds is not None and checkpoint is None:
        raise RuntimeError("maxSeconds requires a checkpoint so the fetch can resume")

    checkpointState = _normalizeCheckpointState(filename, checkpoint)
    if checkpointState.get("done"):
        reporter(int(checkpointState.get("count", 0)))
        return

    count = int(checkpointState.get("count", 0))
    append = count > 0
    interf = createComponentInterface(lastKey=checkpointState.get("lastKey"))
    start = time.monotonic()
    with open(filename, "a" if append else "w", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not append:
            writer.writerow(JLC_COMPONENT_TABLE_HEADER)
        while True:
            remaining = None if limit is None else max(0, limit - count)
            if remaining == 0:
                writeCheckpoint(checkpoint, filename, interf.lastPage, count, interf.done)
                break
            if maxSeconds is not None and time.monotonic() - start >= maxSeconds:
                writeCheckpoint(checkpoint, filename, interf.lastPage, count, interf.done)
                break
            for i in range(retries):
                try:
                    page = interf.getPage(limit=remaining)
                    break
                except Exception as e:
                    if i == retries - 1:
                        raise e from None
                    time.sleep(retryDelay)
            if page is None:
                writeCheckpoint(checkpoint, filename, interf.lastPage, count, True)
                break
            for c in page:
                c = normalizeComponent(c)
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
                    c["price"],
                    _jsonBody(c["jlcExtra"])
                ])
            count += len(page)
            reporter(count)
            writeCheckpoint(checkpoint, filename, interf.lastPage, count, interf.done)

_normalizeComponent = normalizeComponent
_loadCheckpoint = loadCheckpoint
_writeCheckpoint = writeCheckpoint
