import React, { useState, useEffect } from 'react';
import sliders from './sliders.svg';    // nicer slider icon than fa-sliders-h
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';

const rangePattern = getRangePattern();

function RangeSelect({ icon, title, options, onRangeChange }) {
    const [isOpen, setIsOpen] = useState(false);
    const [visible, setVisible] = useState(false);

    const [lowerBound, setLowerBound] = useState('');
    const [upperBound, setUpperBound] = useState('');


    const applyFilter = () => {
        setIsOpen(false);

        setTimeout(() => {
            const lb = valueFromString(lowerBound); // convert number and unit from string
            const ub = valueFromString(upperBound);

            if (lb !== null || ub !== null) {
                let ranges = options.map(o => rangeFromStr(o.value));
                if (lb !== null) {
                    ranges = ranges.map(r => r && r.low <= lb ? r : null);
                }
                if (ub !== null) {
                    ranges = ranges.map(r => r && r.high >= ub ? r : null);
                }

                onRangeChange && onRangeChange(options.filter((o, i) => ranges[i] != null));
            } else {
                onRangeChange && onRangeChange(options);    // default to every selected
            }
        }, 0);
    };

    // check if values are ranges
    useEffect(() => {
        const ranges = options.filter(o => rangePattern.test(o.value));
        const inRange = ranges.length >= options.length / 2;
        setVisible(inRange);
    }, [options])

    if (visible) {
        if (!isOpen) {
            return <div style={{ position: 'absolute', right: 0, bottom: 0 }} title={title} className='mr-1'>
                <button onClick={() => setIsOpen(true)} >
                    {icon || <img src={sliders} style={{ width: '1.5em' }} alt='' />}
                </button>
            </div>;
        }
        else {
            return <div style={{ position: 'absolute', inset: 0, width: '100%' }} className='bg-blue-500'>
                <div className='flex' style={{ flexFlow: 'row' }}>
                    <div style={{ width: '100%', whiteSpace: 'nowrap' }}>Low bound max.</div>
                    <div className='mr-1'><input style={{height: '1.2em'}} className='w-full rounded bg-white pl-1' value={lowerBound} onChange={e => setLowerBound(e.target.value)}></input></div>
                </div>
                <div className='flex mt-1' style={{ flexFlow: 'row' }}>
                    <div style={{ width: '100%', whiteSpace: 'nowrap' }}>High bound min.</div>
                    <div className='mr-1'><input style={{height: '1.2em'}} className='w-full rounded bg-white pl-1' value={upperBound} onChange={e => setUpperBound(e.target.value)}></input></div>
                </div>
                <button style={{ position: 'absolute', right: 0 }} className='pl-1 pr-1 mr-1' onClick={applyFilter}>
                    <div style={{ width: '1em', background: 'transparent' }}><FontAwesomeIcon icon='check-circle' title='Apply'></FontAwesomeIcon></div>
                </button>
            </div>
        }
    }

    return null;
}

export default RangeSelect;


// helpers for different units
function units() {
    return [
        ['%', 1e-2],
        ['%RH', 1],
        ['Hz', 1],
        ['kHz', 1e3],
        ['KHz', 1e3],
        ['MHz', 1e6],
        ['GHz', 1e9],
        ['pa', 1],
        ['Kpa', 1e3],
        ['kpa', 1e3],
        ['Mpa', 1e6],
        ['K', 1],     // this is probably Kelvin, in which case the scale should be 1
        ['N', 1],
        ['V', 1],
        ['mV', 1e-3],
        ['uV', 1e-6],
        ['V/V', 1],
        ['\u2103', 1],
        ['\u00b0', 1],
        ['nm', 1e-9],
        ['cm', 1e-2],
        ['m', 1],
        ['dB', 1],
        ['dBm', 1],
        ['k\u03a9', 1e3],
        ['mcd', 1e-3],
        ['nC', 1e-9],
        ['mm', 1e-3],
        ['ns', 1e-9],
        ['pF', 1e-12],
        ['pa', 1],
        ['ppm', 1e-6],
        ['us', 1e-6],
        ['W', 1],
        ['mW', 1e-3],
        ['mW/sr', 1e-3],
        ['lm', 1],
    ];
}

function anyUnitRegexString() {
    return units().map(kv => kv[0].replace(/\//g, '\\/')).join('|');
}

// attempts to use the unit scale to convert the number 
function rangeFromStr(str) {
    try {
        const match = rangePattern.exec(str);
        if (match) {
            const low = +match[1] * units().filter(u => u[0] === match[2])[0][1];
            const high = +match[4] * units().filter(u => u[0] === match[5])[0][1];
            return { low, high };
        }
    } catch (x) {
        console.error(x);
    }

    return null;
}

function getRangePattern() {
    const pattern = `([-+]?[0-9.]+)(${anyUnitRegexString()})(@[^~]+)?~([-+]?[0-9.]+)(${anyUnitRegexString()})(@[^~]+)?.*`;
    console.log(pattern);
    return new RegExp(pattern);
}

function valueFromString(str) {
    if (!isNaN(str) && str.length > 0) {
        return +str;
    } else {
        const pattern = new RegExp(`([-+]?[0-9.]+)(${anyUnitRegexString()})`);
        const match = pattern.exec(str);
        return match ? +match[1] * units().filter(u => u[0] === match[2])[0][1] : null;
    }
}