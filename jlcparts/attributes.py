import re
import sys

# This module tries to parse LSCS attribute strings into structured data The
# whole process is messy and there is no strong guarantee it will work in all
# cases: there are lots of inconsistencies and typos in the attributes. So we
# try to deliver best effort results

def erase(string, what):
    """
    Given a  string and a list of string, removes all occurences of items from
    what in the string
    """
    for x in what:
        string = string.replace(x, "")
    return string

def stringAttribute(value, name="default"):
    return {
        "format": "${" + name +"}",
        "primary": name,
        "values": {
            name: [value, "string"]
        }
    }

def readWithSiPrefix(value):
    """
    Given a string in format <number><unitPrefix> (without the actual unit),
    read its value. E.g., 10k ~> 10000, 10m ~> 0.01
    """
    value = value.strip()
    unitPrexies = {
        "p": 10e-12,
        "n": 10e-9,
        "u": 10e-6,
        "μ": 10e-6,
        "µ": 10e-6,
        "?": 10e-3, # There is common typo instead of 'm' there is '?' - the keys are close on keyboard
        "m": 10e-3,
        "k": 10e3,
        "M": 10e6,
        "G": 10e9
    }
    if value == "-" or value == "":
        return "NaN"
    if value[-1].isalpha() or value[-1] == "?": # Again, watch for the ? typo
        return float(value[:-1]) * unitPrexies[value[-1]]
    return float(value)

def readResistance(value):
    """
    Given a string, try to parse resistance and return it as Ohms (float)
    """
    value = erase(value, ["Ω", "Ohms", "Ohm"]).strip()
    unitPrefixes = {
        "m": [1e-3, 1e-6],
        "K": [1e3, 1],
        "k": [1e3, 1],
        "M": [1e6, 1e3]
    }
    for prefix, table in unitPrefixes.items():
        if prefix in value:
            split = [float(x) if x != "" else 0 for x in value.split(prefix)]
            value = split[0] * table[0] + split[1] * table[1]
            break
    if value == "-":
        value = "NaN"
    else:
        value = float(value)
    return value

def readCurrent(value):
    """
    Given a string, try to parse resistance and return it as Ohms (float)
    """
    value = value.replace("A", "").strip()
    return readWithSiPrefix(value)

def readVoltage(value):
    value = value.replace("V", "").strip()
    return readWithSiPrefix(value)

def readPower(value):
    """
    Parse power value (in watts), it can also handle fractions
    """
    if "/" in value:
        # Fraction
        matches = re.match(r"(\d+)/(\d+)(.*)", value)
        numerator = matches.group(1)
        denominator = matches.group(2)
        unit = matches.group(3).strip()
        value = str(float(numerator) / float(denominator)) + unit
    value = value.replace("W", "").strip()
    return readWithSiPrefix(value)

def resistanceAttribute(value):
    value = readResistance(value)
    return {
        "format": "${resistance}",
        "primary": "resistance",
        "values": {
            "resistance": [value, "resistance"]
        }
    }

def rdsOnMaxAtIdsAtVgs(value):
    """
    Given a string in format "<resistance> @ <current>, <voltage>" parse it and
    return it as structured value
    """
    def readRds(v):
        if value == "-":
            return "NaN", "NaN", "NaN"
        matched = re.match(r"(.*)@(.*),(.*)", v)
        # There are some transistors with a typo; using "A" instead of "V", fix it:
        voltage = matched.group(3).replace("A", "V")
        return (readResistance(matched.group(1)),
                readCurrent(matched.group(2)),
                readVoltage(voltage))
    if ";" in value:
        # Double P & N MOSFET
        s = value.split(";")
        rds1, id1, vgs1 = readRds(s[0])
        rds2, id2, vgs2 = readRds(s[1])
        return {
            "format": "${Rds 1} @ ${Id 1}, ${Vgs 1}; ${Rds 2} @ ${Id 2}, ${Vgs 2}",
            "primary": "Rds 1",
            "values": {
                "Rds 2": [rds2, "resistance"],
                "Id 2": [id2, "current"],
                "Vgs 2": [vgs2, "voltage"],
                "Rds 1": [rds1, "resistance"],
                "Id 1": [id1, "current"],
                "Vgs 1": [vgs1, "voltage"]
            }
        }
    else:
        rds, ids, vgs = readRds(value)
        return {
            "format": "${Rds} @ ${Id}, ${Vgs}",
            "primary": "Rds",
            "values": {
                "Rds": [rds, "resistance"],
                "Id": [ids, "current"],
                "Vgs": [vgs, "voltage"]
            }
        }

