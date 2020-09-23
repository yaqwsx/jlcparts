import { db } from "./db";
import React from "react";
import { produce, enableMapSet } from "immer";
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { LazyLoadImage } from 'react-lazy-load-image-component';
import { CopyToClipboard } from 'react-copy-to-clipboard';
import { SortableTable } from "./sortableTable"

enableMapSet();

function universalComparator(a, b) {
    if (typeof(a) === "number" && typeof(b) === "number")
        return a - b;
    if (typeof(a) === "string" && typeof(b) === "string")
        return a.localeCompare(b);
    return a.toString().localeCompare(b.toString());
}

function parseImageSize(imageSizeStr) {
    let sizes = imageSizeStr.split("x");
    return sizes.map(x => parseInt(x));
}

function sortImagesSrcBySize(images) {
    let imgCollection = [];
    for (var sizeStr in images) {
        if (sizeStr === "sort")
            continue;
        let imageDimension = parseImageSize(sizeStr);
        let size = imageDimension[0] * imageDimension[1];
        imgCollection.push([size, images[sizeStr]])
    }
    imgCollection.sort((a, b) => {
        return b - a;
    });
    return imgCollection;
}

function getQuantityPrice(quantity, pricelist) {
    for (let pricepoint of pricelist) {
        if (quantity >= pricepoint.qFrom && (quantity <= pricepoint.qTo || !pricepoint.qTo))
            return pricepoint.price;
    }
    if (pricelist[0])
        return pricelist[0].price;
    return undefined;
}

function fullTextComponentsFilter(component, words) {
    let text = componentText(component);
    for (let word of words) {
        if (!text.includes(word))
            return false;
    }
    return true;
}

function componentText(component) {
    return(
        component.lcsc + " " +
        component.mfr + " " +
        component.description
    ).toLocaleLowerCase();
}

function Spinbox() {
    return <div className="w-full text-center">
        <svg className="animate-spin -ml-1 m-8 h-5 w-5 text-black mx-auto inline-block"
             xmlns="http://www.w3.org/2000/svg"
             fill="none" viewBox="0 0 24 24"
             style={{"maxWidth": "100px", "maxHeight": "100px", "width": "100%", "height": "100%"}}>
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
    </div>
}

class ZoomableLazyImage extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            hover: false
        }
    }

    assignRef = (element) => {
        this.container = element;
    }

    handleMouseEnter = () => {
        this.setState({"hover": true});
    }

    handleMouseLeave= () => {
        this.setState({"hover": false});
    }

    render() {
        return (
            <div
                onMouseEnter={this.handleMouseEnter}
                onMouseLeave={this.handleMouseLeave}>
                    <LazyLoadImage
                        height={this.props.width}
                        width={this.props.height}
                        src={this.props.src}/>
                {
                    this.state.hover
                        ? <div className="z-40 absolute bg-white border-solid border-gray-600 border-2">
                            <LazyLoadImage
                                height={this.props.zoomWidth}
                                width={this.props.zoomHeight}
                                src={this.props.zoomSrc}/>
                          </div>
                        : <></>
                }
            </div>)
    }
}

