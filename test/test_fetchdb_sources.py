import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from click.testing import CliRunner

from jlcparts.ui import cli


class EmptyOpenApiInterface:
    lastPage = None

    def getPage(self):
        return None


class SinglePageWebsiteInterface:
    def __init__(self, components):
        self.components = components
        self.segmentIndex = 0
        self.currentPage = 1

    def getPage(self):
        if self.components is None:
            return None
        components = self.components
        self.components = None
        self.segmentIndex = 1
        self.currentPage = 1
        return components


class FetchDbSourcesTest(unittest.TestCase):
    def test_shop_only_component_is_written_to_source_database(self):
        shop_component = {
            "componentCode": "C380550",
            "firstTypeName": "Embedded Processors & Controllers",
            "secondTypeName": "Programmable Logic Device (CPLDs/FPGAs)",
            "componentModel": "GW2AR-LV18QN88C8/I7",
            "componentSpecification": "QFN-88",
            "manufacturer": "GOWIN",
            "libraryType": "expand",
            "description": "QFN-88 Programmable Logic Device (CPLDs/FPGAs) ROHS",
            "stockCount": 154,
            "priceRanges": [{
                "startQuantity": 1,
                "endQuantity": 29,
                "unitPrice": 49.9969,
            }],
            "parameters": [],
            "assemblyComponentFlag": False,
            "websiteComponentId": 352898,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "cache.sqlite3")
            checkpoint_path = os.path.join(tmpdir, "parts.checkpoint.json")
            website_interface = SinglePageWebsiteInterface([shop_component])

            with patch(
                "jlcparts.jlcpcb.createComponentInterface",
                return_value=EmptyOpenApiInterface(),
            ), patch(
                "jlcparts.jlcpcb.createWebsiteComponentInterface",
                return_value=website_interface,
            ), patch(
                "jlcparts.ui.refreshExtraData",
                return_value=None,
            ):
                result = CliRunner().invoke(cli, [
                    "fetchdb",
                    db_path,
                    "--checkpoint",
                    checkpoint_path,
                    "--limit",
                    "0",
                ])

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertFalse(os.path.exists(checkpoint_path))

            conn = sqlite3.connect(db_path)
            row = conn.execute("""
                SELECT category, subcategory, mfr, package, stock, assembly
                FROM jlc_components
                WHERE lcsc = 380550
                """).fetchone()
            conn.close()

            self.assertEqual(row, (
                "Embedded Processors & Controllers",
                "Programmable Logic Device (CPLDs/FPGAs)",
                "GW2AR-LV18QN88C8/I7",
                "QFN-88",
                154,
                0,
            ))


if __name__ == "__main__":
    unittest.main()
