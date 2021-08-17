import React from 'react';
import { fetchJson, db } from './db'
import { Spinbox, InlineSpinbox, ZoomableLazyImage,
         formatAttribute, findCategoryById } from './componentTable'
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
        db.components.get({"lcsc": this.props.lcsc}).then( component => {
            this.setState({"info": component});
        });
    }

    renderImage() {
        var imgSrc = "./brokenimage.svg";
        var zoomImgSrc = "./brokenimage.svg";
        let x = this.state.info;
        if (x.images && x.images.length > 0) {
            imgSrc = zoomImgSrc = x.images[0];
        }
        return <ZoomableLazyImage
            height={90}
            width={90}
            src={imgSrc}
            zoomWidth={350}
            zoomHeight={350}
            zoomSrc={zoomImgSrc}/>
    }

    renderLoaded() {
        let x = this.state.info;
        let price = getQuantityPrice(1, x.price)
        let unitPrice = Math.round((price + Number.EPSILON) * 1000) / 1000;
        let category = findCategoryById(this.props.categories, x.category);
        return <tr>
            <td className="text-left pl-2">
                <a href={x.url}
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
        if ("info" in this.state && this.state["info"] !== undefined)
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
                let log = []
                for (const day in response) {
                    log.push({
                        "day": new Date(day),
                        "components": response[day]
                    });
                }
                log.sort((a, b) => b["day"] - a["day"]);
                this.setState({"table": log})
            });
        db.categories.toArray().then( categories => {
            this.setState({"categories": categories})
        });
    }

    render() {
        if (this.state["table"] === undefined) {
            return <Spinbox/>
        }
        return this.state["table"].map(item => {
            if (item.components.length === 0)
                return <></>
            let day = item.day
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