export class ComponentOverview extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            "components": [],
            "categories": [],
            "activeProperties": {},
            "requiredProperties": new Set(),
            "expectedComponentsVersion": 0,
            "componentsVersion": 0,
            "tableIncludedProperties": new Set(),
            "quantity": 1
        };
    }

    componentDidMount() {
        db.categories.toArray().then( categories => {
            this.setState({
                "categories": this.prepareCategories(categories),
                "rawCategories": categories
            });
        })
    }

    prepareCategories(sourceCategories) {
        let categories = {};
        for (const category of sourceCategories) {
            if (categories[category.category] === undefined) {
                categories[category.category] = [];
            }
            categories[category.category].push({
                "value": category["subcategory"],
                "key": category["id"]
            });
        }

        let sortedCategories = [];
        for (const key in categories) {
            let subCats = categories[key];
            subCats.sort((a, b) => {
                return a["value"].localeCompare(b["value"]);
            });
            sortedCategories.push({
                "category": key,
                "subcategories": subCats
            });
        }
        sortedCategories.sort((a, b) => {
            return a.category.localeCompare(b.category);
        })
        return sortedCategories;
    }

    collectProperties(components) {
        let properties = {};
        for (const component of components) {
            if (!("attributes" in component))
                continue;
            let attributes = component["attributes"];
            for (const property in attributes) {
                if (!(property in properties)) {
                    properties[property] = new Set();
                }
                properties[property].add(attributes[property]);
            }
        }

        let sortedProperties = [];
        for (const property in properties) {
            if (properties[property].size <= 1)
                continue;
            let values = [...properties[property]].map(x => {
                return {"key": x, "value": x};
            });
            values.sort((a, b) => {
                return a.key.localeCompare(b.key);
            });

            sortedProperties.push({
                "property": property,
                "values": values
            });
        }
        sortedProperties.sort((a, b) => {
            return a.property.localeCompare(b.property);
        });
        return sortedProperties;
    }

    handleStartComponentsChange = () => {
        let newVersion = this.state.componentsVersion + 1;
        this.setState(produce(this.state, draft => {
            draft["expectedComponentsVersion"] = newVersion;
        }));
        return newVersion;
    }

    handleComponentsChange = (version, components) => {
        if (version !== this.state.expectedComponentsVersion)
            return;
        this.setState(produce(this.state, draft => {
            draft["componentsVersion"] = version;
            draft["components"] = components;
            // Update properties filters
            var t0 = performance.now();
            let properties = {};
            for (const propertyDic of this.collectProperties(components)) {
                properties[propertyDic["property"]] = propertyDic["values"].map(x => x["key"]);
            }
            for (const property of Object.keys(draft.activeProperties)) {
                if (!(property in properties)) {
                    delete draft["activeProperties"][property];
                }
            }
            for (const property in properties) {
                draft["activeProperties"][property] = properties[property];
            }
            var t1 = performance.now();
            console.log("Active categories took ", t1 - t0, "ms" );
        }));
    }

    handleActivePropertiesChange = (property, values) => {
        this.setState(produce(this.state, draft => {
            draft["activeProperties"][property] = values;
        }));
    }

    handleIncludeInTable = (property, value) => {
        this.setState(produce(this.state, draft => {
            if (value)
                draft["tableIncludedProperties"].add(property);
            else
                draft["tableIncludedProperties"].delete(property);
        }));
    }

    handlePropertyRequired = (property, value) => {
        this.setState(produce(this.state, draft => {
            if (value)
                draft["requiredProperties"].add(property);
            else
                draft["requiredProperties"].delete(property);
        }));
    }

    filterComponents(components, activeProperties, requiredProperties) {
        return components.filter(component => {
            for (const property in activeProperties) {
                let attributes = component["attributes"];
                if (!(property in attributes)) {
                    if (requiredProperties.has(property))
                        return false;
                    else
                        continue
                }
                if (!(activeProperties[property].includes(attributes[property])))
                    return false;
            }
            return true;
        });
    }

    handleQuantityChange = q => {
        this.setState({quantity: q});
    }

    render() {
        let filterComponents = <>
            <CategoryFilter
                categories={this.state.categories}
                onChange={this.handleComponentsChange}
                onAnnounceChange={this.handleStartComponentsChange}/>
            <PropertySelect
                properties={this.collectProperties(this.state.components)}
                values={this.state.activeProperties}
                onChange={this.handleActivePropertiesChange}
                onTableInclude={this.handleIncludeInTable}
                tableIncluded={Array.from(this.state.tableIncludedProperties)}
                requiredProperties={Array.from(this.state.requiredProperties)}
                onPropertyRequired={this.handlePropertyRequired}
                />
            <QuantitySelect
                onChange={this.handleQuantityChange}
                value={this.state.quantity}/>
            </>;

        if (this.state.expectedComponentsVersion !== this.state.componentsVersion) {
            return <>
                    {filterComponents}
                    <Spinbox/>
                </>;
        }

        let header = [
            {
                name: "MFR (click for datasheet)",
                sortable: true,
                displayGetter: x => <a
                    href={x.datasheet}
                    onClick={e => e.stopPropagation()}
                    target="_blank"
                    rel="noopener noreferrer">
                        <FontAwesomeIcon icon="file-pdf"/> {x.mfr}
                    </a>,
                comparator: (a, b) => a.mfr.localeCompare(b.mfr),
                className: "px-1 whitespace-no-wrap"
            },
            {
                name: "LCSC",
                sortable: true,
                className: "px-1 whitespace-no-wrap text-center",
                displayGetter: x => {
                    return <>
                        <a href={x.url}
                            className="underline text-blue-600"
                            onClick={e => e.stopPropagation()}
                            target="_blank"
                            rel="noopener noreferrer">
                                {x.lcsc}
                        </a>
                        <CopyToClipboard text={x.lcsc}>
                            <button className="py-2 px-4" onClick={e => e.stopPropagation()}>
                                <FontAwesomeIcon icon="clipboard"/>
                            </button>
                        </CopyToClipboard>
                    </>
                },
                comparator: (a, b) => a.lcsc.localeCompare(b.lcsc)
            },
            {
                name: "Basic/Extended",
                sortable: true,
                displayGetter: x => x.attributes["Basic/Extended"][0],
                comparator: (a, b) => a.attributes["Basic/Extended"].localeCompare(b.attributes["Basic/Extended"]),
                className: "text-center"
            },
            {
                name: "Image",
                sortable: false,
                displayGetter: x => {
                    var imgSrc = "./brokenimage.svg";
                    var zoomImgSrc = "./brokenimage.svg";
                    if (x.images && Object.keys(x.images).length > 0) {
                        let sources = sortImagesSrcBySize(x.images);
                        imgSrc = sources[0][1];
                        zoomImgSrc = sources[2][1];
                    }
                    return <ZoomableLazyImage
                        height={90}
                        width={90}
                        src={imgSrc}
                        zoomWidth={350}
                        zoomHeight={350}
                        zoomSrc={zoomImgSrc}/>
                }
            },
            {
                name: "Description",
                sortable: true,
                displayGetter: x => x.description,
                comparator: (a, b) => a.description.localeCompare(b.description)
            },
            {
                name: "Manufacturer",
                sortable: true,
                displayGetter: x => x.manufacturer,
                comparator: (a, b) => a.manufacturer.localeCompare(b.manufacturer)
            },
            {
                name: "Stock",
                sortable: true,
                displayGetter: x => x.stock,
                comparator: (a, b) => a.stock - b.stock
            },
            {
                name: "Price",
                sortable: true,
                displayGetter: x => {
                    let price = getQuantityPrice(this.state.quantity, x.price)
                    let unitPrice = Math.round((price + Number.EPSILON) * 1000) / 1000;
                    let sumPrice = Math.round((price * this.state.quantity + Number.EPSILON) * 1000) / 1000;
                    return <>
                        {`${unitPrice}$/unit`}
                        <br/>
                        {`${sumPrice}$/${this.state.quantity} units`}
                    </>
                },
                comparator: (a, b) => {
                    let aPrice = getQuantityPrice(this.state.quantity, a.price);
                    let bPrice = getQuantityPrice(this.state.quantity, b.price);
                    return aPrice - bPrice
                }
            },
        ];
        for (let attribute of this.state.tableIncludedProperties) {
            let getter = x => {
                if (attribute in x.attributes)
                    return x.attributes[attribute];
                return "";
            }

            header.push( {
                name: attribute,
                sortable: true,
                displayGetter: getter,
                comparator: (a, b) => universalComparator(getter(a), getter(b))
            });
        }

        var t0 = performance.now()
        let filteredComponents = this.filterComponents(this.state.components,
            this.state.activeProperties, this.state.requiredProperties);
        var t1 = performance.now()
        console.log("Filtering took ", t1 - t0, " ms");

        return <>
            {filterComponents}
            {filteredComponents.length
                ?  <div className="pt-4">
                        <div className="w-full flex py-2">
                            <p className="flex-none p-2">Components matching query: {filteredComponents.length}</p>
                            <CopyToClipboard text={filteredComponents.map(c => `wget ${c.datasheet}`).join("\n")}>
                                <button className="flex-none ml-auto block flex-none bg-blue-500 hover:bg-blue-700 text-black py-1 px-2 rounded" onClick={e => e.stopPropagation()}>
                                    wget all datasheets <FontAwesomeIcon icon="clipboard"/>
                                </button>
                            </CopyToClipboard>
                        </div>
                        <SortableTable
                            className="w-full"
                            headerClassName="bg-blue-500"
                            header={header}
                            data={filteredComponents}
                            evenRowClassName="bg-gray-100"
                            oddRowClassName="bg-gray-300"
                            keyFun={item => item.lcsc}
                            expandableContent={c =>
                                <ExpandedComponent
                                    component={c}
                                    categories={this.state.rawCategories}/>}/>
                    </div>
                :   <div className="p-8 text-center text-lg">
                        No components match the selected criteria.
                    </div>
            }

        </>
    }
}

