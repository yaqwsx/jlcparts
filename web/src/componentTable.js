import { getCategories, queryComponents, subscribeToComponentLibraryChanges } from "./db";
import React, { useEffect, useMemo, useState } from "react";
import { produce, enableMapSet } from "immer";
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome'
import { LazyLoadImage } from 'react-lazy-load-image-component';
import { Link } from 'react-scroll';
import { CopyToClipboard } from 'react-copy-to-clipboard';
import { saveAs } from 'file-saver';
import { SortableTable } from "./sortableTable"
import { quantityComparator, quantityFormatter } from "./units";
import { AttritionInfo, getQuantityPrice } from "./jlc"
import { naturalCompare } from '@discoveryjs/natural-compare';
import {
    BooleanParam,
    DelimitedNumericArrayParam,
    StringParam,
    useQueryParams,
} from 'use-query-params';
import {
    compressToEncodedURIComponent,
    decompressFromEncodedURIComponent,
} from 'lz-string';

enableMapSet();

const CompressedJsonParam = {
    encode: value => {
        if (value === undefined || value === null) {
            return undefined;
        }
        return compressToEncodedURIComponent(JSON.stringify(value));
    },
    decode: value => {
        if (Array.isArray(value)) {
            value = value[0];
        }
        if (!value) {
            return undefined;
        }
        try {
            const decompressed = decompressFromEncodedURIComponent(value);
            return decompressed ? JSON.parse(decompressed) : undefined;
        } catch (error) {
            console.warn("Cannot decode query state from URL", error);
            return undefined;
        }
    }
};

const ComponentQueryParams = {
    q: StringParam,
    cf: StringParam,
    all: BooleanParam,
    none: BooleanParam,
    c: DelimitedNumericArrayParam,
    f: CompressedJsonParam,
};

function getValue(value) {
    return value?.[0];
}

function getQuantity(value) {
    return value?.[1];
}

// Compare two attributes based on given valueType. If no valueType is
// specified, use primary attribute of x
export function attributeComparator(x, y, valueType) {
    if ((!x?.values) && (!y?.values))
        return 0;
    if (!x?.values)
        return 1;
    if (!y?.values)
        return -1;
    valueType ??= x.primary;
    valueType ??= x.default;
    valueType ??= Object.keys(x.values)[0];
    if (!valueType) {
        return 0;
    }
    let comparator = quantityComparator(getQuantity(x.values[valueType]));
    return comparator(
        getValue(x.values[valueType]),
        getValue(y.values[valueType])
    );
}

