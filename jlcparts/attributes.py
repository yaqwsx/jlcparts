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
        "p": 1e-12,
        "n": 1e-9,
        "u": 1e-6,
        "μ": 1e-6,
        "µ": 1e-6,
        "?": 1e-3, # There is a common typo instead of 'm' there is '?' - the keys are close on keyboard
        "m": 1e-3,
        "k": 1e3,
        "K": 1e3,
        "M": 1e6,
        "G": 1e9
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
    value = erase(value, ["Ω", "Ohms", "Ohm", "(Max)", "Max"]).strip()
    value = value.replace(" ", "") # Sometimes there are spaces after decimal place
    unitPrefixes = {
        "m": [1e-3, 1e-6],
        "K": [1e3, 1],
        "k": [1e3, 1],
        "M": [1e6, 1e3],
        "G": [1e9, 1e6]
    }
    for prefix, table in unitPrefixes.items():
        if prefix in value:
            split = [float(x) if x != "" else 0 for x in value.split(prefix)]
            value = split[0] * table[0] + split[1] * table[1]
            break
    if value == "-" or value == "" or value == "null":
        value = "NaN"
    else:
        value = float(value)
    return value

def readCurrent(value):
    """
    Given a string, try to parse current and return it as Amperes (float)
    """
    value = erase(value, ["PNP"])
    value = value.replace("A", "").strip()
    value = value.split("..")[-1] # Some transistors give a range for current in Rds
    return readWithSiPrefix(value)

def readVoltage(value):
    value = value.replace("v", "V")
    value = value.replace("V-", "V")
    value = value.replace("V", "").strip()
    if value in ["-", "--"] or "null" in value:
        return "NaN"
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

def readCapacitance(value):
    value = value.replace("F", "").strip()
    return readWithSiPrefix(value)

def readCharge(value):
    value = value.replace("C", "").strip()
    return readWithSiPrefix(value)

def readFrequency(value):
    value = erase(value, ["Hz", "HZ"]).strip()
    return readWithSiPrefix(value)

def readInductance(value):
    value = value.replace("H", "").strip()
    return readWithSiPrefix(value)

def resistanceAttribute(value):
    if ";" in value:
        # This is a resistor array
        values = value.split(value)
        values = [readResistance(x.strip()) for x in values]
        values = { "resistance" + (str(i + 1) if i != 0 else ""): [x, "resistance"] for i, x in enumerate(values)}
        format = ", ".join(values.keys())
        return {
            "format": format,
            "primary": "resistance",
            "values": values
        }
    else:
        value = readResistance(value)
        return {
            "format": "${resistance}",
            "primary": "resistance",
            "values": {
                "resistance": [value, "resistance"]
            }
        }

def impedanceAttribute(value):
    value = readResistance(value)
    return {
        "format": "${impedance}",
        "primary": "impedance",
        "values": {
            "impedance": [value, "resistance"]
        }
    }


def voltageAttribute(value):
    value = re.sub(r"\(.*?\)", "", value)
     # Remove multiple current values
    value = value.split("x")[-1]
    value = value.split("/")[-1]
    value = value.split(",")[-1]
    value = value.split("~")[-1]
    value = value.split("or")[-1]
    value = value.replace("VIN", "V").replace("Vin", "V")
    value = value.replace("VDC", "V").replace("VAC", "V")
    value = value.replace("Vdc", "V").replace("Vac", "V")
    value = value.replace("X1:", "")
    value = value.replace("A", "V") # Common typo
    value = erase(value, "±")
    value = re.sub(";.*", "", value)

    if value.strip() in ["-", "Tracking", "nV"]:
        value = "NaN"
    else:
        value = readVoltage(value)
    return {
        "format": "${voltage}",
        "primary": "voltage",
        "values": {
            "voltage": [value, "voltage"]
        }
    }

