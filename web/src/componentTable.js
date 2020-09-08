import { db } from "./db"
import React from 'react';

export class ComponentOverview extends React.Component {
    constructor(props) {
        super(props);
        this.state = {
            "components": [],
            "categories": []
        };
    }

    componentDidMount() {
        db.components.toArray().then( components => {
            this.setState({"components": components });
        });
        db.categories.toArray().then( categories => {
            console.log("X", categories);
            this.setState({"categories": categories });
        })
    }

    render() {
        return <>
            <CategoryFilter categories={this.state.categories}/>
            <PropertySelect/>
            <QuantitySelect/>
            <ComponentTable components={this.state.components} />
        </>
    }
}

class CategoryFilter extends React.Component {
    categories() {
        let categories = {};
        console.log("Y", this.props.categories);
        for (const category of this.props.categories) {
            console.log(category);
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
                console.log(a, b)
                return a["value"].localeCompare(b["value"]);
            });
            sortedCategories.push({
                "category": key,
                "subcategories": subCats
            });
        }
        return sortedCategories;
    }

    render() {
        return <div className="w-full bg-blue-200">
            <h3>Select category</h3>
            <div className="flex items-stretch">
                {this.categories().map(item => {
                    return <SelectBox
                        name={item["category"]}
                        options={item["subcategories"]} />;
                })}
            </div>
        </div>
    }
}

class SelectBox extends React.Component {
    render() {
        return <>
            <div className="rounded flex flex-col w-64 p-1 mx-1 bg-blue-600">
                <div className="flex-none flex w-full">
                    <h5 class="block flex-1 font-bold">{this.props.name}</h5>
                    <div class="flex-1">
                        <a href="#" className="px-3">All</a>
                        <a href="#" className="px-3">None</a>
                    </div>
                </div>
                <select multiple="multiple" className="flex-1 w-full my-2">
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
            {this.props.components.map(component => {
                return <tr key={component.lcsc}>
                    <td>{component.lcsc}</td>
                    <td>{component.description}</td>
                </tr>
            })}
        </table>
    }
}