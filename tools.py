def load_local_store_data():
    """Loads mock local store and product inventory data."""
    return [
        {
            "id": 1,
            "store": "Green Valley Grocers",
            "product": "Organic Milk (1L)",
            "price": 50,
            "discount_price": 42,
            "distance_km": 1.1,
            "category": "Dairy",
        },
        {
            "id": 2,
            "store": "Daily Needs Mart",
            "product": "Whole Wheat Bread",
            "price": 35,
            "discount_price": 28,
            "distance_km": 0.7,
            "category": "Bakery",
        },
        {
            "id": 3,
            "store": "Fresh Farm Produce",
            "product": "Fresh Tomatoes (1kg)",
            "price": 40,
            "discount_price": 30,
            "distance_km": 1.8,
            "category": "Vegetables",
        },
        {
            "id": 4,
            "store": "Corner Stationery",
            "product": "Spiral Notebook",
            "price": 60,
            "discount_price": 45,
            "distance_km": 0.4,
            "category": "Stationery",
        },
    ]


def filter_by_distance(products, max_distance):
    """Filters products within a specific neighborhood radius."""
    return [p for p in products if p["distance_km"] <= max_distance]