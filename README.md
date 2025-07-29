![Logo](web/public/favicon.svg)

# JLC PCB SMD Assembly Component Catalogue

A better tool to browse the components offered by the [JLC PCB SMT Assembly
Service](https://jlcpcb.com/smt-assembly).

## How To Use It?

Just visit: [https://yaqwsx.github.io/jlcparts/](https://yaqwsx.github.io/jlcparts/)

## Why?

Probably all of us love JLC PCB SMT assembly service. It is easy to use, cheap
and fast. However, you can use only components from [their
catalogue](https://jlcpcb.com/parts). This is not as bad, since the library is
quite broad. However, the library UI sucks. You can only browse the categories,
do full-text search. You cannot do parametric search nor sort by property.
That's why I created a simple page which presents the catalogue in much nicer
form. You can:
- do full-text search
- browse categories
- parametric search
- sort by any component attribute
- sort by price based on quantity
- easily access datasheet and LCSC product page.

## Do You Enjoy It? Does It Make Your Life Easier?

[![ko-fi](https://www.ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/E1E2181LU)

Support on Ko-Fi allows me to develop such tools as this one and perform
hardware-related experiments.

## How Does It Look Like?

Title page

![Preview 1](https://user-images.githubusercontent.com/1590880/93708766-32ab0d80-fb39-11ea-8365-da2ca1b13d8b.jpg)

Property filter

![Preview 2](https://user-images.githubusercontent.com/1590880/93708599-e01d2180-fb37-11ea-96b6-5d5eb4e0f285.jpg)

Component detail

![Preview 3](https://user-images.githubusercontent.com/1590880/93708601-e0b5b800-fb37-11ea-84ed-6ba73f07911d.jpg)


## How Does It Work?

The page has no backend so it can be easily hosted on GitHub Pages. Therefore,
Travis CI download XLS spreadsheet from the JLC PCB page, a Python script
process it and it generates per-category JSON file with components.

The frontend uses IndexedDB in the browser to store the component library and
perform queries on it. Therefore, before the first use, you have to download the
component library and it can take a while. Then, all the queries are performed
locally.

## Development

To get started with developing the frontend, you will need NodeJS & Python 3.

Set up the Python portion of the program by running:

```
$ virtualenv venv
$ source venv/bin/activate
$ pip install -e .
```

Download the cached parts database as shown in the [GitHub Actions workflow](https://github.com/yaqwsx/jlcparts/blob/master/.github/workflows/update_components.yaml),
then process it:

```
$ mkdir -p web/public/data/
$ jlcparts buildtables --jobs 0 --ignoreoldstock 30 cache.sqlite3 web/public/data
```

To launch the frontend web server, run:

```
$ cd web
$ npm install
$ npm start
```

### Attribute Normalization Tests

When changing one attribute normalization rule, use the focused section scan
instead of rebuilding the whole generated database:

```
$ PYTHONPATH=. pytest -q test/test_attribute_section_scan.py --attribute-section 'Peak Forward Surge Current'
```

If `cache-v2.sqlite3` is present in the repository root, this command reads raw
values for only that selected section directly from the compact source database.
It does not rebuild the frontend datatables.

Pass `--attribute-section` multiple times to test a small batch. To test raw
values before rebuilding datatables, pass them directly:

```
$ PYTHONPATH=. pytest -q test/test_attribute_section_scan.py \
    --attribute-section 'Vbo (Range Value)' \
    --attribute-value '35V~45V'
```

To test one section against a non-default compact source database path, point
the same test at it explicitly:

```
$ PYTHONPATH=. pytest -q test/test_attribute_section_scan.py \
    --attribute-section 'Peak Forward Surge Current' \
    --attribute-source-db cache-v2.sqlite3
```

The legacy `cache.sqlite3` format is also supported with `--attribute-sqlite`,
but it is slower because raw attributes are stored inside larger JSON blobs.

For textual sections whose values do not contain numbers, include all generated
strings explicitly:

```
$ PYTHONPATH=. pytest -q test/test_attribute_section_scan.py \
    --attribute-section 'Features' \
    --attribute-all-strings
```

## The Page Is Broken!

Feel free to open an issue on GitHub.

## You Might Also Be Interested

- [KiKit](https://github.com/yaqwsx/KiKit): a tool for automatic panelization of
  KiCAD PCBs. It can also perform fully automatic export of manufacturing data
  for JLC PCB assembly - read [the
  documentation](https://github.com/yaqwsx/KiKit/blob/master/docs/fabrication/jlcpcb.md)
  or produce a solder-paste stencil for populating components missing at JLC PCB - read [the
  documentation](https://github.com/yaqwsx/KiKit/blob/master/doc/stencil.md).
- [PcbDraw](https://github.com/yaqwsx/PcbDraw): a tool for making nice schematic
  drawings of your boards and population manuals.
