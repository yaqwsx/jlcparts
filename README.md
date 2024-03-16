![Logo](web/public/favicon.svg)

# JLCPCB SMD Assembly Component Catalogue

A better tool to browse the components offered by the [JLCPCB SMT Assembly
Service](https://jlcpcb.com/smt-assembly).

## How To Use It?

Just visit: [https://yaqwsx.github.io/jlcparts/](https://yaqwsx.github.io/jlcparts/)

The site and parts cache is hosted on GitHub Pages.

## Why?

Probably all of us love JLCPCB SMT assembly service. It is easy to use, cheap
and fast. However, you can use only components from [their
catalogue](https://jlcpcb.com/parts). This is not as bad, since the library is
quite broad. However, the library UI sucks. You can only browse the categories and do full-text searches. You cannot do parametric search nor sort by property.

That's why I created a simple page which presents the catalogue in much nicer
form. You can:
- do full-text search
- browse categories
- parametric search
- sort by any component attribute
- sort by price based on quantity
- easily access datasheet and LCSC product page

## Do You Enjoy It? Does It Make Your Life Easier?

[![ko-fi](https://www.ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/E1E2181LU)

Support on Ko-Fi allows me to develop such tools as this one and perform
hardware-related experiments.

## What Does It Look Like?

### Title Page

![Preview 1](https://user-images.githubusercontent.com/1590880/93708766-32ab0d80-fb39-11ea-8365-da2ca1b13d8b.jpg)

### Property Filter

![Preview 2](https://user-images.githubusercontent.com/1590880/93708599-e01d2180-fb37-11ea-96b6-5d5eb4e0f285.jpg)

### Component Detail

![Preview 3](https://user-images.githubusercontent.com/1590880/93708601-e0b5b800-fb37-11ea-84ed-6ba73f07911d.jpg)


## How Does It Work?

The page has no backend so it can be easily hosted on GitHub Pages.
GitHub Actions downloads the XLSX spreadsheet from the JLCPCB page, and then
a Python script processes it and generates a per-category JSON file with components.

The frontend uses IndexedDB in the browser to store the component library and
perform queries on it. Therefore, before the first use, the page downloads the
component library (it can take a while). Then, all the queries are performed
locally.

## Development

To get started with developing the frontend, you will need NodeJS & Python 3.

Set up the Python portion of the program by running:

```bash
$ virtualenv venv
$ source venv/bin/activate
$ pip install -e .
```

Then to download the cached parts list (from the GH Pages site, generated via GH Actions) and process it, run:

```bash
$ wget https://yaqwsx.github.io/jlcparts/data/cache.zip https://yaqwsx.github.io/jlcparts/data/cache.z0{1..8}
$ 7z x cache.zip
$ mkdir -p web/public/data/
$ jlcparts buildtables --jobs 0 --ignoreoldstock 30 cache.sqlite3 web/public/data
```

To understand how the GH Actions generate the cache zip file, refer to the
[update_components.yaml workflow](.github/workflows/update_components.yaml).

To launch the frontend web server, run:

```bash
$ cd web
$ npm install
$ npm start
```

## Reporting Issues

If the page is broken, feel free to open an issue on GitHub.

## Related Projects

- [KiKit](https://github.com/yaqwsx/KiKit): a tool for automatic panelization of
  KiCAD PCBs. It can also perform fully automatic export of manufacturing data
  for JLCPCB assembly - read [the
  documentation](https://github.com/yaqwsx/KiKit/blob/master/doc/fabrication/jlcpcb.md)
  or produce a solder-paste stencil for populating components missing at JLCPCB - read [the
  documentation](https://github.com/yaqwsx/KiKit/blob/master/doc/stencil.md).
- [PcbDraw](https://github.com/yaqwsx/PcbDraw): a tool for making nice schematic
  drawings of your boards and population manuals.
