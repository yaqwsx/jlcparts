import React from "react";
import { InlineSpinbox } from "./componentTable.js"
import { CORS_KEY } from "./corsBridge.js";
import { lcscCode } from './component'

export function getQuantityPrice(quantity, pricelist) {
    return pricelist.find(pricepoint =>
        quantity >= pricepoint.qFrom && (quantity <= pricepoint.qTo || !pricepoint.qTo)
    )?.price ?? pricelist[0]?.price;
}

export class AttritionInfo extends React.Component {
    constructor(props) {
        super(props);
        this.props = props;
        this.state = {}
    }

    componentDidMount() {
        fetch("https://cors.bridged.cc/https://jlcpcb.com/shoppingCart/smtGood/selectSmtComponentList", {
            method: 'POST',
            headers: {
                "Accept": 'application/json, text/plain, */*',
                "Content-Type": 'application/json;charset=UTF-8',
                "x-cors-grida-api-key": CORS_KEY
            },
            body: JSON.stringify({
                currentPage: 1,
                pageSize: 25,
                keyword: lcscCode(this.props.component),
                firstSortName: "",
                secondeSortName: "",
                searchSource: "search",
                componentAttributes: []
            })
        })
        .then(response => {
            if (!response.ok || response.status !== 200) {
                throw new Error(`Cannot fetch ${lcscCode(this.props.component)}: ${response.statusText}`);
            }
            return response.json();
        })
        .then(({data}) => {
            const lcscId = data.componentPageInfo.list.find(({componentCode}) => componentCode === lcscCode(this.props.component))?.componentId;
            if (lcscId === undefined) {
                throw new Error(`No search results for ${lcscCode(this.props.component)}`);
            }
            return fetch("https://cors.bridged.cc/https://jlcpcb.com/shoppingCart/smtGood/getComponentDetail?componentLcscId=" + lcscId, {
                headers: {
                    "x-cors-grida-api-key": CORS_KEY
                },
            });
        })
        .then(response => {
            if (!response.ok || response.status !== 200) {
                throw new Error(`Cannot fetch ${lcscCode(this.props)}: ${response.statusText}`);
            }
            return response.json();
        })
        .then(({data}) => {
            this.setState({data});
        })
        .catch(error => {
            this.setState({error: true, errorMessage: error.toString()});
            console.log(error);
        });
    }

    price() {
        let q = Math.max(parseInt(this.props.quantity) + parseInt(this.state.data.lossNumber),
            this.state.data.leastNumber);
        return q * getQuantityPrice(q, this.props.component.price);
    }

    render() {
        let data = this.state.data;
        if (this.state.error) {
            return <div className="bg-yellow-400 p-2 mt-2">
                Cannot fetch attrition data from JLC website: {this.state.errorMessage}.
            </div>
        }
        if (data)
            return <table className="w-full">
                <tbody>
                { data.lossNumber
                    ? <tr>
                        <td className="w-1 whitespace-no-wrap">Attrition:</td>
                        <td className="px-2">{data.lossNumber} pcs</td>
                      </tr>
                    : ""
                }
                { data.leastNumber
                    ? <tr>
                        <td className="w-1 whitespace-no-wrap">Minimal order quantity:</td>
                        <td className="px-2">{data.leastNumber} pcs</td>
                      </tr>
                    : ""
                }
                <tr>
                    <td className="w-1 whitespace-no-wrap">Price for {this.props.quantity} pcs:</td>
                    <td className="px-2">{Math.round((this.price() + Number.EPSILON) * 1000) / 1000} USD</td>
                </tr>
                </tbody>
            </table>
        return <div className="w-full p-4 text-center">
                <InlineSpinbox/>
            </div>;
    }
}
