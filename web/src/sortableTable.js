import React from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import produce from 'immer';

function SortableHeaderField(props) {
    var sortIcons;
    var className = "sticky top-0 bg-white "
    if (props.sortable) {
        className += "cursor-pointer"
        let icon = "sort";
        if (props.sortDirection === "asc")
            icon = "sort-amount-up";
        if (props.sortDirection === "desc")
            icon = "sort-amount-down";
        sortIcons = <FontAwesomeIcon icon={icon}/>
    } else {
        sortIcons = <></>
    }

    return <>
        <th onClick={() => props.onClick()} className={className}>
            {props.header}
            { sortIcons }
        </th>
    </>
}

export class SortableTable extends React.Component {
    constructor(props) {
        super(props)
        this.state = {
            sortBy: null,
            sortDirection: "asc"
        };
    }

    handleHeaderClick = name => {
        if (this.state.sortBy === name) {
            this.setState(produce(this.state, draft => {
                if (draft.sortDirection === "asc")
                    draft.sortDirection = "desc";
                else
                    draft.sortDirection = "asc";
            }));
        }
        else {
            this.setState(produce(this.state, draft => {
                draft.sortBy = name;
                draft.sortDirection = "asc";
            }));
        }
    }

    getComparator = (columnName) => {
        for (var obj of this.props.header) {
            if (obj.name === columnName)
                return obj.comparator;
        }
    }

    render() {
        var t0 = performance.now()
        var sortedData = [...this.props.data];
        if (this.state.sortBy) {
            let pureComparator = this.getComparator(this.state.sortBy);
            let comparator;
            if (this.state.sortDirection === "desc")
                comparator = (a, b) => - pureComparator(a, b);
            else
                comparator = pureComparator;

            sortedData.sort(comparator);
        }
        var t1 = performance.now()
        console.log("Sorting took " + (t1 - t0) + " milliseconds.")
        return <>
            <table className={this.props.className}>
                <thead>
                    <tr>{
                        this.props.header.map( x => {
                            let sortDirection = null;
                            if (this.state.sortBy === x.name)
                                sortDirection = this.state.sortDirection;
                            return <SortableHeaderField
                                        key={x.name}
                                        header={x.name}
                                        sortable={x.sortable}
                                        onClick={() => this.handleHeaderClick(x.name)}
                                        sortDirection={sortDirection}/>;
                        })
                    }</tr>
                </thead>
                <tbody>{
                    sortedData.map(row => {
                        return <tr className={this.props.rowClassName} key={this.props.keyFun(row)}>{
                            this.props.header.map(cell => {
                                return <td key={cell.name}>
                                    { cell.displayGetter(row) }
                                </td>
                            })
                        }</tr>
                    })
                }</tbody>
            </table>
        </>
    }
}