import { db } from "./db";
import React from "react";
import { produce, enableMapSet } from "immer";
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { LazyLoadImage } from 'react-lazy-load-image-component';
import { Link } from 'react-scroll';
import { CopyToClipboard } from 'react-copy-to-clipboard';
import { SortableTable } from "./sortableTable"
import { quantityComparator, quantityFormatter } from "./units";
import { AttritionInfo, getQuantityPrice } from "./jlc"
import { naturalCompare } from '@discoveryjs/natural-compare';

enableMapSet();

function getValue(value) {
    return value?.[0];
}

function getQuantity(value) {
    return value?.[1];
}

// Compare two attributes based on given valueType. If no valueType is
// specified, use primary attribute of x
function attributeComparator(x, y, valueType) {
    if (x === undefined && y === undefined)
        return 0;
    if (x === undefined)
        return 1;
    if (y === undefined)
        return -1;
    valueType ??= x.primary;
    let comparator = quantityComparator(getQuantity(x.values[valueType]));
    return comparator(
        getValue(x.values[valueType]),
        getValue(y.values[valueType])
    );
}

function componentText(component) {
    return(
        component.lcsc + " " +
        component.mfr + " " +
        component.description
    ).toLocaleLowerCase();
}

export function formatAttribute(attribute) {
    let varNames = Object.keys(attribute.values).map(x => "\\${" + x + "}");

    let regex = new RegExp('(' + varNames.join('|') + ')', 'g');
    return attribute.format.replace(regex, match => {
        let name = match.slice(2, -1);
        let value = attribute.values[name];
        return quantityFormatter(value[1])(value[0]);
    });
}

export function getImageUrl(img, size) {
    if (!img) {
        return null;
    }
    const sizeInPx = {
        small: "96x96",
        medium: "224x224",
        big: "900x900"
    }[size];
    return `https://assets.lcsc.com/images/lcsc/${sizeInPx}/${img}`;
}

export function restoreLcscUrl(slug, lcsc) {
    return `https://lcsc.com/product-detail/${slug}_${lcsc}.html`;
}

function valueFootprint(value) {
    return JSON.stringify(value);
}

export function Spinbox() {
    return <div className="w-full text-center">
        <svg className="animate-spin -ml-1 m-8 h-5 w-5 text-black mx-auto inline-block"
             xmlns="http://www.w3.org/2000/svg"
             fill="none" viewBox="0 0 24 24"
             style={{maxWidth: "100px", maxHeight: "100px", width: "100%", height: "100%"}}>
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
    </div>
}

export function InlineSpinbox(props) {
    return <div className={`inline text-center ${props.className}`}>
        <svg className="animate-spin h-5 w-5 text-black mx-auto inline-block"
             xmlns="http://www.w3.org/2000/svg"
             fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
    </div>
}


export class ZoomableLazyImage extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            hover: false
        }
    }

    assignRef = element => {
        this.container = element;
    }

    handleMouseEnter = () => {
        this.setState({hover: true});
    }

    handleMouseLeave= () => {
        this.setState({hover: false});
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
                    this.state.hover && (
                        <div className="z-40 absolute bg-white border-solid border-gray-600 border-2">
                            <LazyLoadImage
                                height={this.props.zoomWidth}
                                width={this.props.zoomHeight}
                                src={this.props.zoomSrc}/>
                        </div>
                    )
                }
            </div>
        )
    }
}

