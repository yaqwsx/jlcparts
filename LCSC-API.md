# LCSC API

- to get a product page based on LCSC number use GET request on
  `https://lcsc.com/api/global/additional/search?q=<part_number>`. You get a
  JSON with URL of the product.
- to get a product options based on LSCS number use POST request to
  `https://lcsc.com/api/products/search` with data
  `current_page=1&in_stock=false&is_RoHS=false&show_icon=false&search_content=<part_number>`
  You have to include CSRF token and cookies. Both you can get from the category page (e.g., `https://lcsc.com/products/Pre-ordered-Products_11171.html`)