function findCategoryById(categories, id) {
    for (let category of categories) {
        if (category.id === id )
            return category;
    }
    return {
        category: "unknown",
        subcategory: "unknown"
    }
}

function ExpandedComponent(props) {
    let comp = props.component;
    var imgSrc = "./brokenimage.svg";
    if (comp.images && Object.keys(comp.images).length > 0) {
        let sources = sortImagesSrcBySize(comp.images);
        imgSrc = sources[sources.length - 1][1];
    }
    let category = findCategoryById(props.categories, comp.category)
    return <div className="w-full flex flex-wrap pl-6">
        <div className="w-full md:w-1/5 p-3">
            <img
                src={imgSrc}
                alt={`Component ${comp.lcsc}`}
                className="w-full mx-auto"
                style={{
                    maxWidth: "250px"
                }}/>
        </div>
        <div className="w-full md:w-2/5 p-3">
            <table className="w-full">
                <thead className="border-b-2 font-bold">
                    <tr>
                        <td>Property</td>
                        <td>Value</td>
                    </tr>
                </thead>
                <tbody>
                    <tr key="category">
                        <td>Category</td>
                        <td>{category.category}: {category.subcategory}</td>
                    </tr>
                    {
                        Object.keys(comp.attributes).reduce( (result, pName) => {
                                result.push(
                                    <tr key={pName}>
                                        <td>{pName}</td>
                                        <td>{comp.attributes[pName]}</td>
                                    </tr>);
                                return result;
                        }, [])
                    }
                </tbody>
            </table>
        </div>
        <div className="w-full md:w-2/5 p-3">
        <table className="w-full">
                <thead className="border-b-2 font-bold">
                    <tr>
                        <td>Quantity</td>
                        <td>Unit Price</td>
                    </tr>
                </thead>
                <tbody>{
                   comp.price.map( (pricePoint, idx) => {
                        return <tr key={idx}>
                                <td>{
                                    pricePoint.qTo
                                    ?   `${pricePoint.qFrom}-${pricePoint.qTo}`
                                    :   `${pricePoint.qFrom}+`
                                }</td>
                                <td>{pricePoint.price} USD</td>
                               </tr>;
                   })
                }</tbody>
            </table>
        </div>
    </div>
}

