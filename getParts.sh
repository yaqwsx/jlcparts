#!/usr/bin/env bash

mkdir -p build
wget -O build/parts.xls https://jlcpcb.com/componentSearch/uploadComponentInfo
xls2csv build/parts.xls > build/parts.csv