def continuousDrainCurrent(value):
    """
    Can parse values like '10A', '10A,12A', '1OA(Tc)'
    """
    value = re.sub(r"\(.*?\)", "", value) # Remove all notes about temperature
    value = value.replace("V", "A") # There are some typos - voltage instead of current
    if "," in value:
        # Double P & N MOSFET
        s = value.split(",")
        i1 = readCurrent(s[0])
        i2 = readCurrent(s[1])
        return {
            "format": "${Id 1}, ${Id 2}",
            "default": "Id 1",
            "values": {
                "Id 1": [i1, "current"],
                "Id 2": [i2, "current"]
            }
        }
    else:
        i = readCurrent(value)
        return {
            "format": "${Id}",
            "default": "Id",
            "values": {
                "Id": [i, "current"]
            }
        }

def drainToSourceVoltage(value):
    """
    Can parse single or double voltage values"
    """
    value = value.replace("A", "V") # There are some typos - current instead of voltage
    if "," in value:
        s = value.split(",")
        v1 = readVoltage(s[0])
        v2 = readVoltage(s[1])
        return {
            "format": "${Vds 1}, ${Vds 2}",
            "default": "Vds 1",
            "values": {
                "Vds 1": [v1, "voltage"],
                "Vds 2": [v1, "voltage"]
            }
        }
    else:
        v = readVoltage(value)
        return {
            "format": "${Vds}",
            "default": "Vds",
            "values": {
                "Vds": [v, "voltage"]
            }
        }

def powerDissipation(value):
    """
    Parse single or double power dissipation into structured value
    """
    value = re.sub(r"\(.*?\)", "", value) # Remove all notes about temperature
    if "," in value:
        s = value.split(",")
        p1 = readPower(s[0])
        p2 = readPower(s[1])
        return {
            "format": "${power 1}, ${power 2}",
            "default": "power 1",
            "values": {
                "power 1": [p1, "power"],
                "power 2": [p2, "power"]
            }
        }
    else:
        p = readPower(value)
        return {
            "format": "${power}",
            "default": "power",
            "values": {
                "power": [p, "power"]
            }
        }

def power(value):
    """
    Parse single power value
    """
    value = re.sub(r"\(.*?\)", "", value)
    p = readPower(value)
    return {
        "format": "${power}",
        "default": "Power",
        "values": {
            "power": [p, "power"]
        }
    }

def vgsThreshold(value):
    """
    Parse single or double value in format '<voltage> @ <current>'
    """
    def readVgs(v):
        if value == "-":
            return "NaN", "NaN"
        matched = re.match(r"(.*)@(.*)", v)
        return readVoltage(matched.group(1)), readCurrent(matched.group(2))

    value = re.sub(r"\(.*?\)", "", value)
    if "," in value:
        s = value.split(",")
        v1, i1 = readVgs(s[0])
        v2, i2 = readVgs(s[1])
        return {
            "format": "${Vgs 1} @ ${Id 1}, ${Vgs 2} @ ${Id 2}",
            "default": "Vgs 1",
            "values": {
                "Vgs 1": [v1, "voltage"],
                "Id 1": [i1, "current"],
                "Vgs 2": [v2, "voltage"],
                "Id 2": [i2, "current"]
            }
        }
    else:
        v, i = readVgs(value)
        return {
            "format": "${Vgs} @ ${Id}",
            "default": "Vgs",
            "values": {
                "Vgs": [v, "voltage"],
                "Id": [i, "current"]
            }
        }