// Takes a dictionary of categories and subcategories and lets the user to
// choose several of them. Returns a list of components fulfilling the
// selection via onChange.
class CategoryFilter extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            categories: {},
            allCategories: false,
            searchString: ""
        }
    }

    collectActiveCategories = () => {
        let categories = [];
        for (const key in this.state.categories) {
            categories = categories.concat(this.state.categories[key]);
        }
        return categories;
    }

    notifyParent = () => {
        var t0 = performance.now();
        let version = this.props.onAnnounceChange();
        this.components().then(components => {
            var t1 = performance.now();
            console.log("Select took", t1 - t0, "ms");
            this.props.onChange(version, components);
        });
    }

    // Return query containing components based on current categories and
    // full-text search
    async components() {
        let query;
        if (this.state.allCategories)
            query = db.components;
        else
            query = db.components.where("category").anyOf(this.collectActiveCategories());
        let components = await query.toArray();
        if (this.state.searchString.length === 0)
            return components;

        let words = this.state.searchString.split(/\s+/)
            .filter(x => x.length > 0)
            .map(x => x.toLocaleLowerCase());
        if (words.length === 0)
            return components;
        console.log("Starting search...");
        let t0 = performance.now()
        let filtered = components.filter( component => fullTextComponentsFilter(component, words));
        let t1 = performance.now();
        console.log("Search took", t1 - t0, "ms");
        return filtered;
    }

    handleCategoryChange = (category, value) => {
        console.log("Category change");
        this.setState(produce(this.state, draft => {
            draft.categories[category] = value.map(n => { return parseInt(n)});
            draft.allCategories = false;
        }), this.notifyParent);
    }

    selectAll = (state) => {
        for (let category of this.props.categories) {
            state.categories[category.category] = category.subcategories.map( x => x.key );
        }
        state.allCategories = true;
    }

    handleSelectAll = () => {
        this.setState(produce(this.state, this.selectAll), this.notifyParent);
    }

    handleSelectNone = () => {
        this.setState(produce(this.state, draft => {
            for (let key in draft.categories) {
                draft.categories[key] = [];
            }
            draft.allCategories = false;
        }), this.notifyParent);
    }

    handleFulltextChange = (e) => {
        this.setState(produce(this.state, draft => {
            draft.searchString = e.target.value;
            if (!draft.allCategories && this.collectActiveCategories().length === 0)
                this.selectAll(draft);
        }), () => {
            clearTimeout(this.searchTimeout);
            this.searchTimeout = setTimeout(this.notifyParent(), 3000);
        });
    }

    render() {
        return <div className="w-full p-2 border-b-2 border-gray-600 bg-gray-200">
            <div className="flex">
                <h3 className="block flex-1 text-lg mx-2 font-bold">Select category</h3>
                <button className="block flex-none mx-2 bg-blue-500 hover:bg-blue-700 text-black py-1 px-2 rounded" onClick={this.handleSelectAll}>
                    Select all categories
                </button>

                <button className="block flex-none mx-2 bg-blue-500 hover:bg-blue-700 text-black py-1 px-2 rounded" onClick={this.handleSelectNone}>
                    Select none
                </button>
            </div>
            <div className="w-full flex p-2">
                <label className="flex-none block py-1 mr-2">
                    Contains text:
                </label>
                <input type="text"
                    className="block flex-1 bg-white appearance-none border-2 border-gray-500 rounded w-full
                                py-1 px-4 text-gray-700 leading-tight focus:outline-none focus:bg-white
                                focus:border-blue-500"
                    onChange={this.handleFulltextChange}/>
            </div>
            <div className="flex flex-wrap items-stretch">
                {this.props.categories.map(item => {
                    return <SelectBox
                        className="bg-blue-500"
                        key={item["category"]}
                        name={item["category"]}
                        options={item["subcategories"]}
                        value={this.state.categories[item["category"]]}
                        onChange={value => {
                            this.handleCategoryChange(item["category"], value); } }/>;
                })}
            </div>
        </div>
    }
}