def currentAttribute(value):
    if value.lower().strip() == "adjustable":
        return {
            "format": "${current}",
            "default": "current",
            "values": {
                "current": ["NaN", "current"]
            }
        }
    if ";" in value:
        values = value.split(value)
        values = [readCurrent(x.strip()) for x in values]
        values = { "current" + (str(i + 1) if i != 0 else ""): [x, "current"] for i, x in enumerate(values)}
        format = ", ".join(values.keys())
        return {
            "format": format,
            "primary": "current",
            "values": values
        }
    else:
        value = erase(value, ["±", "Up to"])
        value = re.sub(r"\(.*?\)", "", value)
        # Remove multiple current values
        value = value.split("x")[-1]
        value = value.split("/")[-1]
        value = value.split(",")[-1]
        value = value.split("~")[-1]
        value = value.split("or")[-1]
        # Replace V/A typo
        value = value.replace("V", "A")
        value = readCurrent(value)
        return {
            "format": "${current}",
            "primary": "current",
            "values": {
                "current": [value, "current"]
            }
        }

def powerAttribute(value):
    value = re.sub(r"\(.*?\)", "", value)
    # Replace V/W typo
    value = value.replace("V", "W")
    # Strip random additional characters (e.g., C108632)
    value = value.replace("S", "")

    p = readPower(value)
    return {
        "format": "${power}",
        "default": "power",
        "values": {
            "power": [p, "power"]
        }
    }

def countAttribute(value):
    if value == "-":
        return {
            "format": "${count}",
            "default": "count",
            "values": {
                "count": ["NaN", "count"]
            }
        }
    value = erase(value, [" - Dual"])
    value = re.sub(r"\(.*?\)", "", value)
    # There are expressions like a+b, so let's sum them
    try:
        count = sum(map(int, value.split("+")))
    except ValueError:
        # Sometimes, there are floats in number of pins... God, why?
        # See, e.g., C2836126
        count = sum(map(float, value.split("+")))
    return {
        "format": "${count}",
        "default": "count",
        "values": {
            "count": [count, "count"]
        }
    }


def capacitanceAttribute(value):
    # There are a handful of components, that feature multiple capacitance
    # values, for the sake of the simplicity, take the last one.
    value = readCapacitance(value.split(";")[-1].strip())
    return {
        "format": "${capacitance}",
        "primary": "capacitance",
        "values": {
            "capacitance": [value, "capacitance"]
        }
    }

