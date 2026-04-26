import json
import os
import sqlite3
import time
from pathlib import Path

import click

from .datatables import (
    _mergeAttributes,
    crushImages,
    extractAttributesFromDescription,
    normalizeAttribute,
    trimLcscUrl,
    weakUpdateParameters,
)
from .partLib import PartLibraryDb


def _component_status(component):
    if component.get("extra", {}) == {} and component.get("jlc_extra", {}) == {}:
        return 1
    return 0


def _normalized_attributes(component):
    attrs = _mergeAttributes(component)
    weakUpdateParameters(attrs, extractAttributesFromDescription(component["description"]))

    # Drop fields that are either redundant elsewhere in the schema or not needed
    # by the frontend query path.
    attrs.pop("url", None)
    attrs.pop("images", None)
    attrs.pop("prices", None)
    attrs.pop("datasheet", None)
    attrs.pop("id", None)
    attrs.pop("manufacturer", None)
    attrs.pop("number", None)
    attrs.pop("title", None)
    attrs.pop("quantity", None)
    for i in range(10):
        attrs.pop(f"quantity{i}", None)

    normalized = {}
    for key, value in attrs.items():
        norm_key, norm_value = normalizeAttribute(key, value)
        normalized[norm_key] = norm_value
    return normalized


def _component_row(component, category_id, manufacturer_id, package_id):
    return (
        component["lcsc"],
        category_id,
        component["mfr"],
        manufacturer_id,
        package_id,
        int(component["joints"]),
        int(component["stock"]),
        int(bool(component["basic"])),
        int(bool(component["preferred"])),
        _component_status(component),
        component["description"],
        component["datasheet"],
        json.dumps(component["price"], separators=(",", ":")),
        crushImages(component.get("extra", {}).get("images", None)),
        trimLcscUrl(component.get("extra", {}).get("url", None), component["lcsc"]),
    )