class SelectBox extends React.Component {
    handleAllClick = (e) => {
        e.preventDefault();
        let values = this.props.options.map(option => {
            return option["key"]
        });
        this.props.onChange(values);
    }

    handleNoneClick = (e) => {
        e.preventDefault();
        this.props.onChange([]);
    }

    handleSelectChange = (e) => {
        e.preventDefault();
        let value = Array.from(e.target.selectedOptions, option => option.value);
        this.props.onChange(value);
    }

    render() {
        return <>
            <div className={`rounded flex flex-col flex-1 p-1 m-1 ${this.props.className}`}  style={{"minWidth": "200px", "maxWidth": "400px"}}>
                <div className="flex-none flex w-full">
                    <h5 className="block flex-1 font-bold cursor-default rounded px-1 truncate hover:whitespace-normal">{this.props.name}</h5>
                    <div className="flex-none">
                        <button onClick={this.handleAllClick} className="mx-2">All</button>
                        <button onClick={this.handleNoneClick} className="mx-2">None</button>
                    </div>
                </div>
                <select multiple="multiple" className="flex-1 w-full my-2 p-1"
                        value={this.props.value} onChange={this.handleSelectChange}>
                    {this.props.options.map(option => {
                        return <option value={option["key"]} key={option["key"]}>
                                    {option["value"]}
                            </option>;
                    })}
                </select>
                <div className="flex-none">
                    {this.props.children}
                </div>
            </div>
        </>;
    }
}

class PropertySelect extends React.Component {
    render() {
        return <div className="w-full p-2 border-b-2 border-gray-600 bg-gray-200">
            <h3 className="block w-full text-lg mx-2 font-bold">Property filter</h3>
            <div className="flex flex-wrap items-stretch">
                { this.props.properties.length === 0
                ? <p className="mx-2">
                    There are no properties to select from. Select category or adjust the full-text search to include some components.
                 </p>
                : this.props.properties.map(item => {
                    return <SelectBox
                        className="bg-blue-500"
                        key={item["property"]}
                        name={item["property"]}
                        options={item["values"]}
                        value={this.props.values[item["property"]]}
                        onChange={value => {
                            this.props.onChange(item["property"], value); } }
                    >
                        <div className="w-full">
                            <input
                                className="mr-2 leading-tight"
                                type="checkbox"
                                checked={this.props.tableIncluded.includes(item["property"])}
                                onChange={e => {
                                    this.props.onTableInclude(item["property"], e.target.checked); } } />
                            Table column
                        </div>
                        <div className="w-full">
                            <input
                                className="mr-2 leading-tight"
                                type="checkbox"
                                checked={this.props.requiredProperties.includes(item["property"])}
                                onChange={e => {
                                    this.props.onPropertyRequired(item["property"], e.target.checked); } } />
                            Required
                        </div>
                    </SelectBox>;
                })}
            </div>
        </div>
    }
}

class QuantitySelect extends React.Component {
    render() {
        return <div className="w-full p-2 border-b-2 border-gray-600 bg-gray-200">
            <div className="flex">
                <div className="flex-none py-2 mr-2">
                    Specify quantity (for price point selection)
                </div>
                <input
                    className="block flex-1 bg-white appearance-none border-2 border-gray-500 rounded w-full
                        py-1 px-4 text-gray-700 leading-tight focus:outline-none focus:bg-white
                        focus:border-blue-500"
                    type="number"
                    min={1}
                    onChange={e => this.props.onChange(e.target.value)}
                    value={this.props.value}
                    />
            </div>
        </div>
    }
}