export class ComponentOverview extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            components: [],
            categories: [],
            activeProperties: {},
            stockRequired: false,
            requiredProperties: new Set(),
            expectedComponentsVersion: 0,
            componentsVersion: 0,
            tableIncludedProperties: new Set(),
            quantity: 1,
            favorites: new Set(),
            favoritesOnly: false
        };

        db.settings.get("favorites").then(favorites => {
          this.setState({favorites: new Set(favorites.value)});
        });
    }

    componentDidMount() {
        db.categories.toArray().then( categories => {
            this.setState({
                categories: this.prepareCategories(categories),
                rawCategories: categories
            });
        })
    }

    prepareCategories(sourceCategories) {
        let categories = {};
        for (const category of sourceCategories) {
            categories[category.category] ??= [];
            categories[category.category].push({
                value: category.subcategory,
                key: category.id
            });
        }

        let sortedCategories = [];
        for (const key in categories) {
            let subCats = categories[key];
            subCats.sort((a, b) => a.value.localeCompare(b.value));
            sortedCategories.push({
                category: key,
                subcategories: subCats
            });
        }
        sortedCategories.sort((a, b) => a.category.localeCompare(b.category));
        return sortedCategories;
    }

    collectProperties(components) {
        let properties = {};
        for (const component of components) {
            if (!("attributes" in component))
                continue;
            let attributes = component.attributes;
            for (const property in attributes) {
                properties[property] ??= {};
                let val = attributes[property];
                properties[property][valueFootprint(val)] = val;
            }
        }

        let propertiesList = [];
        for (const property in properties) {
            if (Object.keys(properties[property]).length <= 1)
                continue;
            let values = Object.entries(properties[property]).map(x => ({key: x[0], value: x[1]}));
            propertiesList.push({property, values});
        }
        propertiesList.sort((a, b) => a.property.localeCompare(b.property));
        return propertiesList;
    }

    handleStartComponentsChange = () => {
        let newVersion = this.state.componentsVersion + 1;
        this.setState(produce(this.state, draft => {
            draft.expectedComponentsVersion = newVersion;
        }));
        return newVersion;
    }

    handleComponentsChange = (version, components) => {
        if (version !== this.state.expectedComponentsVersion)
            return;
        if (!components)
            return;
        this.setState(produce(this.state, draft => {
            draft.componentsVersion = version;
            draft.components = components;
            // Update properties filters
            var t0 = performance.now();
            let properties = {};
            for (const propertyDic of this.collectProperties(components)) {
                properties[propertyDic.property] = propertyDic.values.map(x => x.key);
            }
            for (const property of Object.keys(draft.activeProperties)) {
                if (!(property in properties)) {
                    delete draft.activeProperties[property];
                }
            }
            for (const property in properties) {
                draft.activeProperties[property] = properties[property];
            }
            var t1 = performance.now();
            console.log("Active categories took ", t1 - t0, "ms" );
        }));
    }

    handleActivePropertiesChange = (property, values) => {
        this.setState(produce(this.state, draft => {
            draft.activeProperties[property] = values;
        }));
    }

    handleIncludeInTable = (property, value) => {
        this.setState(produce(this.state, draft => {
            if (value)
                draft.tableIncludedProperties.add(property);
            else
                draft.tableIncludedProperties.delete(property);
        }));
    }

    handlePropertyRequired = (property, value) => {
        this.setState(produce(this.state, draft => {
            if (value)
                draft.requiredProperties.add(property);
            else
                draft.requiredProperties.delete(property);
        }));
    }

    filterComponents(components, activeProperties, requiredProperties) {
        return components.filter(component => {
            for (const property in activeProperties) {
                if (this.state.stockRequired && component.stock < this.state.quantity)
                    return false;
                if (this.state.favoritesOnly && !this.state.favorites.has(component.lcsc))
                    return false;                
                let attributes = component.attributes;
                if (!(property in attributes)) {
                    if (requiredProperties.has(property))
                        return false;
                    else
                        continue;
                }
                if (!(activeProperties[property].includes(valueFootprint(attributes[property]))))
                    return false;
            }
            return true;
        });
    }

    handleQuantityChange = q => {
        this.setState({quantity: q});
    }

    handleStockRequired = stockRequired => {
        this.setState({stockRequired: stockRequired});
    }

    handleFavoritesOnly = (favoritesOnly) => {
      this.setState({favoritesOnly});
    }

    updateFavorites(lcsc, isFavorite) {
      let copy = new Set(this.state.favorites);
      if (isFavorite) {
        copy.add(lcsc);
      } else {
        copy.delete(lcsc);
      }

      db.settings.put({key: "favorites", value: Array.from(copy)}); // save in database for next time

      this.setState({favorites: copy});
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
                value={this.state.quantity}
                stockRequired={this.state.stockRequired}
                onStockRequired={this.handleStockRequired}
                onFavoritesOnly={this.handleFavoritesOnly}/>
            </>;

        if (this.state.expectedComponentsVersion !== this.state.componentsVersion) {
            return <>
                    {filterComponents}
                    <Spinbox/>
                </>;
        }

        let header = [
            {
                name: "MFR",
                sortable: true,
                displayGetter: x => <>
                  <div className="flex py-2">
                    <div className="pl-1" onClick={e=>{ e.stopPropagation(); this.updateFavorites(x.lcsc, !this.state.favorites.has(x.lcsc))}}>
                      {this.state.favorites.has(x.lcsc)
                        ? <FontAwesomeIcon icon="heart" title="Unfavorite"></FontAwesomeIcon>
                        : <div style={{color: 'gray'}}><FontAwesomeIcon icon="heart" title="Add to favorites" className="text-muted"></FontAwesomeIcon></div>}
                    </div>
                    <CopyToClipboard text={x.mfr}>
                        <button className="px-4" onClick={e => e.stopPropagation()}>
                            <FontAwesomeIcon icon="clipboard"/>
                        </button>
                    </CopyToClipboard>
                    {x.datasheet ? (
                        <a
                            href={x.datasheet}
                            className="underline text-blue-600"
                            onClick={e => e.stopPropagation()}
                            target="_blank"
                            rel="noopener noreferrer">
                                <FontAwesomeIcon icon="file-pdf"/> {x.mfr}
                        </a>
                    ) : (
                        x.mfr
                    )}
                  </div>
                </>,
                comparator: (a, b) => naturalCompare(a.mfr, b.mfr),
                className: "px-1 whitespace-no-wrap"
            },
            {
                name: "LCSC",
                sortable: true,
                className: "px-1 whitespace-no-wrap text-center",
                displayGetter: x => {
                    let discontinued = null;
                    if (x.attributes.Status) {
                        let flag = formatAttribute(x.attributes.Status);
                        if (flag === "Discontinued") {
                            discontinued = <FontAwesomeIcon icon="exclamation-triangle"
                                color="red" className="mx-2"
                                title="Warning, this component has been discontinued"/>;
                        }
                    }
                    return <>
                        {discontinued}
                        <CopyToClipboard text={x.lcsc}>
                            <button className="py-2 px-4 pl-1" onClick={e => e.stopPropagation()}>
                                <FontAwesomeIcon icon="clipboard"/>
                            </button>
                        </CopyToClipboard>
                        <a href={restoreLcscUrl(x.url, x.lcsc)}
                            className="underline text-blue-600"
                            onClick={e => e.stopPropagation()}
                            target="_blank"
                            rel="noopener noreferrer">
                                {x.lcsc}
                        </a>
                    </>
                },
                comparator: (a, b) => naturalCompare(a.lcsc, b.lcsc)
            },
            {
                name: "Basic/Extended",
                sortable: true,
                displayGetter: x => formatAttribute(x.attributes["Basic/Extended"])[0],
                comparator: (a, b) => formatAttribute(a.attributes["Basic/Extended"]).localeCompare(formatAttribute(b.attributes["Basic/Extended"])),
                className: "text-center"
            },
            {
                name: "Image",
                sortable: false,
                displayGetter: x => {
                    const imgSrc = getImageUrl(x.img, "small") ?? "./brokenimage.svg";
                    const zoomImgSrc = getImageUrl(x.img, "big") ?? "./brokenimage.svg";
                    return <ZoomableLazyImage
                        height={90}
                        width={90}
                        src={imgSrc}
                        zoomWidth={450}
                        zoomHeight={450}
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
                displayGetter: x => formatAttribute(x.attributes.Manufacturer),
                comparator: (a, b) => formatAttribute(a.attributes.Manufacturer).localeCompare(formatAttribute(b.attributes.Manufacturer))
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
                    if (price === undefined) {
                        return "Not available";
                    }
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
                    if (aPrice === undefined && bPrice === undefined)
                        return 0;
                    if (aPrice === undefined)
                        return 1;
                    if (bPrice === undefined)
                        return -1;
                    return aPrice - bPrice
                }
            },
        ];
        for (let attribute of this.state.tableIncludedProperties) {
            let getter = x => {
                if (attribute in x.attributes)
                    return formatAttribute(x.attributes[attribute]);
                return "";
            }

            let comparator = (x, y) => {
                let val1 = x.attributes[attribute];
                let val2 = y.attributes[attribute];
                return attributeComparator(val1, val2);
            }

            header.push( {
                name: attribute,
                sortable: true,
                displayGetter: getter,
                comparator: comparator,
                onDelete: () => this.handleIncludeInTable(attribute, false),
                className: "text-center"
            });
        }

        var t0 = performance.now()
        let filteredComponents = this.filterComponents(this.state.components,
            this.state.activeProperties, this.state.requiredProperties);
        var t1 = performance.now()
        console.log("Filtering took ", t1 - t0, " ms");

        return <>
            {filterComponents}
            <div className="w-full flex p-2">
                <Link activeClass="active"
                    className="w-full md:w-1/2 block md:mr-2 bg-gray-500 hover:bg-gray-700 text-black py-1 px-2 rounded text-center"
                    to="property-select" spy={true} smooth={true} duration={100} >
                    ↑ <span className="text-bold text-green-500">■</span> Scroll to properties <span className="text-bold text-green-500">■</span> ↑
                </Link>
                <Link activeClass="active"
                    className="w-full md:w-1/2 block md:ml-2 bg-gray-500 hover:bg-gray-700 text-black py-1 px-2 rounded text-center"
                    to="category-select" spy={true} smooth={true} duration={100} >
                    ↑ <span className="text-bold text-red-500">■</span> Scroll to search bar <span className="text-bold text-red-500">■</span> ↑
                </Link>
            </div>
            {filteredComponents.length
                ?  <div className="pt-4" id="results">
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
                                    categories={this.state.rawCategories}
                                    componentQuantity={this.state.quantity}/>}/>
                    </div>
                :   <div className="p-8 text-center text-lg" id="results">
                        No components match the selected criteria.
                    </div>
            }

        </>
    }
}

