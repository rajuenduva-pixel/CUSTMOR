import streamlit as st
from model import HyperlocalMatcher
from tools import filter_by_distance, load_local_store_data

st.title("🛒 Open-Source AI Hyperlocal Marketplace")
st.write(
    "Find discounted local products with zero delivery fees from your"
    " neighborhood!"
)

# Load data and model
products = load_local_store_data()
matcher = HyperlocalMatcher(products)

# User Input
user_query = st.text_input(
    "What are you looking for?", "I need fresh milk or vegetables with discount"
)
max_distance = st.slider("Max Distance (km)", 0.5, 5.0, 2.0)

if st.button("Search Local Stores"):
  raw_matches = matcher.search(user_query, top_k=3)
  final_matches = filter_by_distance(raw_matches, max_distance)

  if final_matches:
    st.success(f"Found {len(final_matches)} local products near you!")
    for item in final_matches:
      st.subheader(f"{item['product']} @ {item['store']}")
      st.write(f"🏷️ **Price:** ₹{item['discount_price']} (Original: ₹{item['price']})")
      st.write(
          f"📍 **Distance:** {item['distance_km']} km | 🎯 **Match Score:**"
          f" {item['relevance_score']:.2f}"
      )
      st.divider()
  else:
    st.warning("No matching local products found within this radius.")