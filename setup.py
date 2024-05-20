# -*- coding: utf-8 -*-

import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="jlcparts",
    version="0.1.0",
    author="Jan Mrázek",
    author_email="email@honzamrazek.cz",
    description="Better view of JLCPCB parts",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yaqwsx/jlcparts",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    install_requires=[
        "requests",
        "click",
        "lxml"
    ],
    setup_requires=[

    ],
    zip_safe=False,
    include_package_data=True,
    entry_points = {
        "console_scripts": [
            "jlcparts=jlcparts.ui:cli"
        ],
    }
)
