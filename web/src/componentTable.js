import { db } from "./db";
import React from "react";
import produce from "immer";
import { LazyLoadImage } from 'react-lazy-load-image-component';
import { SortableTable } from "./sortableTable"

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
            "activeProperties": {}
        };
    }

    componentDidMount() {
        db.categories.toArray().then( categories => {
            this.setState({"categories": this.prepareCategories(categories)});
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

    handleComponentsChange = (components) => {
        this.setState(produce(this.state, draft => {
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
                if (!(property in draft["activeProperties"])) {
                    draft["activeProperties"][property] = properties[property];
                }
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

    filterComponents(components, activeProperties) {
        return components.filter(component => {
            for (const property in activeProperties) {
                let attributes = component["attributes"];
                if (!(property in attributes))
                    continue;
                if (!(activeProperties[property].includes(attributes[property])))
                    return false;
            }
            return true;
        });
    }

    render() {
        let header = [
            {
                name: "MFR",
                sortable: true,
                displayGetter: x => x.mfr,
                comparator: (a, b) => a.mfr.localeCompare(b.mfr)
            },
            {
                name: "LCSC",
                sortable: true,
                displayGetter: x => {
                    return <a href={x.url} className="underline text-blue-600">
                        {x.lcsc}
                    </a>
                },
                comparator: (a, b) => a.lcsc.localeCompare(b.lcsc)
            },
            {
                name: "Image",
                sortable: false,
                displayGetter: x => {
                    var imgSrc = "";
                    var zoomImgSrc = "";
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
                displayGetter: x => x.price[0].price.toString() + " USD",
                comparator: (a, b) => (a.price[0].price - b.price[0].price)
            },
        ];
        var t0 = performance.now()
        let filteredComponents = this.filterComponents(this.state.components, this.state.activeProperties);
        var t1 = performance.now()
        console.log("Filtering took ", t1 - t0, " ms");

        return <>
            <CategoryFilter
                categories={this.state.categories}
                onChange={this.handleComponentsChange}/>
            <PropertySelect
                properties={this.collectProperties(this.state.components)}
                values={this.state.activeProperties}
                onChange={this.handleActivePropertiesChange}/>
            <QuantitySelect/>

            {filteredComponents.length
                ?   <SortableTable
                        className="w-full"
                        header={header}
                        data={filteredComponents}
                        rowClassName="bg-white odd:bg-gray-200"
                        keyFun={item => item.lcsc}/>
                :   <div>No components match the select criteria</div>
            }

        </>
    }
}

// Takes a dictionary of categories and subcategories and lets the user to
// choose several of them. Returns a list of components fulfilling the
// selection via onChange.
class CategoryFilter extends React.Component {
    constructor(props) {
        super(props);
        this.state = {}
    }

    collectActiveCategories = () => {
        let categories = [];
        for (const key in this.state) {
            categories = categories.concat(this.state[key]);
        }
        return categories;
    }

    // Return query containing components based on current categories and
    // full-text search
    componentQuery() {
        return db.components.where("category").anyOf(this.collectActiveCategories());
    }

    handleCategoryChange = (category, value) => {
        var t0 = performance.now();
        this.setState({[category]: value.map(n => { return parseInt(n)})}, () => {
            this.componentQuery().toArray().then(components => {
                var t1 = performance.now();
                console.log("Select took", t1 - t0, "ms");
                this.props.onChange(components);
            })
        });
    }

    render() {
        return <div className="w-full bg-blue-200">
            <h3>Select category</h3>
            <div className="flex flex-wrap items-stretch">
                {this.props.categories.map(item => {
                    return <SelectBox
                        key={item["category"]}
                        name={item["category"]}
                        options={item["subcategories"]}
                        value={this.state[item["category"]]}
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
            <div className="rounded flex flex-col flex-1 p-1 m-1 bg-blue-600"  style={{"minWidth": "200px", "maxWidth": "400px"}}>
                <div className="flex-none flex w-full">
                    <h5 className="block flex-1 font-bold">{this.props.name}</h5>
                    <div className="flex-none">
                        <button onClick={this.handleAllClick} className="mx-2">All</button>
                        <button onClick={this.handleNoneClick} className="mx-2">None</button>
                    </div>
                </div>
                <select multiple="multiple" className="flex-1 w-full my-2"
                        value={this.props.value} onChange={this.handleSelectChange}>
                    {this.props.options.map(option => {
                        return <option value={option["key"]} key={option["key"]}>
                                    {option["value"]}
                            </option>;
                    })}
                </select>
            </div>
        </>;
    }
}

class PropertySelect extends React.Component {
    render() {
        return <div className="w-full bg-purple-200">
            <h3>Filter properties</h3>
            <div className="flex flex-wrap items-stretch">
                {this.props.properties.map(item => {
                    return <SelectBox
                        key={item["property"]}
                        name={item["property"]}
                        options={item["values"]}
                        value={this.props.values[item["property"]]}
                        onChange={value => {
                            this.props.onChange(item["property"], value); } }
                    />;
                })}
            </div>
        </div>
    }
}

class QuantitySelect extends React.Component {
    render() {
        return <div className="w-full bg-yellow-200">
            <h3>Specify quantity (for price point selection)</h3>
        </div>
    }
}

export class ComponentTable extends React.Component {
    render() {
        return this.props.components.length
            ?   <table className="w-full">
                    <tbody>
                        {this.props.components.map(component => {
                            return <tr key={component.lcsc}>
                                <td>{component.lcsc}</td>
                                <td>{component.description}</td>
                            </tr>})}
                    </tbody>
                </table>
            :   <div>No components match the select criteria</div>
    }
}