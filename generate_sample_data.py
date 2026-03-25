"""
generate_sample_data.py
Run this script to create sample_ecommerce_data.xlsx for testing the Phoenix Protocol.
Usage: python generate_sample_data.py
"""

import pandas as pd
import random
from datetime import datetime, timedelta
import os

random.seed(42)

# ─── Config ────────────────────────────────────────────────────────────────────
ROWS = 500

REGIONS     = ["North India", "South India", "West India", "East India", "Central India"]
CATEGORIES  = ["Electronics", "Fashion", "Home & Kitchen", "Books", "Sports", "Beauty", "Toys", "Grocery"]
PRODUCTS    = {
    "Electronics": ["Smartphone", "Laptop", "Earbuds", "Smartwatch", "Tablet", "LED TV"],
    "Fashion":     ["Kurta", "Jeans", "Saree", "T-Shirt", "Shoes", "Jacket"],
    "Home & Kitchen": ["Mixer Grinder", "Pressure Cooker", "Air Fryer", "Bedsheet", "Sofa Cover"],
    "Books":       ["Engineering Guide", "UPSC Prep", "Novel", "Self Help", "Science Book"],
    "Sports":      ["Cricket Bat", "Football", "Yoga Mat", "Dumbbells", "Badminton Racket"],
    "Beauty":      ["Face Cream", "Lipstick", "Shampoo", "Perfume", "Sunscreen"],
    "Toys":        ["LEGO Set", "Remote Car", "Barbie Doll", "Board Game", "Puzzle"],
    "Grocery":     ["Basmati Rice", "Cooking Oil", "Dal", "Tea Powder", "Spices Pack"]
}
PAYMENT     = ["UPI", "Credit Card", "Debit Card", "Net Banking", "Cash on Delivery", "EMI"]
STATUS      = ["Delivered", "Delivered", "Delivered", "Returned", "Cancelled", "Processing"]
CITIES      = ["Mumbai", "Delhi", "Bangalore", "Chennai", "Hyderabad", "Kolkata", "Pune", "Ahmedabad", "Jaipur", "Lucknow"]
PLATFORMS   = ["Mobile App", "Web Browser", "Mobile App", "Mobile App", "Web Browser"]

# ─── Generate ──────────────────────────────────────────────────────────────────
records = []
start_date = datetime(2024, 1, 1)

for i in range(1, ROWS + 1):
    category = random.choice(CATEGORIES)
    product  = random.choice(PRODUCTS[category])
    qty      = random.randint(1, 5)
    price    = round(random.uniform(99, 89999), 2)
    discount = round(random.uniform(0, 40), 1)
    final_price = round(price * qty * (1 - discount/100), 2)
    date     = start_date + timedelta(days=random.randint(0, 364))
    status   = random.choice(STATUS)
    rating   = round(random.uniform(2.0, 5.0), 1) if status == "Delivered" else None

    records.append({
        "Order_ID":        f"ORD{i:05d}",
        "Date":            date.strftime("%Y-%m-%d"),
        "Month":           date.strftime("%B %Y"),
        "Region":          random.choice(REGIONS),
        "City":            random.choice(CITIES),
        "Category":        category,
        "Product":         product,
        "Quantity":        qty,
        "Unit_Price":      price,
        "Discount_Pct":    discount,
        "Revenue":         final_price,
        "Payment_Method":  random.choice(PAYMENT),
        "Platform":        random.choice(PLATFORMS),
        "Order_Status":    status,
        "Customer_Rating": rating,
        "Shipping_Days":   random.randint(1, 10) if status == "Delivered" else None,
    })

df = pd.DataFrame(records)

# Save
out = "sample_ecommerce_data.xlsx"
df.to_excel(out, index=False)
print(f"✓ Generated {len(df)} rows → {out}")
print(f"\nColumns: {list(df.columns)}")
print(f"\nSample queries to try:")
print("  → What is the total revenue?")
print("  → Show me the top 5 categories by sales")
print("  → What is the trend over time?")
print("  → Count of orders by region")
print("  → What is the average order value?")
print("  → Give me a complete summary")