import React from "react";

export function getQuantityPrice(quantity, pricelist) {
    for (let pricepoint of pricelist) {
        if (quantity >= pricepoint.qFrom && (quantity <= pricepoint.qTo || !pricepoint.qTo))
            return pricepoint.price;
    }
    if (pricelist[0])
        return pricelist[0].price;
    return undefined;
}

export class AttritionInfo extends React.Component {
    constructor(props) {
        super(props);
        this.props = props;
        this.state = {}
    }

    componentDidMount() {
        fetch("https://jlcpcb.com/shoppingCart/smtGood/getComponentDetail?componentCode=" + this.props.component.lcsc)
                .then(response => {
                    if (!response.ok) {
                        console.log(`Cannot fetch ${this.props.lcsc}: ${response.statusText}`);
                        return;
                    }
                    return response.json();
                })
                .then(responseJson => {
                    this.setState({data: responseJson.data});
                });
    }

    price() {
        let q = Math.max(this.props.quantity + this.state.data.lossNumber,
            this.state.data.leastNumber);
        return q * getQuantityPrice(q, this.props.component.price);
    }

    render() {
        let data = this.state.data;
        if (data)
            return <table className="w-full">
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
            </table>
        return "";
    }
}