export function findCategoryById(categories, id) {
    return categories.find(category => category.id === id) ?? {
        category: "unknown",
        subcategory: "unknown"
    }
}

function ExpandedComponent(props) {
    let comp = props.component;
    const imgSrc = getImageUrl(comp.img, "big") ?? "./brokenimage.svg";
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
                                        <td>{formatAttribute(comp.attributes[pName])}</td>
                                    </tr>);
                                return result;
                        }, [])
                    }
                </tbody>
            </table>
        </div>
        <div className="w-full md:w-2/5 p-3">
            <table className="w-full border-b-2">
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
            <AttritionInfo component={comp} quantity={props.componentQuantity} />
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
            searchString: "",
            abort: () => null
        }
    }

    collectActiveCategories = () => {
        return Object.values(this.state.categories).flat();
    }

    notifyParent = () => {
        var t0 = performance.now();
        console.log("Select start");
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
        this.state.abort();
        let query;
        if (this.state.allCategories) {
            if (this.state.searchString.length < 3) { // prevent high ram usage
                return [];
            }
            query = db.components;
        }
        else
            query = db.components.where("category").anyOf(this.collectActiveCategories());

        if (this.state.searchString.length !== 0) {
            const words = this.state.searchString.split(/\s+/)
                .filter(x => x.length > 0)
                .map(x => x.toLocaleLowerCase());
            if (words.length > 0) {
                query = query.filter(component => {
                    const text = componentText(component);
                    return words.every(word => text.includes(word));
                });
            }
        }

        let aborted = false;
        this.setState({abort: () => aborted = true});
        const components = await query.until(() => aborted).toArray();
        return aborted ? null : components;
    }

    handleCategoryChange = (category, value) => {
        console.log("Category change");
        this.setState(produce(this.state, draft => {
            draft.categories[category] = value.map(n => parseInt(n));
            draft.allCategories = false;
        }), this.notifyParent);
    }

    selectAll = state => {
        for (let category of this.props.categories) {
            state.categories[category.category] = category.subcategories.map( x => x.key );
        }
        state.allCategories = true;
    }

    selectNone = state => {
        for (let key in state.categories) {
            state.categories[key] = [];
        }
        state.allCategories = false;
    }

    handleSelectAll = () => {
        this.setState(produce(this.state, this.selectAll), this.notifyParent);
    }

    handleSelectNone = () => {
        this.setState(produce(this.state, this.selectNone), this.notifyParent);
    }

    handleFulltextChange = e => {
        this.setState(produce(this.state, draft => {
            draft.searchString = e.target.value;
            if (!draft.allCategories && this.collectActiveCategories().length === 0)
                this.selectAll(draft);
        }), () => {
            clearTimeout(this.searchTimeout);
            this.searchTimeout = setTimeout(this.notifyParent, 350);
        });
    }

    handleClear = () => {
        this.setState(produce(this.state, draft => {
            draft.searchString = "";
            if (draft.allCategories) {
                this.selectNone(draft);
            }
        }), () => {
            this.notifyParent();
        });
    }

    render() {
        return <div className="w-full p-2 border-b-2 border-gray-600 bg-gray-200">
            <div className="flex">
                <h3 className="block flex-1 text-lg mx-2 font-bold" id="category-select">
                    <span className="text-bold text-red-500">⛶</span> Select category
                </h3>
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
                    placeholder={this.state.allCategories ? "At least 3 characters" : undefined}
                    value={this.state.searchString}
                    onChange={this.handleFulltextChange}/>
                <button className="flex-none block ml-2 bg-blue-500 hover:bg-blue-700 text-black py-1 px-2 rounded" onClick={this.handleClear}>
                    Clear search
                </button>
            </div>
            <div className="w-full flex p-2">
                <Link activeClass="active"
                    className="w-full md:w-1/2 block md:mr-2 bg-gray-500 hover:bg-gray-700 text-black py-1 px-2 rounded text-center"
                    to="results" spy={true} smooth={true} duration={100} >
                    ↓ <span className="text-bold text-blue-500">■</span> Scroll to results <span className="text-bold text-blue-500">■</span> ↓
                </Link>
                <Link activeClass="active"
                    className="w-full md:w-1/2 block md:ml-2 bg-gray-500 hover:bg-gray-700 text-black py-1 px-2 rounded text-center"
                    to="property-select" spy={true} smooth={true} duration={100} >
                    ↓ <span className="text-bold text-green-500">■</span> Scroll to properties <span className="text-bold text-green-500">■</span> ↓
                </Link>
            </div>
            <div className="flex flex-wrap items-stretch">
                {this.props.categories.map(item => {
                    return <MultiSelectBox
                        className="bg-blue-500"
                        key={item.category}
                        name={item.category}
                        options={item.subcategories}
                        value={this.state.categories[item.category]}
                        onChange={value => {
                            this.handleCategoryChange(item.category, value); } }/>;
                })}
            </div>
            <div className="w-full flex p-2">
                <Link activeClass="active"
                    className="w-full md:w-1/2 block md:mr-2 bg-gray-500 hover:bg-gray-700 text-black py-1 px-2 rounded text-center"
                    to="results" spy={true} smooth={true} duration={100} >
                    ↓ <span className="text-bold text-blue-500">■</span> Scroll to results <span className="text-bold text-blue-500">■</span> ↓
                </Link>
                <Link activeClass="active"
                    className="w-full md:w-1/2 block md:ml-2 bg-gray-500 hover:bg-gray-700 text-black py-1 px-2 rounded text-center"
                    to="category-select" spy={true} smooth={true} duration={100} >
                    ↑ <span className="text-bold text-red-500">■</span> Scroll to search bar <span className="text-bold text-red-500">■</span> ↑
                </Link>
            </div>
        </div>
    }
}

