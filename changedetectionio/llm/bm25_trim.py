"""
BM25-based relevance trimming for large snapshot text.

When a snapshot is large and no CSS pre-filter has narrowed it down,
we use BM25 to select the lines most relevant to the user's intent
before sending to the LLM. This keeps the context focused without
an arbitrary char truncation.

Pure functions — no side effects, fully testable.
"""

