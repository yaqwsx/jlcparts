import { db } from "./db";
import React from 'react';
import produce from 'immer';

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
        }));
    }

    handleActivePropertiesChange = (property, values) => {
        this.setState(produce(this.state, draft => {
            draft["activeProperties"][property] = values;
        }));
    }

    filterComponents() {
        return this.state.components.filter(component => {
            for (const property in this.state.activeProperties) {
                let attributes = component["attributes"];
                console.log(property, attributes)
                if (!(property in attributes))
                    continue;
                if (!(this.state.activeProperties[property].includes(attributes[property])))
                    return false;
            }
            return true;
        });
    }

    render() {
        return <>
            <CategoryFilter
                categories={this.state.categories}
                onChange={this.handleComponentsChange}/>
            <PropertySelect
                properties={this.collectProperties(this.state.components)}
                values={this.state.activeProperties}
                onChange={this.handleActivePropertiesChange}/>
            <QuantitySelect/>
            <ComponentTable components={this.filterComponents()} />
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
        this.setState({[category]: value.map(n => { return parseInt(n)})}, () => {
            this.componentQuery().toArray().then(components => {
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
        return <table className="w-full">
            <tbody>
            {this.props.components.length
                ?   this.props.components.map(component => {
                    return <tr key={component.lcsc}>
                        <td>{component.lcsc}</td>
                        <td>{component.description}</td>
                    </tr>})
                :   <div>No components match the select criteria</div>}
            </tbody>
        </table>
    }
}