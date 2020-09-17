import React from 'react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import produce from 'immer';
import { Waypoint } from 'react-waypoint';


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
            sortDirection: "asc",
            visibleItems: 100
        };
    }

    componentDidUpdate(prevProps) {
        if (prevProps.data !== this.props.data) {
            this.setState({visibleItems: 100});
        }
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

    getPropAsString = propName => {
        if (this.props[propName])
            return this.props.[propName];
        return "";
    }

    rowClassName = () => { return this.getPropAsString("rowClassName"); }

    evenRowClassName = () => { return this.getPropAsString("evenRowClassName"); }

    oddRowClassName = () => { return this.getPropAsString("oddRowClassName"); }

    showMore = () => {
        this.setState(produce(this.state, draft => {
            if (this.state.visibleItems < this.props.data.length)
                draft.visibleItems += 100;
        }));
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
        sortedData = sortedData.slice(0, this.state.visibleItems);
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
                    sortedData.map((row, index) => {
                        let className = this.rowClassName();
                        if ( index % 2 === 0 )
                            className += " " + this.evenRowClassName();
                        else
                            className += " " + this.oddRowClassName();
                        return <ExpandableTableRow className={className}
                                                  key={this.props.keyFun(row)}
                                                  expandableContent={this.props.expandableContent(row)}>
                                {
                                    this.props.header.map(cell => {
                                        return <td key={cell.name} className={cell.className}>
                                            { cell.displayGetter(row) }
                                        </td>
                                    })
                                }
                            </ExpandableTableRow>
                    })
                }</tbody>
            </table>
            {
                this.state.visibleItems < this.props.data.length
                ? <p className="w-full text-center m-4">Loading more components...</p>
                : <></>
            }
            <Waypoint key="tableEnd" onEnter={this.showMore}/>
        </>
    }
}

class ExpandableTableRow extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            expanded: false
        }
    }

    handleClick = (e) => {
        e.preventDefault();
        this.setState(produce(this.state, draft => {
            draft.expanded = !draft.expanded;
        }));
    }

    render() {
        let expandableContent = <></>
        let className = this.props.className ? this.props.className : "";
        if (this.state.expanded && this.props.expandableContent) {
            expandableContent = <tr>
                    <td colSpan={this.props.children.length}>
                        {this.props.expandableContent}
                    </td>
                </tr>;
        }
        if (this.props.expandableContent)
            className += " cursor-pointer";
        return <>
            <tr className={className} onClick={this.handleClick}>
                {this.props.children}
            </tr>
            {expandableContent}
        </>
    }
}