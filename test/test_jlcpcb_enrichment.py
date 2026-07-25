import unittest
from unittest.mock import patch

from jlcparts.datatables import normalizeAttribute
from jlcparts.jlcpcb import (
    JlcWebsiteInterface,
    _jlcExtra,
    _website_stock_category_segments,
    _website_component_enrichment,
    enrichComponentsFromWebsite,
    websiteComponentToPayload,
)


class JlcWebsiteEnrichmentTest(unittest.TestCase):
    def test_exact_component_is_selected_from_fuzzy_results(self):
        def fake_post(path, payload):
            self.assertEqual(payload["keyword"], "C11255")
            return {
                "componentPageInfo": {
                    "list": [
                        {
                            "componentCode": "C19979310",
                            "componentId": 21308624,
                            "lossNumber": 0,
                        },
                        {
                            "componentCode": "C11255",
                            "componentId": 11806,
                            "lossNumber": 1,
                            "leastPatchNumber": 2,
                            "minPurchaseNum": 1,
                        },
                    ]
                }
            }

        def fake_get(path, params):
            self.assertEqual(params["componentLcscId"], 11806)
            return {
                "componentCode": "C11255",
                "assemblyProcess": "THT",
                "assemblyMode": "manualWeld",
                "lossNumber": 1,
                "leastNumber": 2,
                "leastPatchNumber": 2,
                "minPurchaseNum": 1,
            }

        with patch("jlcparts.jlcpcb._website_api_post", fake_post), \
             patch("jlcparts.jlcpcb._website_api_get", fake_get):
            enrichment = _website_component_enrichment("C11255")

        self.assertEqual(enrichment["websiteComponentId"], 11806)
        self.assertEqual(enrichment["assemblyProcess"], "THT")
        self.assertEqual(enrichment["assemblyMode"], "manualWeld")
        self.assertEqual(enrichment["lossNumber"], 1)
        self.assertEqual(enrichment["leastNumber"], 2)
        self.assertEqual(enrichment["leastPatchNumber"], 2)
        self.assertEqual(enrichment["minPurchaseNum"], 1)

    def test_enrichment_failure_keeps_component_usable(self):
        components = [{"componentCode": "C1", "description": "original"}]
        with patch("jlcparts.jlcpcb._website_component_enrichment",
                   side_effect=RuntimeError("boom")):
            enriched = enrichComponentsFromWebsite(components, workers=1, reporter=lambda _: None)

        self.assertEqual(enriched, components)

    def test_jlc_extra_contains_assembly_and_attrition_attributes(self):
        extra = _jlcExtra({
            "assemblyComponentFlag": False,
            "assemblyProcess": "SMT",
            "assemblyMode": "smtWeld",
            "websiteComponentId": 1443,
            "lossNumber": 10,
            "leastNumber": 20,
            "leastPatchNumber": 20,
            "minPurchaseNum": 1,
            "parameters": [],
        })

        self.assertEqual(extra["assemblyProcess"], "SMT")
        self.assertEqual(extra["assemblyMode"], "smtWeld")
        self.assertEqual(extra["websiteComponentId"], 1443)
        self.assertEqual(extra["attrition"]["lossNumber"], 10)
        self.assertEqual(extra["attributes"]["Assembly Process"], "SMT")
        self.assertEqual(extra["attributes"]["Assembly Mode"], "smtWeld")
        self.assertEqual(extra["attributes"]["Attrition"], "10")
        self.assertEqual(extra["attributes"]["Minimum Order Quantity"], "20")
        self.assertEqual(extra["attributes"]["Minimum Placement Quantity"], "20")
        self.assertEqual(extra["attributes"]["Minimum Purchase Quantity"], "1")

    def test_attrition_properties_are_count_attributes(self):
        for key in [
            "Attrition",
            "Minimum Order Quantity",
            "Minimum Placement Quantity",
            "Minimum Purchase Quantity",
        ]:
            normalized_key, normalized_value = normalizeAttribute(key, "12")
            self.assertEqual(normalized_key, key)
            self.assertEqual(normalized_value["values"]["count"], [12, "count"])

    def test_shop_component_is_converted_to_source_payload(self):
        component = {
            "componentId": 352898,
            "componentCode": "C380550",
            "componentBrandEn": "GOWIN",
            "componentModelEn": "GW2AR-LV18QN88C8/I7",
            "componentSpecificationEn": "QFN-88",
            "componentLibraryType": "expand",
            "describe": "QFN-88 Programmable Logic Device (CPLDs/FPGAs) ROHS",
            "stockCount": 154,
            "componentPrices": [{
                "startNumber": 1,
                "endNumber": 29,
                "productPrice": 49.9969,
            }],
            "firstSortName": "Programmable Logic Device (CPLDs/FPGAs)",
            "secondSortName": "Embedded Processors & Controllers",
            "assemblyComponentFlag": False,
            "componentSource": "shop",
            "isBuyComponent": "1",
        }

        payload = websiteComponentToPayload(component)

        self.assertEqual(payload["componentCode"], "C380550")
        self.assertEqual(
            payload["firstTypeName"],
            "Embedded Processors & Controllers",
        )
        self.assertEqual(
            payload["secondTypeName"],
            "Programmable Logic Device (CPLDs/FPGAs)",
        )
        self.assertEqual(payload["componentModel"], "GW2AR-LV18QN88C8/I7")
        self.assertEqual(payload["componentSpecification"], "QFN-88")
        self.assertEqual(payload["stockCount"], 154)
        self.assertEqual(payload["assemblyComponentFlag"], False)
        self.assertEqual(payload["priceRanges"], [{
            "startQuantity": 1,
            "endQuantity": 29,
            "unitPrice": 49.9969,
        }])

    def test_stock_categories_are_partitioned_below_result_window(self):
        def fake_post(path, payload):
            self.assertEqual(payload["presaleType"], "stock")
            return {
                "sortAndCountVoList": [
                    {
                        "sortName": "Small",
                        "componentSortKeyId": 1,
                        "componentCount": 10,
                        "childSortList": [],
                    },
                    {
                        "sortName": "Large",
                        "componentSortKeyId": 2,
                        "componentCount": 120000,
                        "childSortList": [
                            {
                                "componentSortKeyId": 20,
                                "componentCount": 70000,
                            },
                            {
                                "componentSortKeyId": 21,
                                "componentCount": 50000,
                            },
                        ],
                    },
                ],
            }

        with patch("jlcparts.jlcpcb._website_api_post", fake_post):
            segments = _website_stock_category_segments()

        self.assertEqual(segments, [
            {"parent_id": 1, "child_id": None, "component_count": 10},
            {"parent_id": 2, "child_id": 20, "component_count": 70000},
            {"parent_id": 2, "child_id": 21, "component_count": 50000},
        ])

    def test_website_interface_checkpoints_after_each_page(self):
        requests = []

        def fake_post(path, payload):
            requests.append(payload)
            page = payload["currentPage"]
            return {
                "componentPageInfo": {
                    "pageNum": page,
                    "pages": 2,
                    "list": [{
                        "componentCode": f"C{page}",
                        "stockCount": 1,
                    }],
                },
            }

        interface = JlcWebsiteInterface(
            pageSize=1,
            segments=[{
                "parent_id": 18,
                "child_id": 2585,
                "component_count": 2,
            }],
        )
        with patch("jlcparts.jlcpcb._website_api_post", fake_post):
            first = interface.getPage()
            self.assertEqual(interface.segmentIndex, 0)
            self.assertEqual(interface.currentPage, 2)
            second = interface.getPage()
            self.assertTrue(interface.done)
            self.assertIsNone(interface.getPage())

        self.assertEqual(first[0]["componentCode"], "C1")
        self.assertEqual(second[0]["componentCode"], "C2")
        self.assertEqual(requests[0]["productTypeIdList"], [18])
        self.assertEqual(requests[0]["componentTypeIdList"], [2585])


if __name__ == "__main__":
    unittest.main()