def inductanceAttribute(value):
    value = readInductance(value)
    return {
        "format": "${inductance}",
        "primary": "inductance",
        "values": {
            "inductance": [value, "inductance"]
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
        v = v.replace("，", ",") # Replace special unicode characters
        matched = re.match(r"(.*)\s*@\s*(.*)\s*,\s*(.*)", v)
        if matched is None:
            matched = re.match(r"(.*)\s+(.*),(.*)", v) # Sometimes there is no @
        # There are some transistors with a typo; using "A" instead of "V" or Ω, fix it:
        resistance = matched.group(1).replace("A", "Ω")
        voltage = matched.group(3).replace("A", "V")
        if "~" in voltage:
            voltage = voltage.split("~")[-1]
        return (readResistance(resistance),
                readCurrent(matched.group(2)),
                readVoltage(voltage))
    if value.count(",") == 3 or ";" in value:
        # Double P & N MOSFET
        if ";" in value:
            s = value.split(";")
        else:
            s = value.split(",")
            s = [s[0] + "," + s[1], s[2] + "," + s[3]]
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

def rdsOnMaxAtVgsAtIds(value):
    """
    Given a string in format "<resistance> @ <voltage>, <current>" parse it and
    return it as structured value
    """
    def readRds(v):
        if value == "-":
            return "NaN", "NaN", "NaN"
        v = v.replace("，", ",") # Replace special unicode characters
        # There is sometimes missing comma
        v = re.sub(r"V(\d)", r"V,\1", v)
        matched = re.match(r"(.*)\s*@\s*(.*)\s*,\s*(.*)", v)
        if matched is None:
            matched = re.match(r"(.*)\s+(.*),(.*)", v) # Sometimes there is no @
        resistance = matched.group(1).strip()
        voltage = matched.group(2).strip()
        current = matched.group(3).strip()
        # There are sometimes swapped values
        if current.endswith("V") and (voltage.endswith("A") or voltage.endswith("m")):
            current, voltage = voltage, current
        if voltage.endswith("A"):
            voltage = voltage.replace("A", "V")
        if "~" in voltage:
            voltage = voltage.split("~")[-1]
        if current.endswith("V"):
            current = current.replace("V", "A")
        if not current.endswith("A"):
            current += "A"
        return (readResistance(resistance),
                readCurrent(current),
                readVoltage(voltage))
    if value.count(",") == 3 or ";" in value:
        # Double P & N MOSFET
        if ";" in value:
            s = value.split(";")
        else:
            s = value.split(",")
            s = [s[0] + "," + s[1], s[2] + "," + s[3]]
        rds1, id1, vgs1 = readRds(s[0])
        rds2, id2, vgs2 = readRds(s[1])
        return {
            "format": "${Rds 1} @ ${Vgs 1}, ${Id 1}; ${Rds 2} @ ${Vgs 2}, ${Id 2}",
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
            "format": "${Rds} @ ${Vgs}, ${Id}",
            "primary": "Rds",
            "values": {
                "Rds": [rds, "resistance"],
                "Id": [ids, "current"],
                "Vgs": [vgs, "voltage"]
            }
        }


def continuousTransistorCurrent(value, symbol):
    """
    Can parse values like '10A', '10A,12A', '1OA(Tc)'
    """
    value = re.sub(r"\(.*?\)", "", value) # Remove all notes about temperature
    value = erase(value, ["±"])
    value = value.replace("V", "A") # There are some typos - voltage instead of current
    value = value.replace(";", ",") # Sometimes semicolon is used instead of comma
    if "," in value:
        # Double P & N MOSFET
        s = value.split(",")
        i1 = readCurrent(s[0])
        i2 = readCurrent(s[1])
        return {
            "format": "${" + symbol + " 1}, ${" + symbol + " 2}",
            "default": symbol + " 1",
            "values": {
                symbol + " 1": [i1, "current"],
                symbol + " 2": [i2, "current"]
            }
        }
    else:
        i = readCurrent(value)
        return {
            "format": "${" + symbol + "}",
            "default": symbol,
            "values": {
                symbol: [i, "current"]
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
    value = value.replace("V", "W") # Common typo
    if "A" in value:
        # The value is a clear nonsense
        return {
            "format": "${power}",
            "default": "power",
            "values": {
                "power": ["NaN", "power"]
            }
        }
    value = value.split("/")[-1] # When there are multiple thermal ratings for
        # transistors, choose the last as it is the most interesting one
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

def vgsThreshold(value):
    """
    Parse single or double value in format '<voltage> @ <current>'
    """
    def readVgs(v):
        if value == "-":
            return "NaN", "NaN"
        matched = re.match(r"(.*?)(@| )(.*)", v)
        return readVoltage(matched.group(1)), readCurrent(matched.group(3))

    value = re.sub(r"\(.*?\)", "", value)
    if "," in value or ";" in value:
        splitchar = "," if "," in value else ";"
        s = value.split(splitchar)
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

def esr(value):
    """
    Parse equivalent series resistance in the form '<resistance> @ <frequency>'
    """
    if value == "-":
        return {
            "format": "-",
            "default": "esr",
            "values": {
                "esr": ["NaN", "resistance"],
                "frequency": ["NaN", "frequency"]
            }
        }
    value = erase(value, ["(", ")"]) # For resonators, the value is enclosed in parenthesis
    matches = re.search(r"\d+(\.\d+)?\s*?[a-zA-Z]?(Ohm|Ω)", value)
    res = readResistance(matches.group(0).replace(" ", ""))

    matches = re.search(r"\d+(\.\d+)?[a-zA-Z]?Hz", value)
    if matches:
        freq = readFrequency(matches.group(0))
        return {
            "format": "${esr} @ ${frequency}",
            "default": "esr",
            "values": {
                "esr": [res, "resistance"],
                "frequency": [freq, "frequency"]
            }
        }
    else:
        return {
            "format": "${esr}",
            "default": "esr",
            "values": {
                "esr": [res, "resistance"]
            }
        }

def rippleCurrent(value):
    if value == "-":
        return {
            "format": "-",
            "default": "current",
            "values": {
                "current": ["NaN", "current"],
                "frequency": ["NaN", "frequency"]
            }
        }
    s = value.split("@")
    if len(s) == 1:
        s = value.split(" ")
    i = readCurrent(s[0])
    if len(s) > 1:
        f = readFrequency(s[1].split("~")[-1])
    else:
        f = "NaN"
    return {
        "format": "${current} @ ${frequency}",
        "default": "current",
        "values": {
            "current": [i, "current"],
            "frequency": [f, "frequency"]
        }
    }

def sizeMm(value):
    if value == "-":
        return {
            "format": "-",
            "default": "width",
            "values": {
                "width": ["NaN", "length"],
                "height": ["NaN", "length"]
            }
        }
    value = value.lower()
    s = value.split("x")
    w = float(s[0]) / 1000
    h = float(s[1]) / 1000
    return {
        "format": "${width}×${height}",
        "default": "width",
        "values": {
            "width": [w, "length"],
            "height": [h, "length"]
        }
    }

def forwardVoltage(value):
    if value == "-":
        return {
            "format": "-",
            "default": "Vf",
            "values": {
                "Vf": ["NaN", "voltage"],
                "If": ["NaN", "current"]
            }
        }
    value = erase(value, ["<"])
    value = re.sub(r"\(.*?\)", "", value)
    s = value.split("@")

    vStr = s[0].replace("A", "V") # Common typo
    v = readVoltage(vStr)
    i = readCurrent(s[1])
    return {
        "format": "${Vf} @ ${If}",
        "default": "Vf",
        "values": {
            "Vf": [v, "voltage"],
            "If": [i, "current"]
        }
    }

def removeColor(string):
    """
    If there is a color name in the string, remove it
    """
    return erase(string, ["Red", "Green", "Blue", "Orange", "Yellow"])

def voltageRange(value):
    if value == "-":
        return {
            "format": "-",
            "default": "Vmin",
            "values": {
                "Vmin": ["NaN", "voltage"],
                "Vmax": ["NaN", "voltage"]
            }
        }
    value = re.sub(r"\(.*?\)", "", value)
    value = value.replace("A", "V") # Common typo
    value = value.split(",")[0] # In the case of multivalue range
    if ".." in value:
        s = value.split("..")
    elif "-" in value:
        s = value.split("-")
    else:
        s = value.split("~")
    s = [removeColor(x) for x in s] # Something there is the color in the attributes
    vMin = s[0].split(",")[0].split("/")[0]
    vMin = readVoltage(vMin)
    if len(s) == 2:
        return {
            "format": "${Vmin} ~ ${Vmax}",
            "default": "Vmin",
            "values": {
                "Vmin": [vMin, "voltage"],
                "Vmax": [readVoltage(s[1]), "voltage"]
            }
        }
    return {
            "format": "${Vmin}",
            "default": "Vmin",
            "values": {
                "Vmin": [vMin, "voltage"]
            }
        }

def clampingVoltage(value):
    if value == "-":
        return {
            "format": "-",
            "default": "Vc",
            "values": {
                "Vc": ["NaN", "voltage"],
                "Ic": ["NaN", "current"]
            }
        }
    value = re.sub(r"\(.*?\)", "", value)
    s = value.split("@")
    vC = s[0].split(",")[0].split("/")[0]
    vC = vC.replace("A", "V") # Common typo
    vC = readVoltage(vC)
    if len(s) == 2:
        c = s[1].replace("V", "A") # Common typo
        return {
            "format": "${Vc} @ ${Ic}",
            "default": "Vc",
            "values": {
                "Vc": [vC, "voltage"],
                "Ic": [readCurrent(c), "current"]
            }
        }
    return {
            "format": "${Vc}",
            "default": "Vc",
            "values": {
                "Vc": [vC, "voltage"]
            }
        }

def vceBreakdown(value):
    value = erase(value, "PNP").split(",")[0]
    return voltageAttribute(value)

def vceOnMax(value):
    matched = re.match(r"(.*)@(.*),(.*)", value)
    if matched:
        vce = readVoltage(matched.group(1))
        vge = readVoltage(matched.group(2))
        ic = readCurrent(matched.group(3))
    else:
        vce = "NaN"
        vge = "NaN"
        ic = "NaN"
    return {
        "format": "${Vce} @ ${Vge}, ${Ic}",
        "default": "Vce",
        "values": {
            "Vce": [vce, "voltage"],
            "Vge": [vge, "voltage"],
            "Ic": [ic, "current"]
        }
    }

def temperatureAttribute(value):
    if value == "-":
        return {
            "format": "-",
            "default": "temperature",
            "values": {
                "temperature": ["NaN", "temperature"]
            }
        }
    value = erase(value, ["@"])
    value = re.sub(r"\(.*?\)", "", value)
    value = value.strip()
    assert value.endswith("℃")
    value = erase(value, ["℃"])
    v = int(value)
    return {
        "format": "${temperature}",
        "default": "temperature",
        "values": {
            "temperature": [v, "temperature"]
        }
    }

def capacityAtVoltage(value):
    """
    Parses <capacity> @ <voltage>
    """
    if value == "-":
        return {
            "format": "-",
            "default": "capacity",
            "values": {
                "capacity": ["NaN", "capacitance"],
                "voltage": ["NaN", "voltage"]
            }
        }
    def readTheTuple(value):
        try:
            c, v = tuple(value.split("@"))
        except:
            c, v = tuple(value.split(" "))
        c = readCapacitance(c.strip())
        v = readVoltage(v.strip())
        return c, v
    if ";" in value:
        a, b = tuple(value.split(";"))
        c1, v1 = readTheTuple(a)
        c2, v2 = readTheTuple(b)
        return {
            "format": "${capacity 1} @ ${voltage 1}; {capacity 2} @ ${voltage 2}",
            "default": "capacity 1",
            "values": {
                "capacity 1": [c1, "capacitance"],
                "voltage 1": [v1, "voltage"],
                "capacity 2": [c2, "capacitance"],
                "voltage 2": [v2, "voltage"]
            }
        }
    c, v = readTheTuple(value)
    return {
            "format": "${capacity} @ ${voltage}",
            "default": "capacity",
            "values": {
                "capacity": [c, "capacitance"],
                "voltage": [v, "voltage"]
            }
        }

def chargeAtVoltage(value):
    """
    Parses <charge> @ <voltage>
    """
    if value == "-":
        return {
            "format": "-",
            "default": "charge",
            "values": {
                "charge": ["NaN", "capacitance"],
                "voltage": ["NaN", "voltage"]
            }
        }
    def readTheTuple(value):
        try:
            q, v = tuple(value.split("@"))
        except:
            q, v = tuple(value.split(" "))
        q = readCharge(q.strip())
        if "/" in v:
            v = v.split("/")[-1]
        v = readVoltage(re.sub(r'-?\d+~', '', v.strip()))
        return q, v

    if ";" in value:
        a, b = tuple(value.split(";"))
        q1, v1 = readTheTuple(a)
        q2, v2 = readTheTuple(b)
        return {
            "format": "${charge 1} @ ${voltage 1}; ${charge 2} @ ${voltage 2}",
            "default": "charge 1",
            "values": {
                "charge 1": [q1, "charge"],
                "voltage 1": [v2, "voltage"],
                "charge 2": [q2, "charge"],
                "voltage 2": [v2, "voltage"]
            }
        }

    q, v = readTheTuple(value)
    return {
            "format": "${charge} @ ${voltage}",
            "default": "charge",
            "values": {
                "charge": [q, "charge"],
                "voltage": [v, "voltage"]
            }
        }
