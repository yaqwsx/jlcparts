
// Return comparator for given quantity
export function quantityComparator(quantityName) {
    const numericQuantities = [
        "resistance", "voltage", "current", "power", "count", "capacitance",
        "length", "inductance", "temperature", "charge"
    ];
    if (numericQuantities.includes(quantityName))
        return numericComparator;
    return (a, b) => String(a).localeCompare(String(b));
}

// Return formatter for given quantity
export function quantityFormatter(quantityName) {
    const formatters = {
        resistance: resistanceFormatter,
        voltage: siFormatter("V"),
        current: siFormatter("A"),
        power: siFormatter("W"),
        capacitance: siFormatter("F"),
        frequency: siFormatter("Hz"),
        length: siFormatter("m"),
        inductance: siFormatter("H"),
        charge: siFormatter("C"),
        count: x => String(x),
        temperature: x => `${x} °C`
    };

    let formatter = formatters[quantityName];
    if (formatter)
        return formatter
    return x => String(x);
}

function numericComparator(a, b) {
    if (a === "NaN")
        a = undefined;
    if (b === "NaN")
        b = undefined;
    if (a === undefined && b === undefined)
        return 0;
    if (a === undefined)
        return 1;
    if (b === undefined)
        return -1;

    return a - b;
}

// Format values like 1u6, 1k6, 1M9
function infixMagnitudeFormatter(value, letter, order) {
    value = value / order;
    let integralPart = Math.floor(value);
    let fractionalPart = (value - integralPart) * 1000; // Number of significant digits
    let fractionalPartStr = fractionalPart.toFixed().replace(/0*$/,'');

    return String(integralPart) + letter + fractionalPartStr;
}

function siFormatterImpl(value, unit) {
    if (value === "NaN")
        return "-";
    if (value === 0)
        return "0 " + unit;
    let prefixes = [
        { magnitude: 1e-12, prefix: "p" },
        { magnitude: 1e-9, prefix: "n" },
        { magnitude: 1e-6, prefix: "μ" },
        { magnitude: 1e-3, prefix: "m" },
        { magnitude: 1, prefix: "" },
        { magnitude: 1e3, prefix: "k" },
        { magnitude: 1e6, prefix: "M" },
        { magnitude: 1e9, prefix: "G" }
    ];
    // Choose prefix to use
    let prefix;
    for (var idx = 0; idx < prefixes.length; idx++) {
        if (idx === prefixes.length - 1 || Math.abs(value) < prefixes[idx + 1].magnitude) {
            prefix = prefixes[idx];
            break;
        }
    }

    return (value / prefix.magnitude)
                .toFixed(6)
                .replace(/0*$/,'')
                .replace(/[.,]$/,'') + " " + prefix.prefix + unit;
}

function siFormatter(unit) {
    return value => siFormatterImpl(value, unit);
}

function resistanceFormatter(resistance) {
    if (resistance === "NaN")
        return "-"
    if (resistance === 0)
        return "0R";
    if (resistance < 1) {
        return (resistance * 1000).toFixed(6).replace(/0*$/,'').replace(/[.,]$/,'') + "mR";
    }
    if (resistance < 1e3) {
        // Format with R, e.g., 1R 5R6
        return infixMagnitudeFormatter(resistance, "R", 1);
    }
    if (resistance < 1e6) {
        // Format with k, e.g, 3k3 56k
        return infixMagnitudeFormatter(resistance, "k", 1e3);
    }
    if (resistance < 1e9) {
        // Format with M, e.g., 1M, 5M6
        return infixMagnitudeFormatter(resistance, "M", 1e6);
    }
    // Format with G
    return infixMagnitudeFormatter(resistance, "G", 1e9);
}