class WebDbBuilder:
    def __init__(self, source_db, output_db, page_size=4096, with_fts=True):
        self.source_db = source_db
        self.output_db = output_db
        self.page_size = page_size
        self.with_fts = with_fts

        self.src = PartLibraryDb(source_db)
        self.conn = sqlite3.connect(output_db)
        self.conn.row_factory = sqlite3.Row

        self.category_cache = {}
        self.manufacturer_cache = {}
        self.package_cache = {}
        self.attr_key_cache = {}
        self.attr_value_cache = {}

        self.component_count = 0
        self.attribute_count = 0

    def configure(self):
        self.conn.execute(f"PRAGMA page_size = {int(self.page_size)}")
        self.conn.execute("PRAGMA journal_mode = OFF")
        self.conn.execute("PRAGMA synchronous = OFF")
        self.conn.execute("PRAGMA temp_store = MEMORY")
        self.conn.execute("PRAGMA cache_size = -200000")
        self.conn.execute("PRAGMA locking_mode = EXCLUSIVE")

    def create_schema(self):
        self.conn.executescript(
            """
            DROP TABLE IF EXISTS meta;
            DROP TABLE IF EXISTS component_attributes;
            DROP TABLE IF EXISTS attribute_values;
            DROP TABLE IF EXISTS attribute_keys;
            DROP TABLE IF EXISTS components;
            DROP TABLE IF EXISTS categories;
            DROP TABLE IF EXISTS manufacturers;
            DROP TABLE IF EXISTS packages;
            DROP TABLE IF EXISTS component_fts;

            CREATE TABLE meta (
                key TEXT PRIMARY KEY NOT NULL,
                value TEXT NOT NULL
            );

            CREATE TABLE categories (
                category_id INTEGER PRIMARY KEY NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT NOT NULL,
                UNIQUE(category, subcategory)
            );

            CREATE TABLE manufacturers (
                manufacturer_id INTEGER PRIMARY KEY NOT NULL,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE packages (
                package_id INTEGER PRIMARY KEY NOT NULL,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE components (
                component_id INTEGER PRIMARY KEY NOT NULL,
                lcsc TEXT NOT NULL UNIQUE,
                category_id INTEGER NOT NULL REFERENCES categories(category_id),
                mfr TEXT NOT NULL,
                manufacturer_id INTEGER REFERENCES manufacturers(manufacturer_id),
                package_id INTEGER REFERENCES packages(package_id),
                joints INTEGER NOT NULL,
                stock INTEGER NOT NULL,
                basic INTEGER NOT NULL,
                preferred INTEGER NOT NULL,
                discontinued INTEGER NOT NULL,
                description TEXT NOT NULL,
                datasheet TEXT NOT NULL,
                price TEXT NOT NULL,
                img TEXT,
                url TEXT
            );

            CREATE TABLE attribute_keys (
                attribute_key_id INTEGER PRIMARY KEY NOT NULL,
                name TEXT NOT NULL UNIQUE
            );

            CREATE TABLE attribute_values (
                attribute_value_id INTEGER PRIMARY KEY NOT NULL,
                json TEXT NOT NULL UNIQUE
            );

            CREATE TABLE component_attributes (
                component_id INTEGER NOT NULL REFERENCES components(component_id),
                attribute_key_id INTEGER NOT NULL REFERENCES attribute_keys(attribute_key_id),
                attribute_value_id INTEGER NOT NULL REFERENCES attribute_values(attribute_value_id),
                PRIMARY KEY(component_id, attribute_key_id)
            ) WITHOUT ROWID;
            """
        )

        if self.with_fts:
            self.conn.execute(
                """
                CREATE VIRTUAL TABLE component_fts USING fts5(
                    lcsc,
                    mfr,
                    description,
                    content='',
                    columnsize=0,
                    detail='none',
                    tokenize='unicode61'
                )
                """
            )

    def get_or_create_category_id(self, category, subcategory):
        key = (category, subcategory)
        category_id = self.category_cache.get(key)
        if category_id is not None:
            return category_id

        row = self.conn.execute(
            "SELECT category_id FROM categories WHERE category = ? AND subcategory = ?",
            key,
        ).fetchone()
        if row is None:
            cur = self.conn.execute(
                "INSERT INTO categories(category, subcategory) VALUES (?, ?)",
                key,
            )
            category_id = cur.lastrowid
        else:
            category_id = row["category_id"]
        self.category_cache[key] = category_id
        return category_id

    def get_or_create_lookup_id(self, table, id_column, value_column, value, cache):
        if value in cache:
            return cache[value]
        row = self.conn.execute(
            f"SELECT {id_column} FROM {table} WHERE {value_column} = ?",
            (value,),
        ).fetchone()
        if row is None:
            cur = self.conn.execute(
                f"INSERT INTO {table}({value_column}) VALUES (?)",
                (value,),
            )
            value_id = cur.lastrowid
        else:
            value_id = row[id_column]
        cache[value] = value_id
        return value_id

    def get_or_create_manufacturer_id(self, name):
        if not name:
            return None
        return self.get_or_create_lookup_id(
            "manufacturers",
            "manufacturer_id",
            "name",
            name,
            self.manufacturer_cache,
        )

    def get_or_create_package_id(self, package):
        if not package:
            return None
        return self.get_or_create_lookup_id(
            "packages",
            "package_id",
            "name",
            package,
            self.package_cache,
        )

    def get_or_create_attr_key_id(self, name):
        return self.get_or_create_lookup_id(
            "attribute_keys",
            "attribute_key_id",
            "name",
            name,
            self.attr_key_cache,
        )

    def get_or_create_attr_value_id(self, value_json):
        return self.get_or_create_lookup_id(
            "attribute_values",
            "attribute_value_id",
            "json",
            value_json,
            self.attr_value_cache,
        )

    def insert_component(self, component_id, component):
        category_id = self.get_or_create_category_id(
            component["category"], component["subcategory"]
        )
        manufacturer_id = self.get_or_create_manufacturer_id(component.get("manufacturer", ""))
        package_id = self.get_or_create_package_id(component.get("package", ""))

        self.conn.execute(
            """
            INSERT INTO components(
                component_id, lcsc, category_id, mfr, manufacturer_id, package_id,
                joints, stock, basic, preferred, discontinued, description,
                datasheet, price, img, url
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (component_id,) + _component_row(component, category_id, manufacturer_id, package_id),
        )

        if self.with_fts:
            self.conn.execute(
                """
                INSERT INTO component_fts(rowid, lcsc, mfr, description)
                VALUES (?, ?, ?, ?)
                """,
                (
                    component_id,
                    component["lcsc"],
                    component["mfr"],
                    component["description"],
                ),
            )

        attr_rows = []
        for key, value in _normalized_attributes(component).items():
            attr_key_id = self.get_or_create_attr_key_id(key)
            attr_value_json = json.dumps(value, sort_keys=True, separators=(",", ":"))
            attr_value_id = self.get_or_create_attr_value_id(attr_value_json)
            attr_rows.append((component_id, attr_key_id, attr_value_id))

        if attr_rows:
            self.conn.executemany(
                """
                INSERT INTO component_attributes(
                    component_id, attribute_key_id, attribute_value_id
                )
                VALUES (?, ?, ?)
                """,
                attr_rows,
            )
            self.attribute_count += len(attr_rows)

    def finalize(self, started_at):
        self.conn.executescript(
            """
            CREATE INDEX components_category_id ON components(category_id);
            CREATE INDEX components_stock ON components(stock);
            CREATE INDEX components_manufacturer_id ON components(manufacturer_id);
            CREATE INDEX components_package_id ON components(package_id);
            CREATE INDEX component_attributes_key_value
                ON component_attributes(attribute_key_id, attribute_value_id, component_id);
            CREATE INDEX component_attributes_component_id
                ON component_attributes(component_id);
            """
        )

        self.conn.execute("ANALYZE")
        self.conn.execute("VACUUM")

        elapsed = time.monotonic() - started_at
        output_size = os.path.getsize(self.output_db)
        meta = {
            "source_db": self.source_db,
            "components": str(self.component_count),
            "component_attributes": str(self.attribute_count),
            "categories": str(
                self.conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
            ),
            "manufacturers": str(
                self.conn.execute("SELECT COUNT(*) FROM manufacturers").fetchone()[0]
            ),
            "packages": str(
                self.conn.execute("SELECT COUNT(*) FROM packages").fetchone()[0]
            ),
            "attribute_keys": str(
                self.conn.execute("SELECT COUNT(*) FROM attribute_keys").fetchone()[0]
            ),
            "attribute_values": str(
                self.conn.execute("SELECT COUNT(*) FROM attribute_values").fetchone()[0]
            ),
            "with_fts": "1" if self.with_fts else "0",
            "page_size": str(self.page_size),
            "build_seconds": f"{elapsed:.2f}",
            "output_bytes": str(output_size),
        }
        self.conn.executemany(
            "INSERT INTO meta(key, value) VALUES (?, ?)",
            list(meta.items()),
        )
        self.conn.commit()

    def build(self, ignoreoldstock=None, limit=None, verbose=False):
        started_at = time.monotonic()
        component_id = 1

        with self.conn:
            self.configure()
            self.create_schema()

            categories = self.src.categories()
            for category, subcategories in categories.items():
                for subcategory in subcategories:
                    components = self.src.getCategoryComponents(
                        category,
                        subcategory,
                        stockNewerThan=ignoreoldstock,
                    )
                    if not components:
                        continue

                    for component in components:
                        self.insert_component(component_id, component)
                        component_id += 1
                        self.component_count += 1
                        if limit is not None and self.component_count >= limit:
                            break

                    if verbose:
                        print(
                            f"{self.component_count} components, {self.attribute_count} attributes"
                        )
                    self.conn.commit()

                    if limit is not None and self.component_count >= limit:
                        break
                if limit is not None and self.component_count >= limit:
                    break

        self.finalize(started_at)

    def close(self):
        self.src.close()
        self.conn.close()


@click.command()
@click.argument("library", type=click.Path(dir_okay=False, exists=True))
@click.argument("output", type=click.Path(dir_okay=False))
@click.option(
    "--ignoreoldstock",
    type=int,
    default=None,
    help="Ignore components that weren't on stock for more than n days",
)
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Build at most this many components",
)
@click.option(
    "--page-size",
    type=int,
    default=4096,
    help="SQLite page size for the generated web DB",
)
@click.option(
    "--no-fts",
    is_flag=True,
    help="Skip the full text index to reduce build time and size",
)
@click.option("--verbose", is_flag=True, help="Be verbose")
def buildwebdb(library, output, ignoreoldstock, limit, page_size, no_fts, verbose):
    """
    Build a frontend-oriented SQLite database out of LIBRARY and save it to OUTPUT.
    """
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    builder = WebDbBuilder(
        source_db=library,
        output_db=output,
        page_size=page_size,
        with_fts=not no_fts,
    )
    try:
        builder.build(ignoreoldstock=ignoreoldstock, limit=limit, verbose=verbose)
    finally:
        builder.close()
