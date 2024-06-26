import React from 'react';
import { fetchJson, unpackAndProcessLines, unpackLinesAsArray } from './db'
import { Spinbox, InlineSpinbox, ZoomableLazyImage,
         formatAttribute, findCategoryById, getImageUrl,
         restoreLcscUrl } from './componentTable'
import { getQuantityPrice } from './jlc'
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'

export function History(props) {
    return <div className="bg-gray-200 p-2">
        <HistoryTable/>
    </div>
}

class HistoryItem extends React.Component {
    constructor(props) {
        super(props);
        this.state = {};
    }

    componentDidMount() {
        let schema;
        unpackAndProcessLines('components', (component, idx) => {
            component = JSON.parse(component);
            if (idx === 0) {    // first entry is schema
                schema = component;
            } else {
                if (component[schema.lcsc] === this.props.lcsc) {
                    this.setState({info: component});
                    return 'abort'; // done
                }
            }
        });
    }

    renderImage() {
        let x = this.state.info;
        const imgSrc = getImageUrl(x.img, "small") ?? "./brokenimage.svg";
        return <ZoomableLazyImage
            height={90}
            width={90}
            src={imgSrc}
            zoomWidth={350}
            zoomHeight={350}
            zoomSrc={imgSrc}/>
    }

    renderLoaded() {
        let x = this.state.info;
        let price = getQuantityPrice(1, x.price)
        let unitPrice = Math.round((price + Number.EPSILON) * 1000) / 1000;
        let category = findCategoryById(this.props.categories, x.category);
        return <tr>
            <td className="text-left pl-2">
                <a href={restoreLcscUrl(x.url, x.lcsc)}
                    className="underline text-blue-600"
                    onClick={e => e.stopPropagation()}
                    target="_blank"
                    rel="noopener noreferrer">
                        {x.lcsc}
                </a>
            </td>
            <td className="text-left">
                <a
                    href={x.datasheet}
                    onClick={e => e.stopPropagation()}
                    target="_blank"
                    rel="noopener noreferrer">
                        <FontAwesomeIcon icon="file-pdf"/> {x.mfr}
                </a>
            </td>
            <td className="text-center">
                {formatAttribute(x.attributes["Basic/Extended"])[0]}
            </td>
            <td className="text-center">
                {this.renderImage()}
            </td>
            <td className="text-left">
                {x.description}
            </td>
            <td className="text-left">
                {category.category}: {category.subcategory}
            </td>
            <td className="text-left">
                {`${unitPrice}$/unit`}
            </td>
            <td className="text-right pr-2">
                {x.stock}
            </td>
        </tr>
    }

    renderUnknown() {
        return <tr className="text-center">
            <td className="text-left pl-2">
                {this.props.lcsc}
            </td>
            <td className="" colSpan={7}>
                Component is missing in database. Do you use the latest database?
            </td>
        </tr>
    }

    render() {
        if (this.state?.info !== undefined)
            return this.renderLoaded();
        if ("info" in this.state)
            return this.renderUnknown();
        return <tr className="text-center">
            <td className="text-left pl-2">
                {this.props.lcsc}
            </td>
            <td className="" colSpan={7}>
                <InlineSpinbox/>
            </td>
        </tr>
    }
}

function DayTable(props) {
    return <table className="w-full bg-white p-2 mb-4">
        <thead className="bg-white">
            <tr>{
                ["LCSC", "MFR", "Basic/Extended", "Image", "Description",
                 "Category", "Price", "Stock"].map( label => {
                    return <th key={label} className="bg-blue-500 mx-1 p-2 border-r-2 rounded">
                        {label}
                    </th>
                })
            }</tr>
        </thead>
        <tbody>
            {
                props.components.map(
                    lcsc =>
                        <HistoryItem
                        key={lcsc}
                        lcsc={lcsc}
                        categories={props.categories}/>)
            }
        </tbody>
    </table>
}

class HistoryTable extends React.Component {
    constructor(props) {
        super(props);
        this.state = {};
    }

    componentDidMount() {
        fetchJson(process.env.PUBLIC_URL + "/data/changelog.json")
            .then(response => {
                let log = [];
                for (const day in response) {
                    log.push({
                        day: new Date(day),
                        components: response[day]
                    });
                }
                log.sort((a, b) => b.day - a.day);
                this.setState({table: log});
            });

        unpackLinesAsArray('subcategories').then(cats => {
            this.setState({categories: cats.filter((c,i) => i > 0).map(s => JSON.parse(s))});
        });
    }

    render() {
        if (this.state.table === undefined) {
            return <Spinbox/>
        }
        return this.state.table.map(item => {
            if (item.components.length === 0)
                return null;
            let day = item.day;
            return <div key={item.day}>
                <h2 className="w-full text-lg font-bold mt-6">
                    Newly added components on {day.getDate()}. {day.getMonth() + 1}. {day.getFullYear()}:
                </h2>
                <DayTable
                    components={item.components}
                    categories={this.state.categories}
                    />
            </div>
        });
    }
}