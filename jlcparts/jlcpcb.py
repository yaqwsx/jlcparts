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
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Any, Callable
from urllib.parse import unquote

import requests

JLCPCB_APP_ID = os.environ.get("JLCPCB_APP_ID")
JLCPCB_ACCESS_KEY = os.environ.get("JLCPCB_ACCESS_KEY")
JLCPCB_SECRET_KEY = os.environ.get("JLCPCB_SECRET_KEY")

JLCPCB_API_HOST = "https://open.jlcpcb.com"
JLCPCB_COMPONENT_LIST_PATH = "/overseas/openapi/component/getComponentLibraryList"
JLCPCB_COMPONENT_DETAIL_PATH = "/overseas/openapi/component/getComponentDetailByCode"
JLCPCB_WEBSITE_API_HOST = "https://jlcpcb.com/api/overseas-pcb-order/v1"
JLCPCB_WEBSITE_COMPONENT_LIST_PATH = "/shoppingCart/smtGood/selectSmtComponentList/v2"
JLCPCB_WEBSITE_COMPONENT_DETAIL_PATH = "/shoppingCart/smtGood/getComponentDetail"
JLCPCB_WEBSITE_PAGE_SIZE = 1000
JLCPCB_WEBSITE_RESULT_WINDOW = 100000

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
    attributes = _parameterAttributes(component.get("parameters", []))
    for sourceKey, attrName in [
        ("assemblyProcess", "Assembly Process"),
        ("assemblyMode", "Assembly Mode"),
        ("lossNumber", "Attrition"),
        ("leastNumber", "Minimum Order Quantity"),
        ("leastPatchNumber", "Minimum Placement Quantity"),
        ("minPurchaseNum", "Minimum Purchase Quantity"),
    ]:
        value = component.get(sourceKey)
        if value is not None and value != "":
            attributes[attrName] = str(value)

    attrition = {
        key: component.get(key)
        for key in ["lossNumber", "leastNumber", "leastPatchNumber", "minPurchaseNum"]
        if component.get(key) is not None
    }
    return {
        "source": "jlcpcb_openapi",
        "rohs": component.get("rohsFlag"),
        "eccn": component.get("eccnCode") or "",
        "assembly": component.get("assemblyComponentFlag"),
        "assemblyProcess": component.get("assemblyProcess"),
        "assemblyMode": component.get("assemblyMode"),
        "websiteComponentId": component.get("websiteComponentId"),
        "attrition": attrition,
        "attributes": attributes,
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


def _website_api_post(path: str, payload: dict) -> dict:
    resp = requests.post(
        JLCPCB_WEBSITE_API_HOST + path,
        json=payload,
        headers={
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Cannot fetch {path}: HTTP {resp.status_code}: {resp.text}")
    data = resp.json()
    if data.get("code") != 200 or data.get("data") is None:
        raise RuntimeError(f"Cannot fetch {path}: {data}")
    return data["data"]


def _website_api_get(path: str, params: dict) -> dict:
    resp = requests.get(
        JLCPCB_WEBSITE_API_HOST + path,
        params=params,
        headers={"Accept": "application/json, text/plain, */*"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Cannot fetch {path}: HTTP {resp.status_code}: {resp.text}")
    data = resp.json()
    if data.get("code") != 200 or data.get("data") is None:
        raise RuntimeError(f"Cannot fetch {path}: {data}")
    return data["data"]


def _find_website_component(component_code: str) -> dict:
    data = _website_api_post(JLCPCB_WEBSITE_COMPONENT_LIST_PATH, {
        "currentPage": 1,
        "pageSize": 25,
        "keyword": component_code,
        "searchSource": "search",
        "searchType": 2,
        "componentBrandList": [],
        "componentSpecificationList": [],
        "componentAttributeList": [],
        "paramList": [],
    })
    page_info = data.get("componentPageInfo", {})
    for row in page_info.get("list", []):
        if row.get("componentCode") == component_code:
            return row
    raise RuntimeError(f"No exact JLC website result for {component_code}")


def _get_website_component_detail(component_id: int) -> dict:
    return _website_api_get(
        JLCPCB_WEBSITE_COMPONENT_DETAIL_PATH,
        {"componentLcscId": component_id},
    )


def _website_component_enrichment(component_code: str) -> dict:
    row = _find_website_component(component_code)
    component_id = row.get("componentId")
    if component_id is None:
        raise RuntimeError(f"No JLC website componentId for {component_code}")
    detail = _get_website_component_detail(component_id)
    combined = {**row, **detail}
    return {
        "websiteComponentId": component_id,
        "assemblyProcess": combined.get("assemblyProcess"),
        "assemblyMode": combined.get("assemblyMode"),
        "lossNumber": combined.get("lossNumber"),
        "leastNumber": combined.get("leastNumber"),
        "leastPatchNumber": combined.get("leastPatchNumber"),
        "minPurchaseNum": combined.get("minPurchaseNum"),
    }


def _website_price_ranges(component: dict) -> List[dict]:
    return [
        {
            "startQuantity": price.get("startNumber"),
            "endQuantity": price.get("endNumber"),
            "unitPrice": price.get("productPrice"),
        }
        for price in component.get("componentPrices", [])
    ]


def websiteComponentToPayload(component: dict) -> dict:
    """
    Convert a JLCPCB component-shop result to the OpenAPI-shaped payload used
    by SourceDb.

    The website names its category levels in the opposite order to OpenAPI:
    firstSortName is the subcategory and secondSortName is the parent category.
    """
    return {
        "componentCode": component.get("componentCode"),
        "firstTypeName": component.get("secondSortName") or "",
        "secondTypeName": component.get("firstSortName") or "",
        "componentModel": (
            component.get("componentModelEn")
            or component.get("componentModel")
            or ""
        ),
        "componentSpecification": (
            component.get("componentSpecificationEn")
            or component.get("componentSpecification")
            or ""
        ),
        "solderJointCount": component.get("solderJointCount", 0) or 0,
        "manufacturer": (
            component.get("componentBrandEn")
            or component.get("componentBrand")
            or ""
        ),
        "libraryType": (
            component.get("componentLibraryType")
            or component.get("libraryType")
            or ""
        ),
        "description": (
            component.get("describe")
            or component.get("description")
            or ""
        ),
        "dataManualUrl": component.get("dataManualUrl"),
        "dataManualFileAccessIdUrl": component.get("dataManualFileAccessIdUrl"),
        "dataManualOfficialLink": component.get("dataManualOfficialLink"),
        "stockCount": component.get("stockCount", 0) or 0,
        "priceRanges": _website_price_ranges(component),
        "parameters": component.get("parameters") or [],
        "rohsFlag": component.get("rohsFlag"),
        "assemblyComponentFlag": component.get("assemblyComponentFlag"),
        "websiteComponentId": component.get("componentId"),
        "componentSource": component.get("componentSource"),
        "isBuyComponent": component.get("isBuyComponent"),
    }


def _website_stock_category_segments() -> List[dict]:
    data = _website_api_post(JLCPCB_WEBSITE_COMPONENT_LIST_PATH, {
        "currentPage": 1,
        "pageSize": 0,
        "keyword": "",
        "searchSource": "search",
        "searchType": 1,
        "presaleType": "stock",
        "stockFlag": True,
        "componentBrandList": [],
        "componentSpecificationList": [],
        "componentAttributeList": [],
        "paramList": [],
    })

    segments = []
    for parent in data.get("sortAndCountVoList", []):
        parent_id = parent.get("componentSortKeyId")
        parent_count = int(parent.get("componentCount", 0) or 0)
        if parent_id is None or parent_count == 0:
            continue

        if parent_count <= JLCPCB_WEBSITE_RESULT_WINDOW:
            segments.append({
                "parent_id": parent_id,
                "child_id": None,
                "component_count": parent_count,
            })
            continue

        child_count = 0
        for child in parent.get("childSortList", []):
            count = int(child.get("componentCount", 0) or 0)
            child_count += count
            if count == 0:
                continue
            if count > JLCPCB_WEBSITE_RESULT_WINDOW:
                raise RuntimeError(
                    "JLC website category exceeds the result window: "
                    f"{parent.get('sortName')} / {child.get('sortName')} "
                    f"has {count} components"
                )
            segments.append({
                "parent_id": parent_id,
                "child_id": child.get("componentSortKeyId"),
                "component_count": count,
            })

        if child_count != parent_count:
            raise RuntimeError(
                "JLC website category cannot be completely partitioned: "
                f"{parent.get('sortName')} has {parent_count} components, "
                f"but its subcategories contain {child_count}"
            )
    return segments


class JlcWebsiteInterface:
    def __init__(self, pageSize: int = JLCPCB_WEBSITE_PAGE_SIZE,
                 segmentIndex: int = 0, currentPage: int = 1,
                 segments: Optional[List[dict]] = None) -> None:
        self.pageSize = pageSize
        self.segments = (
            _website_stock_category_segments()
            if segments is None
            else segments
        )
        self.segmentIndex = segmentIndex
        self.currentPage = currentPage
        self.done = self.segmentIndex >= len(self.segments)

    def _payload(self, segment: dict) -> dict:
        payload = {
            "currentPage": self.currentPage,
            "pageSize": self.pageSize,
            "keyword": "",
            "searchSource": "search",
            "searchType": 2,
            "presaleType": "stock",
            "stockFlag": True,
            "productTypeIdList": [segment["parent_id"]],
            "componentBrandList": [],
            "componentSpecificationList": [],
            "componentAttributeList": [],
            "paramList": [],
        }
        if segment.get("child_id") is not None:
            payload["componentTypeIdList"] = [segment["child_id"]]
        return payload

    def getPage(self) -> Optional[List[Any]]:
        if self.done:
            return None

        while self.segmentIndex < len(self.segments):
            segment = self.segments[self.segmentIndex]
            data = _website_api_post(
                JLCPCB_WEBSITE_COMPONENT_LIST_PATH,
                self._payload(segment),
            )
            page_info = data.get("componentPageInfo")
            if not isinstance(page_info, dict):
                raise RuntimeError(
                    "JLC website returned no component page for "
                    f"category {segment['parent_id']}/{segment.get('child_id')}"
                )

            components = page_info.get("list") or []
            page_number = int(page_info.get("pageNum", self.currentPage) or 0)
            page_count = int(page_info.get("pages", 0) or 0)
            if components and page_number != self.currentPage:
                raise RuntimeError(
                    f"JLC website returned page {page_number}, "
                    f"expected {self.currentPage}"
                )

            if not components or page_number >= page_count:
                self.segmentIndex += 1
                self.currentPage = 1
                self.done = self.segmentIndex >= len(self.segments)
            else:
                self.currentPage += 1

            if components:
                return [
                    websiteComponentToPayload(component)
                    for component in components
                ]

        self.done = True
        return None


def createWebsiteComponentInterface(segmentIndex: int = 0,
                                    currentPage: int = 1) -> JlcWebsiteInterface:
    return JlcWebsiteInterface(
        segmentIndex=segmentIndex,
        currentPage=currentPage,
    )


def _apply_website_enrichment(component: dict, enrichment: dict) -> dict:
    return {
        **component,
        **{
            key: value
            for key, value in enrichment.items()
            if value is not None
        },
    }


def enrichComponentsFromWebsite(components: List[dict], workers: int = 8,
                                reporter: Callable[[str], None] = print) -> List[dict]:
    if not components:
        return components

    enriched = list(components)
    by_future = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        for index, component in enumerate(components):
            code = component.get("componentCode")
            if not code:
                continue
            by_future[executor.submit(_website_component_enrichment, code)] = (index, code)

        for future in as_completed(by_future):
            index, code = by_future[future]
            try:
                enriched[index] = _apply_website_enrichment(enriched[index], future.result())
            except Exception as e:
                reporter(f"Cannot enrich {code} from JLC website: {type(e).__name__}: {e}")
    return enriched

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
