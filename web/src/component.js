export function imageUrl(component, size) {
    if (!component.img) {
        return null;
    }
    const sizeInPx = {
        small: "96x96",
        medium: "224x224",
        big: "900x900"
    }[size];
    return `https://assets.lcsc.com/images/lcsc/${sizeInPx}/${component.img}`;
}

export function restoreLcscUrl(component) {
    return `https://lcsc.com/product-detail/${component.slug}_${component.lcsc}.html`;
}