import re

def chipResistor(description):
    attrs = {}

    matches = re.search(r"\d+(.\d+)?[a-zA-Z]?Ohms", description)
    if matches is not None:
        attrs["Resistance"] = matches.group(0)

    matches = re.search(r"±\d+(.\d+)?%", description)
    if matches is not None:
        attrs["Tolerance"] = matches.group(0)

    matches = re.search(r"((\d+/\d+)|(\d+(.\d+)?[a-zA-Z]?))W", description)
    if matches is not None:
        attrs["Power"] = matches.group(0)

    return attrs