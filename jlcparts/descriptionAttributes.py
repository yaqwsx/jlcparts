import re

def chipResistor(description: str) -> dict:
    attrs = {}

    matches = re.search(r"\d+(\.\d+)?[a-zA-Z]?Ohms", description)
    if matches is not None:
        attrs["Resistance"] = matches.group(0)

    matches = re.search(r"±\d+(\.\d+)?%", description)
    if matches is not None:
        attrs["Tolerance"] = matches.group(0)

    matches = re.search(r"((\d+/\d+)|(\d+(.\d+)?[a-zA-Z]?))W", description)
    if matches is not None:
        attrs["Power"] = matches.group(0)

    return attrs

def capacitor(description: str) -> dict:
    attrs = {}

    matches = re.search(r"\d+(\.\d+)?[a-zA-Z]?F", description)
    if matches is not None:
        attrs["Capacitance"] = matches.group(0)

    matches = re.search(r"\d+(\.\d+)?[a-zA-Z]?V", description)
    if matches is not None:
        attrs["Voltage - Rated"] = matches.group(0)

    return attrs