export function formatAttribute(attribute) {
    if (!attribute?.values || !attribute?.format) {
        return "";
    }

    let varNames = Object.keys(attribute.values).map(x => "\\${" + x + "}");

    if (varNames.length === 0) {
        return "";
    }

    let regex = new RegExp('(' + varNames.join('|') + ')', 'g');
    return attribute.format.replace(regex, match => {
        let name = match.slice(2, -1);
        let value = attribute.values[name];
        if (!value) {
            return "";
        }
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
    if (!slug) {
        return `https://www.lcsc.com/search?q=${encodeURIComponent(lcsc)}`;
    }
    return `https://lcsc.com/product-detail/${slug}_${lcsc}.html`;
}

function valueFootprint(value) {
    return JSON.stringify(value);
}

function sortedNumbers(values = []) {
    return values
        .map(value => Number(value))
        .filter(value => Number.isFinite(value))
        .sort((a, b) => a - b);
}

function sortedStrings(values = []) {
    return [...values]
        .filter(value => typeof value === "string" && value.length > 0)
        .sort((a, b) => a.localeCompare(b));
}

function categoryUrlSignature(query = {}) {
    return JSON.stringify({
        q: query.q || "",
        cf: query.cf || "",
        all: Boolean(query.all),
        none: Boolean(query.none),
        c: sortedNumbers(query.c),
    });
}

function filterUrlSignature(query = {}) {
    return JSON.stringify(query.f ?? {});
}

function compactFilterState(filterState) {
    if (!filterState || typeof filterState !== "object") {
        return undefined;
    }
    const result = {};
    if (filterState.p && typeof filterState.p === "object" && Object.keys(filterState.p).length > 0) {
        result.p = {};
        for (const property of sortedStrings(Object.keys(filterState.p))) {
            const values = filterState.p[property];
            if (Array.isArray(values) && values.length > 0) {
                result.p[property] = sortedStrings(values);
            }
        }
        if (Object.keys(result.p).length === 0) {
            delete result.p;
        }
    }
    if (Array.isArray(filterState.req) && filterState.req.length > 0) {
        result.req = sortedStrings(filterState.req);
    }
    if (Array.isArray(filterState.cols) && filterState.cols.length > 0) {
        result.cols = sortedStrings(filterState.cols);
    }
    if (filterState.qty !== undefined && Number(filterState.qty) !== 1) {
        result.qty = Number(filterState.qty);
    }
    if (filterState.stock) {
        result.stock = true;
    }
    return Object.keys(result).length > 0 ? result : undefined;
}

function displayText(value) {
    if (value === null || value === undefined) {
        return "";
    }
    if (typeof value !== "object") {
        return String(value);
    }
    for (const key of ["value", "label", "name", "category", "subcategory", "title"]) {
        if (key in value) {
            return displayText(value[key]);
        }
    }
    return JSON.stringify(value);
}

function formatCount(value) {
    if (!Number.isFinite(value)) {
        return "";
    }
    return value.toLocaleString();
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
    return <div className={`inline text-center ${props.className ?? ""}`}>
        <svg className="animate-spin h-5 w-5 text-black mx-auto inline-block"
             xmlns="http://www.w3.org/2000/svg"
             fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
    </div>
}

function formatDuration(seconds) {
    if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) {
        return "estimating";
    }
    if (seconds < 1) {
        return "less than 1s";
    }
    if (seconds < 60) {
        return `${Math.ceil(seconds)}s`;
    }
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.ceil(seconds % 60);
    return `${minutes}m ${remainingSeconds}s`;
}

function QueryProgress(props) {
    const progress = props.progress;
    if (!progress) {
        return null;
    }
    const done = progress.done || progress.progress >= 1;
    const percent = Math.max(0, Math.min(100, (progress.progress ?? 0) * 100));
    const fileText = progress.filesTotal
        ? `${progress.filesDone}/${progress.filesTotal} files`
        : "";
    const cacheText = progress.cachedFiles
        ? `, ${progress.cachedFiles} cached`
        : "";
    const etaText = done
        ? "Done"
        : progress.etaSeconds === null
        ? "ETA: estimating"
        : `ETA: ${formatDuration(progress.etaSeconds)}`;

    return <div className="w-full px-2 pb-2">
        <div className="flex flex-wrap text-sm">
            <span className="flex-none mr-3">{progress.phase}</span>
            <span className="flex-none mr-3">{Math.round(percent)}%</span>
            <span className="flex-none mr-3">{fileText}{cacheText}</span>
            <span className="flex-none">{etaText}</span>
        </div>
        <div className="w-full bg-gray-300 mt-1 h-2">
            <div className="bg-blue-500 h-2" style={{width: `${percent}%`}}></div>
        </div>
    </div>;
}


export function ZoomableLazyImage(props) {
    const [hover, setHover] = useState(false);

    return (
        <div
            onMouseEnter={() => setHover(true)}
            onMouseLeave={() => setHover(false)}>
                <LazyLoadImage
                    height={props.width}
                    width={props.height}
                    src={props.src}/>
            {
                hover && (
                    <div className="z-40 absolute bg-white border-solid border-gray-600 border-2">
                        <LazyLoadImage
                            height={props.zoomWidth}
                            width={props.zoomHeight}
                            src={props.zoomSrc}/>
                    </div>
                )
            }
        </div>
    )
}

export function ComponentOverview() {
    const [urlQuery, setUrlQuery] = useQueryParams(ComponentQueryParams);
    return <ComponentOverviewView urlQuery={urlQuery} setUrlQuery={setUrlQuery}/>;
}

class ComponentOverviewView extends React.Component {
    constructor(props) {
        super(props);
        const filterState = compactFilterState(props.urlQuery?.f) ?? {};
        this.state = {
            components: [],
            categories: [],
            properties: [],
            activeProperties: {},
            stockRequired: Boolean(filterState.stock),
            requiredProperties: new Set(filterState.req ?? []),
            expectedComponentsVersion: 0,
            componentsVersion: 0,
            tableIncludedProperties: new Set(filterState.cols ?? []),
            propertyValueCounts: {},
            quantity: filterState.qty ?? 1
        };
        this.lastAppliedFilterSignature = filterUrlSignature(props.urlQuery);
    }

    componentDidMount() {
        this.mounted = true;
        this.unsubscribeFromLibraryChanges = subscribeToComponentLibraryChanges(() => {
            this.loadCategories();
        });
        this.loadCategories();
    }

    componentWillUnmount() {
        this.mounted = false;
        this.unsubscribeFromLibraryChanges?.();
    }

    loadCategories() {
        const loadId = Symbol();
        this.activeCategoryLoad = loadId;
        getCategories().then(categories => {
            if (!this.mounted || this.activeCategoryLoad !== loadId) {
                return;
            }
            const normalizedCategories = categories.map(category => ({
                ...category,
                category: displayText(category.category),
                subcategory: displayText(category.subcategory),
            }));
            this.setState({
                categories: this.prepareCategories(normalizedCategories),
                rawCategories: normalizedCategories
            });
        });
    }

    componentDidUpdate(prevProps) {
        if (filterUrlSignature(prevProps.urlQuery) !== filterUrlSignature(this.props.urlQuery)) {
            this.applyUrlFilterState();
        }
    }

    prepareCategories(sourceCategories) {
        let categories = {};
        for (const category of sourceCategories) {
            const componentCount = Number(category.componentCount) || 0;
            categories[category.category] ??= [];
            categories[category.category].push({
                value: category.subcategory,
                label: `${category.subcategory} (${formatCount(componentCount)})`,
                key: category.id,
                componentCount
            });
        }

        let sortedCategories = [];
        for (const key in categories) {
            let subCats = categories[key];
            subCats.sort((a, b) => a.value.localeCompare(b.value));
            const componentCount = subCats.reduce((total, subcat) => total + subcat.componentCount, 0);
            sortedCategories.push({
                category: key,
                label: `${key} (${formatCount(componentCount)})`,
                componentCount,
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
                let footprint = valueFootprint(val);
                properties[property][footprint] ??= {
                    value: val,
                    count: 0
                };
                properties[property][footprint].count += 1;
            }
        }

        let propertiesList = [];
        for (const property in properties) {
            let values = Object.entries(properties[property]).map(([key, item]) => ({
                key,
                value: item.value,
                count: item.count
            }));
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
            const collectedProperties = this.collectProperties(components);
            draft.properties = collectedProperties;
            let properties = {};
            let propertyValueCounts = {};
            for (const propertyDic of collectedProperties) {
                properties[propertyDic.property] = propertyDic.values.map(x => x.key);
                propertyValueCounts[propertyDic.property] = propertyDic.values.length;
            }
            for (const property of Object.keys(draft.activeProperties)) {
                if (!(property in properties)) {
                    delete draft.activeProperties[property];
                }
            }
            for (const property in properties) {
                draft.activeProperties[property] = properties[property];
            }
            draft.propertyValueCounts = propertyValueCounts;
            this.applyUrlFilterStateToDraft(draft);
            var t1 = performance.now();
            console.log("Active categories took ", t1 - t0, "ms" );
        }));
    }

    handleActivePropertiesChange = (property, values) => {
        this.setState(produce(this.state, draft => {
            draft.activeProperties[property] = values;
        }), () => this.updateUrlFilterState("pushIn"));
    }

    handleIncludeInTable = (property, value) => {
        this.setState(produce(this.state, draft => {
            if (value)
                draft.tableIncludedProperties.add(property);
            else
                draft.tableIncludedProperties.delete(property);
        }), () => this.updateUrlFilterState("pushIn"));
    }

    handlePropertyRequired = (property, value) => {
        this.setState(produce(this.state, draft => {
            if (value)
                draft.requiredProperties.add(property);
            else
                draft.requiredProperties.delete(property);
        }), () => this.updateUrlFilterState("pushIn"));
    }

    filterComponents(components, activeProperties, requiredProperties, propertyValueCounts) {
        const activeValueSets = {};
        for (const property in activeProperties) {
            if (activeProperties[property].length !== propertyValueCounts[property]) {
                activeValueSets[property] = new Set(activeProperties[property]);
            }
        }
        return components.filter(component => {
            if (this.state.stockRequired && component.stock < this.state.quantity)
                return false;
            for (const property in activeProperties) {
                let attributes = component.attributes;
                const required = requiredProperties.has(property);
                const allValuesSelected = activeProperties[property].length === propertyValueCounts[property];
                if (allValuesSelected && !required) {
                    continue;
                }
                if (!(property in attributes)) {
                    if (required)
                        return false;
                    else
                        continue;
                }
                if (allValuesSelected) {
                    continue;
                }
                if (!(activeValueSets[property].has(valueFootprint(attributes[property]))))
                    return false;
            }
            return true;
        });
    }

    handleQuantityChange = q => {
        this.setState({quantity: q}, () => this.updateUrlFilterState("replaceIn"));
    }

    handleStockRequired = stockRequired => {
        this.setState({stockRequired: stockRequired}, () => this.updateUrlFilterState("pushIn"));
    }

    applyUrlFilterStateToDraft(draft) {
        const filterState = compactFilterState(this.props.urlQuery?.f) ?? {};
        draft.quantity = filterState.qty ?? 1;
        draft.stockRequired = Boolean(filterState.stock);
        draft.tableIncludedProperties = new Set(filterState.cols ?? []);
        draft.requiredProperties = new Set(filterState.req ?? []);

        if (draft.properties.length > 0) {
            const defaults = {};
            const propertyValues = {};
            for (const propertyDic of draft.properties) {
                defaults[propertyDic.property] = propertyDic.values.map(x => x.key);
                propertyValues[propertyDic.property] = new Set(defaults[propertyDic.property]);
            }
            draft.activeProperties = defaults;
            const propertyFilters = filterState.p ?? {};
            for (const [property, values] of Object.entries(propertyFilters)) {
                const availableValues = propertyValues[property];
                if (!availableValues || !Array.isArray(values)) {
                    continue;
                }
                const selectedValues = values.filter(value => availableValues.has(value));
                if (selectedValues.length > 0) {
                    draft.activeProperties[property] = selectedValues;
                }
            }
        }
    }

    applyUrlFilterState() {
        const signature = filterUrlSignature(this.props.urlQuery);
        if (this.lastAppliedFilterSignature === signature) {
            return;
        }
        this.lastAppliedFilterSignature = signature;
        this.setState(produce(this.state, draft => {
            this.applyUrlFilterStateToDraft(draft);
        }));
    }

    buildUrlFilterState() {
        const propertyFilters = {};
        for (const [property, values] of Object.entries(this.state.activeProperties)) {
            const totalValues = this.state.propertyValueCounts[property];
            if (totalValues === undefined || !Array.isArray(values) || values.length === totalValues) {
                continue;
            }
            propertyFilters[property] = values;
        }

        return compactFilterState({
            p: propertyFilters,
            req: Array.from(this.state.requiredProperties),
            cols: Array.from(this.state.tableIncludedProperties),
            qty: this.state.quantity,
            stock: this.state.stockRequired,
        });
    }

    updateUrlFilterState(updateType) {
        const filterState = this.buildUrlFilterState();
        this.lastAppliedFilterSignature = JSON.stringify(filterState ?? {});
        this.props.setUrlQuery({f: filterState}, updateType);
    }

    // get text content from a react element object
    extractText(element) {
      // Check if the element is a simple string or number and return it as text
      if (typeof element === 'string' || typeof element === 'number') {
        return String(element);
      }

      // If the element has props and children, dive deeper
      if (element && element.props && element.props.children) {
        if (Array.isArray(element.props.children)) {
          // If children is an array, recursively extract text from each child
          return element.props.children.map(child => this.extractText(child)).join(' ');
        } else {
          // If children is a single element, recursively extract its text
          return this.extractText(element.props.children);
        }
      }

      // If we reach here, the element does not contain directly extractable text
      return '';
    }

    downloadComponents(components, header) {
      let headerContent = header.map(cell => `"${cell.name}"`).join(',');
      let csvContent = components.map((row, index) => {
        // expandableContent={this.props.expandableContent(row)}>
        let csvRow = header.map(cell => {
          if (cell.name === "Image") {
            return `"${cell.displayGetter(row)?.props?.src || ''}"`;
          } else {
            return '"' + this.extractText(cell.displayGetter(row)).trim().replace('"', "'") + '"';
          }
        }).join(',');

        return csvRow;
      }).join('\n');

      const blob = new Blob([`${headerContent}\n${csvContent}`], { type: "text/csv;charset=utf-8" });
      saveAs(blob, `components-${components.length}.csv`);
    }

    render() {
        let filterComponents = <>
            <CategoryFilter
                categories={this.state.categories}
                urlQuery={this.props.urlQuery}
                setUrlQuery={this.props.setUrlQuery}
                onChange={this.handleComponentsChange}
                onAnnounceChange={this.handleStartComponentsChange}/>
            <PropertySelect
                properties={this.state.properties}
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
                onStockRequired={this.handleStockRequired}/>
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
                    <CopyToClipboard text={x.mfr}>
                        <button className="py-2 px-4 pl-1" onClick={e => e.stopPropagation()}>
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
            this.state.activeProperties, this.state.requiredProperties, this.state.propertyValueCounts);
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
                            <div className="flex-none ml-auto block flex-none">
                                <CopyToClipboard text={filteredComponents.map(c => `wget ${c.datasheet}`).join("\n")}>
                                    <button className="bg-blue-500 hover:bg-blue-700 text-black py-2 px-2 mr-2 rounded" onClick={e => e.stopPropagation()}>
                                        wget all datasheets <FontAwesomeIcon icon="clipboard"/>
                                    </button>
                                </CopyToClipboard>
                                <button className="bg-blue-500 hover:bg-blue-700 text-black py-2 px-2 rounded" onClick={() => this.downloadComponents(filteredComponents, header)}>
                                    Download CSV <FontAwesomeIcon icon="download"/>
                                </button>
                            </div>
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

export function findCategoryById(categories = [], id) {
    return categories.find(category => category.id === id) ?? {
        category: "unknown",
        subcategory: "unknown"
    }
}

export function ExpandedComponent(props) {
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
            categoryFilterString: "",
            queryProgress: null,
            abort: () => null
        }
        this.lastAppliedUrlSignature = null;
    }

    componentDidMount() {
        this.applyUrlQuery();
    }

    componentDidUpdate(prevProps) {
        if (prevProps.categories !== this.props.categories) {
            this.applyUrlQuery(true);
        } else if (categoryUrlSignature(prevProps.urlQuery) !== categoryUrlSignature(this.props.urlQuery)) {
            this.applyUrlQuery();
        }
    }

    componentWillUnmount() {
        clearTimeout(this.searchTimeout);
        clearTimeout(this.categoryFilterTimeout);
    }

    collectActiveCategories = () => {
        return Object.values(this.state.categories).flat();
    }

    categoryMatchesFilter = (category, filterString = this.state.categoryFilterString) => {
        const words = filterString.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
        if (words.length === 0) {
            return true;
        }
        const haystack = [
            category.category,
            category.label,
            ...category.subcategories.flatMap(subcategory => [
                subcategory.value,
                subcategory.label
            ])
        ].filter(Boolean).join(" ").toLocaleLowerCase();
        return words.every(word => haystack.includes(word));
    }

    filteredCategories = (filterString = this.state.categoryFilterString) => {
        return this.props.categories.filter(category => this.categoryMatchesFilter(category, filterString));
    }

    applyCategoryFilterToDraft = draft => {
        const visibleCategories = new Set(this.filteredCategories(draft.categoryFilterString).map(category => category.category));
        for (const category of this.props.categories) {
            if (!visibleCategories.has(category.category)) {
                draft.categories[category.category] = [];
            } else if (draft.allCategories) {
                draft.categories[category.category] = category.subcategories.map(subcategory => subcategory.key);
            } else {
                draft.categories[category.category] ??= [];
            }
        }
    }

    stateFromUrlQuery = query => {
        const searchString = query?.q ?? "";
        const categoryFilterString = query?.cf ?? "";
        const categoryIds = new Set(sortedNumbers(query?.c));
        const noCategories = Boolean(query?.none);
        const allCategories = !noCategories && (
            Boolean(query?.all) ||
            (categoryIds.size === 0 && searchString.trim().length >= 3)
        );
        const categories = {};

        for (const category of this.props.categories) {
            const visible = this.categoryMatchesFilter(category, categoryFilterString);
            categories[category.category] = noCategories || !visible
                ? []
                : allCategories
                ? category.subcategories.map(subcategory => subcategory.key)
                : category.subcategories
                    .filter(subcategory => categoryIds.has(subcategory.key))
                    .map(subcategory => subcategory.key);
        }

        return { categories, allCategories, searchString, categoryFilterString };
    }

    applyUrlQuery = (force = false) => {
        const signature = categoryUrlSignature(this.props.urlQuery);
        if (!force && this.lastAppliedUrlSignature === signature) {
            return;
        }
        this.lastAppliedUrlSignature = signature;
        clearTimeout(this.searchTimeout);
        this.setState(this.stateFromUrlQuery(this.props.urlQuery), () => {
            this.clearStaleFilterUrlState();
            this.notifyParent();
        });
    }

    buildUrlQueryPatch(state = this.state) {
        const activeCategories = sortedNumbers(Object.values(state.categories).flat());
        const noCategories = !state.allCategories && activeCategories.length === 0;
        return {
            q: state.searchString || undefined,
            cf: state.categoryFilterString || undefined,
            all: state.allCategories ? true : undefined,
            none: noCategories ? true : undefined,
            c: state.allCategories || noCategories
                ? undefined
                : activeCategories,
            f: noCategories ? undefined : this.props.urlQuery?.f,
        };
    }

    updateUrlQuery = (updateType) => {
        const patch = this.buildUrlQueryPatch();
        this.lastAppliedUrlSignature = categoryUrlSignature({
            ...this.props.urlQuery,
            ...patch,
        });
        this.props.setUrlQuery?.(patch, updateType);
    }

    clearStaleFilterUrlState = () => {
        if (this.props.urlQuery?.none && this.props.urlQuery?.f !== undefined) {
            this.props.setUrlQuery?.({f: undefined}, "replaceIn");
        }
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
        let aborted = false;
        const queryToken = Symbol();
        this.activeQueryToken = queryToken;
        this.setState({abort: () => aborted = true, queryProgress: null});
        try {
            const components = await queryComponents({
                categoryIds: this.collectActiveCategories(),
                allCategories: this.state.allCategories && this.state.categoryFilterString.trim().length === 0,
                searchString: this.state.searchString,
                checkAbort: () => aborted,
                onProgress: progress => {
                    if (this.activeQueryToken !== queryToken || aborted) {
                        return;
                    }
                    this.pendingQueryProgress = progress;
                    if (this.progressUpdatePending) {
                        return;
                    }
                    this.progressUpdatePending = true;
                    window.requestAnimationFrame(() => {
                        this.progressUpdatePending = false;
                        if (this.activeQueryToken !== queryToken || aborted) {
                            return;
                        }
                        this.setState({queryProgress: this.pendingQueryProgress});
                    });
                }
            });
            if (this.activeQueryToken === queryToken && !aborted) {
                this.setState({
                    queryProgress: {
                        ...(this.pendingQueryProgress ?? {}),
                        phase: "Performing component query",
                        progress: 1,
                        etaSeconds: null,
                        done: true,
                    }
                });
            }
            return components;
        } finally {
            if (this.activeQueryToken === queryToken) {
                window.setTimeout(() => {
                    if (this.activeQueryToken === queryToken) {
                        this.setState({queryProgress: null});
                    }
                }, 1500);
            }
        }
    }

    handleCategoryChange = (category, value) => {
        console.log("Category change");
        this.setState(produce(this.state, draft => {
            draft.categories[category] = value.map(n => parseInt(n));
            draft.allCategories = false;
        }), () => {
            this.updateUrlQuery("pushIn");
            this.notifyParent();
        });
    }

    selectAll = state => {
        const visibleCategories = new Set(this.filteredCategories(state.categoryFilterString).map(category => category.category));
        for (let category of this.props.categories) {
            state.categories[category.category] = visibleCategories.has(category.category)
                ? category.subcategories.map( x => x.key )
                : [];
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
        this.setState(produce(this.state, this.selectAll), () => {
            this.updateUrlQuery("pushIn");
            this.notifyParent();
        });
    }

    handleSelectNone = () => {
        this.setState(produce(this.state, this.selectNone), () => {
            this.updateUrlQuery("pushIn");
            this.notifyParent();
        });
    }

    handleFulltextChange = e => {
        this.setState(produce(this.state, draft => {
            draft.searchString = e.target.value;
            if (!draft.allCategories && this.collectActiveCategories().length === 0)
                this.selectAll(draft);
        }), () => {
            this.updateUrlQuery("replaceIn");
            clearTimeout(this.searchTimeout);
            this.searchTimeout = setTimeout(this.notifyParent, 350);
        });
    }

    handleCategoryFilterChange = e => {
        this.setState(produce(this.state, draft => {
            draft.categoryFilterString = e.target.value;
            this.applyCategoryFilterToDraft(draft);
        }), () => {
            this.updateUrlQuery("replaceIn");
            clearTimeout(this.categoryFilterTimeout);
            this.categoryFilterTimeout = setTimeout(this.notifyParent, 350);
        });
    }

    handleClear = () => {
        this.setState(produce(this.state, draft => {
            draft.searchString = "";
            if (draft.allCategories) {
                this.selectNone(draft);
            }
        }), () => {
            this.updateUrlQuery("pushIn");
            this.notifyParent();
        });
    }

    render() {
        const filteredCategories = this.filteredCategories();
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
                    Search component by text:
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
            <div className="w-full flex p-2">
                <label className="flex-none block py-1 mr-2">
                    Filter categories:
                </label>
                <input type="text"
                    className="block flex-1 bg-white appearance-none border-2 border-gray-500 rounded w-full
                                py-1 px-4 text-gray-700 leading-tight focus:outline-none focus:bg-white
                                focus:border-blue-500"
                    placeholder="Category or subcategory text"
                    value={this.state.categoryFilterString}
                    onChange={this.handleCategoryFilterChange}/>
                {this.state.categoryFilterString
                    ? <button className="flex-none block ml-2 bg-blue-500 hover:bg-blue-700 text-black py-1 px-2 rounded" onClick={() => {
                        this.handleCategoryFilterChange({target: {value: ""}});
                    }}>
                        Clear filter
                    </button>
                    : null}
            </div>
            <QueryProgress progress={this.state.queryProgress}/>
            <div className="flex flex-wrap items-stretch">
                {filteredCategories.map(item => {
                    return <MultiSelectBox
                        className="bg-blue-500"
                        key={item.category}
                        name={item.category}
                        label={item.label}
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

function MultiSelectBox(props) {
    const handleAllClick = e => {
        e.preventDefault();
        let values = props.options.map(option => option.key);
        props.onChange(values);
    };

    const handleNoneClick = e => {
        e.preventDefault();
        props.onChange([]);
    };

    const handleSelectChange = e => {
        e.preventDefault();
        let value = Array.from(e.target.selectedOptions, option => option.value);
        props.onChange(value);
    };

    let selectStyle = {};
    if (props.minHeight)
        selectStyle.minHeight = props.minHeight;
    return <>
        <div className={`rounded flex flex-col flex-1 p-1 m-1 ${props.className}`}  style={{minWidth: "200px", maxWidth: "400px"}}>
            <div className="flex-none flex w-full">
                <h5 className="block flex-1 font-bold cursor-default rounded px-1 truncate hover:whitespace-normal"
                    title={props.label ?? props.name}>
                    {props.label ?? props.name}
                </h5>
                <div className="flex-none">
                    <button onClick={handleAllClick} className="mx-2">All</button>
                    <button onClick={handleNoneClick} className="mx-2">None</button>
                </div>
            </div>
            <select multiple="multiple" className="flex-1 w-full my-2 p-1"
                    style={selectStyle}
                    value={props.value ?? []} onChange={handleSelectChange}>
                {props.options.map(option => {
                    return <option value={option.key} key={option.key} title={option.value}>
                                {option.label ?? option.value}
                        </option>;
                })}
            </select>
            <div className="flex-none">
                {props.children}
            </div>
        </div>
    </>;
}

function SingleSelectBox(props) {
    return <select className={props.className} value={props.value} onChange={props.onChange}>
        {props.options.map(option => {
            return <option value={option.key} key={option.key}>
                        {option.value}
                </option>;
        })}
    </select>
}

function PropertySelector(props) {
    const valueTypes = useMemo(
        () => [...new Set(props.item.values.flatMap(x => Object.keys(x.value?.values ?? {})))]
            .map(x => ({key: x, value: x})),
        [props.item.values]
    );
    const [sortBy, setSortBy] = useState(valueTypes[0]?.value ?? "");

    useEffect(() => {
        if (!valueTypes.some(x => x.value === sortBy)) {
            setSortBy(valueTypes[0]?.value ?? "");
        }
    }, [sortBy, valueTypes]);

    const valueOptions = useMemo(() => {
        let options = [...props.item.values];
        options.sort((a, b) => attributeComparator(a.value, b.value, sortBy));
        return options.map(x => {
            const formatted = formatAttribute(x.value);
            return {
                key: x.key,
                value: formatted,
                label: `${formatted} (${formatCount(x.count)})`
            };
        });
    }, [props.item.values, sortBy]);

    return <MultiSelectBox
        className={props.className}
        minHeight="10em"
        name={props.item.property}
        options={valueOptions}
        value={props.value}
        onChange={value => {
            props.onChange(value); } }
    >
        <div className="w-full flex">
            <div className="flex-none">
                Sort by:
            </div>
            <div className="flex-1 ml-2">
                <SingleSelectBox
                    className="w-full rounded bg-white"
                    value={sortBy}
                    options={valueTypes}
                    onChange={e => setSortBy(e.target.value)}/>
            </div>
        </div>
        <div className="w-full">
            <input
                className="mr-2 leading-tight"
                type="checkbox"
                checked={props.tableIncluded}
                onChange={e => {
                    props.onTableInclude(e.target.checked); } } />
            Table column
        </div>
        <div className="w-full">
            <input
                className="mr-2 leading-tight"
                type="checkbox"
                checked={props.required}
                onChange={e => {
                    props.onPropertyRequired(e.target.checked); } } />
            Required
        </div>
    </MultiSelectBox>;
}

function PropertySelect(props) {
    return <div className="w-full p-2 border-b-2 border-gray-600 bg-gray-200">
        <h3 className="block w-full text-lg mx-2 font-bold" id="property-select">
            <span className="text-bold text-green-500">⛶</span> Property filter
        </h3>
        <div className="flex flex-wrap items-stretch">
            { props.properties.length === 0
            ? <p className="mx-2">
                There are no properties to select from. Select category or adjust the full-text search to include some components.
             </p>
            : props.properties.map(item => {
                return <PropertySelector
                    key={item.property}
                    className="bg-blue-500"
                    item={item}
                    value={props.values[item.property]}
                    onChange={value => props.onChange(item.property, value)}
                    tableIncluded={props.tableIncluded.includes(item.property)}
                    onTableInclude={value => props.onTableInclude(item.property, value)}
                    required={props.requiredProperties.includes(item.property)}
                    onPropertyRequired={value => props.onPropertyRequired(item.property, value) }
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

function QuantitySelect(props) {
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
                onChange={e => props.onChange(e.target.value)}
                value={props.value}
                />
            <div className="flex-none flex items-center">
                <input
                    className="px-2 ml-3 transform scale-150"
                    type="checkbox"
                    checked={props.stockRequired}
                    onChange={e => {
                        props.onStockRequired(e.target.checked)
                    }}/>
                <span className="ml-1 py-2 pl-2 leading-none">
                    Require on stock <br/>
                    <span className="text-gray-600 text-xs">
                        (Stock data can be 24 hours old)
                    </span>
                </span>
            </div>
        </div>
    </div>
}
