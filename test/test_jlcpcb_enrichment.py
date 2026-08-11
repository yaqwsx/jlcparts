import unittest
from unittest.mock import patch

from jlcparts.datatables import normalizeAttribute
from jlcparts.jlcpcb import (
    _jlcExtra,
    _website_component_enrichment,
    enrichComponentsFromWebsite,
)
from jlcparts.sourceDb import SourceDb


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
                "componentProductType": 2,
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
        self.assertEqual(enrichment["componentProductType"], 2)
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
            "componentProductType": 0,
            "websiteComponentId": 1443,
            "lossNumber": 10,
            "leastNumber": 20,
            "leastPatchNumber": 20,
            "minPurchaseNum": 1,
            "parameters": [],
        })

        self.assertEqual(extra["assemblyProcess"], "SMT")
        self.assertEqual(extra["assemblyMode"], "smtWeld")
        self.assertEqual(extra["componentProductType"], 0)
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

    def test_component_product_type_survives_source_database_round_trip(self):
        source_db = SourceDb(":memory:")
        source_db.updateJlcPayload({
            "componentCode": "C123",
            "firstTypeName": "Test",
            "secondTypeName": "Parts",
            "componentModel": "TEST-123",
            "componentSpecification": "SMD",
            "stockCount": 1,
            "libraryType": "Basic",
            "componentProductType": 1,
        })

        components = list(source_db.iterCategoryComponents("Test", "Parts"))

        self.assertEqual(len(components), 1)
        self.assertEqual(components[0]["jlc_extra"]["componentProductType"], 1)
        source_db.close()


if __name__ == "__main__":
    unittest.main()
