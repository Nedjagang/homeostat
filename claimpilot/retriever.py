"""Lexical retriever over policies/*.md — stdlib only, no embedding API/key required.

Each policy doc is one clause (see policies/README.md), so retrieval is document-level:
score every doc against the query with TF-IDF cosine, filter by policy id if the question
names one, and return the top-k above a minimum-relevance floor. Below that floor we return
no context at all — this is what makes CLM-101/102/103 (the unanswerable claims) correctly
come back empty instead of weakly matching an unrelated clause.
"""
import math
import re
from collections import Counter
from pathlib import Path

POLICIES_DIR = Path(__file__).parent / "policies"
TOKEN_RE = re.compile(r"[a-z0-9]+")
MIN_RELEVANCE = 0.08

# Small stopword list — without it, boilerplate shared across every clause doc
# ("is", "of", "under", "policy"...) dominates cosine similarity over the terms
# that actually distinguish one clause from another.
STOPWORDS = {
    "a", "an", "the", "is", "are", "of", "to", "in", "on", "for", "and", "or",
    "this", "that", "per", "under", "from", "by", "as", "up", "through", "not",
    "all", "no", "be", "with", "at", "it", "its", "would", "will", "any",
    "policy", "section", "document", "coverage", "covered", "hp", "100", "au", "220",
}


def _tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


class Retriever:
    def __init__(self, policies_dir: Path = POLICIES_DIR):
        self.docs: list[tuple[str, str]] = []  # (filename, text)
        for path in sorted(policies_dir.glob("*.md")):
            if path.name == "README.md":
                continue
            self.docs.append((path.stem, path.read_text(encoding="utf-8")))
        self._doc_tokens = [Counter(_tokenize(text)) for _, text in self.docs]
        doc_freq: Counter = Counter()
        for tokens in self._doc_tokens:
            doc_freq.update(tokens.keys())
        n = max(len(self.docs), 1)
        self._idf = {term: math.log(n / (1 + df)) + 1 for term, df in doc_freq.items()}

    def _vector(self, tokens: Counter) -> dict[str, float]:
        return {t: c * self._idf.get(t, 0.0) for t, c in tokens.items()}

    @staticmethod
    def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
        common = set(a) & set(b)
        num = sum(a[t] * b[t] for t in common)
        norm_a = math.sqrt(sum(v * v for v in a.values()))
        norm_b = math.sqrt(sum(v * v for v in b.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return num / (norm_a * norm_b)

    def retrieve(self, query: str, policy_id: str | None = None, k: int = 3) -> list[tuple[str, str, float]]:
        """Return up to k (doc_name, text, score) tuples above MIN_RELEVANCE, best first."""
        q_vec = self._vector(Counter(_tokenize(query)))
        scored = []
        for (name, text), doc_tokens in zip(self.docs, self._doc_tokens):
            if policy_id and not name.upper().startswith(policy_id.upper()):
                continue
            score = self._cosine(q_vec, self._vector(doc_tokens))
            if score >= MIN_RELEVANCE:
                scored.append((name, text, score))
        scored.sort(key=lambda t: t[2], reverse=True)
        return scored[:k]


_default_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    global _default_retriever
    if _default_retriever is None:
        _default_retriever = Retriever()
    return _default_retriever