class MultiSelectBox extends React.Component {
    handleAllClick = e => {
        e.preventDefault();
        let values = this.props.options.map(option => option.key);
        this.props.onChange(values);
    }

    handleNoneClick = e => {
        e.preventDefault();
        this.props.onChange([]);
    }

    handleSelectChange = e => {
        e.preventDefault();
        let value = Array.from(e.target.selectedOptions, option => option.value);
        this.props.onChange(value);
    }

    render() {
        let selectStyle = {};
        if (this.props.minHeight)
            selectStyle.minHeight = this.props.minHeight;
        return <>
            <div className={`rounded flex flex-col flex-1 p-1 m-1 ${this.props.className}`}  style={{minWidth: "200px", maxWidth: "400px"}}>
                <div className="flex-none flex w-full">
                    <h5 className="block flex-1 font-bold cursor-default rounded px-1 truncate hover:whitespace-normal">{this.props.name}</h5>
                    <div className="flex-none">
                        <button onClick={this.handleAllClick} className="mx-2">All</button>
                        <button onClick={this.handleNoneClick} className="mx-2">None</button>
                    </div>
                </div>
                <select multiple="multiple" className="flex-1 w-full my-2 p-1"
                        style={selectStyle}
                        value={this.props.value} onChange={this.handleSelectChange}>
                    {this.props.options.map(option => {
                        return <option value={option.key} key={option.key} title={option.value}>
                                    {option.value}
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

class SingleSelectBox extends React.Component {
    render() {
        return <select className={this.props.className} onChange={this.props.onChange}>
            {this.props.options.map(option => {
                return <option value={option.key} key={option.key}>
                            {option.value}
                    </option>;
            })}
        </select>
    }
}

class PropertySelector extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            sortBy: this.collectValueTypes()[0].value
        };
    }

    collectValueTypes() {
        return [...new Set(this.props.item.values.flatMap(x => Object.keys(x.value.values)))].map(x => ({key: x, value: x}));
    }

    valueOptions() {
        let options = [...this.props.item.values];
        options.sort((a, b) => {
            return attributeComparator(a.value, b.value, this.state.sortBy);
        })
        return options.map(x => ({
            key: x.key,
            value: formatAttribute(x.value)
        }));
    }

    handleSortChange = e => {
        this.setState({sortBy: e.target.value});
    }

    render() {
        let options = this.valueOptions();
        if (options.length <= 1)
            return null;
        return <MultiSelectBox
            className={this.props.className}
            minHeight="10em"
            name={this.props.item.property}
            options={this.valueOptions()}
            value={this.props.value}
            onChange={value => {
                this.props.onChange(value); } }
        >
            <div className="w-full flex">
                <div className="flex-none">
                    Sort by:
                </div>
                <div className="flex-1 ml-2">
                    <SingleSelectBox
                        className="w-full rounded bg-white"
                        value={this.state.sortBy}
                        options={this.collectValueTypes()}
                        onChange={this.handleSortChange}/>
                </div>
            </div>
            <div className="w-full">
                <input
                    className="mr-2 leading-tight"
                    type="checkbox"
                    checked={this.props.tableIncluded}
                    onChange={e => {
                        this.props.onTableInclude(e.target.checked); } } />
                Table column
            </div>
            <div className="w-full">
                <input
                    className="mr-2 leading-tight"
                    type="checkbox"
                    checked={this.props.required}
                    onChange={e => {
                        this.props.onPropertyRequired(e.target.checked); } } />
                Required
            </div>
        </MultiSelectBox>;
    }
}

class PropertySelect extends React.Component {
    render() {
        return <div className="w-full p-2 border-b-2 border-gray-600 bg-gray-200">
            <h3 className="block w-full text-lg mx-2 font-bold" id="property-select">
                <span className="text-bold text-green-500">⛶</span> Property filter
            </h3>
            <div className="flex flex-wrap items-stretch">
                { this.props.properties.length === 0
                ? <p className="mx-2">
                    There are no properties to select from. Select category or adjust the full-text search to include some components.
                 </p>
                : this.props.properties.map(item => {
                    return <PropertySelector
                        key={item.property}
                        className="bg-blue-500"
                        item={item}
                        value={this.props.values[item.property]}
                        onChange={value => this.props.onChange(item.property, value)}
                        tableIncluded={this.props.tableIncluded.includes(item.property)}
                        onTableInclude={value => this.props.onTableInclude(item.property, value)}
                        required={this.props.requiredProperties.includes(item.property)}
                        onPropertyRequired={value => this.props.onPropertyRequired(item.property, value) }
                    />;
                })}
            </div>
            <div className="w-full flex p-2">
                <Link activeClass="active"
                    className="w-full md:w-1/2 block md:mr-2 bg-gray-500 hover:bg-gray-700 text-black py-1 px-2 rounded text-center"
                    to="results" spy={true} smooth={true} duration={100} >
                    ↓ <span className="text-bold text-blue-500">■</span> Scroll to results <span className="text-bold text-blue-500">■</span> ↓
                </Link>
                <Link activeClass="active"
                    className="w-full md:w-1/2 block md:ml-2 bg-gray-500 hover:bg-gray-700 text-black py-1 px-2 rounded text-center"
                    to="category-select" spy={true} smooth={true} duration={100} >
                    ↑ <span className="text-bold text-red-500">■</span> Scroll to search bar <span className="text-bold text-red-500">■</span> ↑
                </Link>
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
                <div className="flex-none flex items-center">
                    <input
                        className="px-2 ml-3 transform scale-150"
                        type="checkbox"
                        checked={this.props.stockRequired}
                        onChange={e => {
                            this.props.onStockRequired(e.target.checked)
                        }}/>
                    <span className="ml-1 py-2 pl-2 leading-none">
                        Require on stock <br/>
                        <span className="text-gray-600 text-xs">
                            (Stock data can be 24 hours old)
                        </span>
                    </span>
                </div>
                <div className="flex-none flex items-center">
                    <input
                        className="px-2 ml-3 transform scale-150"
                        type="checkbox"
                        checked={this.props.favoritesOnly}
                        onChange={e => {
                            this.props.onFavoritesOnly(e.target.checked)
                        }}/>
                    <span className="ml-1 py-2 pl-2 leading-none">
                        Favorites only <br/>
                    </span>
                </div>
            </div>
        </div>
    }
}
