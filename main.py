from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class HyperlocalMatcher:

  def __init__(self, products):
    self.products = products
    # Combine product text features for NLP vectorization
    self.descriptions = [
        f"{p['product']} {p['category']} {p['store']}" for p in products
    ]
    self.vectorizer = TfidfVectorizer()
    self.tfidf_matrix = self.vectorizer.fit_transform(self.descriptions)

  def search(self, query, top_k=2):
    """Finds the most relevant products matching the user's natural language query."""
    query_vec = self.vectorizer.transform([query])
    scores = cosine_similarity(query_vec, self.tfidf_matrix).flatten()
    top_indices = scores.argsort()[::-1][:top_k]

    results = []
    for idx in top_indices:
      if scores[idx] > 0:
        prod = self.products[idx].copy()
        prod["relevance_score"] = float(scores[idx])
        results.append(prod)
    return results