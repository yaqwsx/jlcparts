import React, { useState, useEffect, useRef } from 'react';
import sliders from './sliders.svg';    // nicer slider icon than fa-sliders-h
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';

function RangeSelect({ icon, title, options, onRangeChange }) {
    const [isOpen, setIsOpen] = useState(false);
    const [visible, setVisible] = useState(false);

    const [lowerBound, setLowerBound] = useState('');
    const [upperBound, setUpperBound] = useState('');

    const rangePattern = useRef(/([-+]?[0-9.]+).~([-+]?[0-9.]+)..*/);

    const applyFilter = () => {
        setIsOpen(false);

        setTimeout(() => {
            const lbValid = !isNaN(lowerBound) && lowerBound.trim().length;
            const ubValid = !isNaN(upperBound) && upperBound.trim().length

            if (lbValid || ubValid) {
                let ranges = options.map(o => rangePattern.current.exec(o.value)).map(r => r && r.length === 3 ? r : null);
                if (lbValid) {
                    ranges = ranges.map(r => r && +r[1] <= +lowerBound ? r : null);
                }
                if (ubValid) {
                    ranges = ranges.map(r => r && +r[2] >= +upperBound ? r : null);
                }

                onRangeChange && onRangeChange(options.filter((o, i) => ranges[i] != null));
            } else {
                onRangeChange && onRangeChange(options);    // default to every selected
            }
        }, 0);
    };

    // check if values are ranges
    useEffect(() => {
        const ranges = options.filter(o => rangePattern.current.test(o.value));
        const inRange = ranges.length >= options.length / 2;
        setVisible(inRange);
    }, [options, rangePattern])

    if (visible) {
        if (!isOpen) {
            return <div style={{ position: 'absolute', right: 0, bottom: 0 }} title={title} className='mr-1'>
                <button onClick={() => setIsOpen(true)} >
                    {icon || <img src={sliders} style={{ width: '1.5em' }} alt='' />}
                </button>
            </div>;
        }
        else {
            return <div style={{position: 'absolute', inset: 0, width: '100%'}} className='bg-blue-500'>
                <div className='flex' style={{flexFlow: 'row'}}>
                    <div style={{width: '100%'}}>Low bound max.</div>
                    <div className='mr-1'><input type='number' className='w-full rounded bg-white pl-1' style={{width: '3em'}} value={lowerBound} onChange={e => setLowerBound(e.target.value)}></input></div>
                </div>
                <div className='flex mt-1' style={{flexFlow: 'row'}}>
                    <div style={{width: '100%'}}>High bound min.</div>
                    <div className='mr-1'><input type='number' className='w-full rounded bg-white pl-1' style={{width: '3em'}} value={upperBound} onChange={e => setUpperBound(e.target.value)}></input></div>
                </div>
                <button style={{position: 'absolute', right: 0}} className='pl-1 pr-1 mr-1' onClick={applyFilter}>
                    <div style={{width: '1em', background: 'transparent'}}><FontAwesomeIcon icon='check-circle' title='Apply'></FontAwesomeIcon></div>
                </button>
            </div>
        }
    }

    return null;
}

export default RangeSelect;
