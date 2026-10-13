from __future__ import annotations

import heapq
import math
import re
from collections import Counter, defaultdict

_ASCII_WORD = re.compile(r"[a-z0-9]+(?:[._\-/][a-z0-9]+)*")
_ASCII_SPLIT = re.compile(r"[._\-/]")
_CJK_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")


def tokenize(text: str) -> list[str]:
    """中文按相邻两字切分，英文数字按词切分（带连字符的编号同时保留整体和各段）。"""
    lowered = (text or "").lower()
    tokens: list[str] = []
    for word in _ASCII_WORD.findall(lowered):
        tokens.append(word)
        parts = [part for part in _ASCII_SPLIT.split(word) if part]
        if len(parts) > 1:
            tokens.extend(parts)
    for run in _CJK_RUN.findall(lowered):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[index : index + 2] for index in range(len(run) - 1))
    return tokens


class BM25Index:
    def __init__(self, ids: list[str], documents: list[str], metadatas: list[dict], k1: float = 1.5, b: float = 0.75):
        self.ids = ids
        self.documents = documents
        self.metadatas = metadatas
        self.k1 = k1
        self.b = b
        self.term_freqs = [Counter(tokenize(doc)) for doc in documents]
        self.lengths = [sum(freqs.values()) for freqs in self.term_freqs]
        self.avg_length = (sum(self.lengths) / len(self.lengths)) if self.lengths else 1.0
        self.postings: dict[str, list[int]] = defaultdict(list)
        for index, freqs in enumerate(self.term_freqs):
            for term in freqs:
                self.postings[term].append(index)
        total = len(documents)
        self.idf = {
            term: math.log(1 + (total - len(docs) + 0.5) / (len(docs) + 0.5)) for term, docs in self.postings.items()
        }

    def __len__(self) -> int:
        return len(self.ids)

    def search(self, query: str, limit: int) -> list[tuple[int, float]]:
        scores: dict[int, float] = defaultdict(float)
        for term in set(tokenize(query)):
            idf = self.idf.get(term)
            if not idf:
                continue
            for index in self.postings[term]:
                freq = self.term_freqs[index][term]
                norm = self.k1 * (1 - self.b + self.b * self.lengths[index] / self.avg_length)
                scores[index] += idf * freq * (self.k1 + 1) / (freq + norm)
        return heapq.nlargest(limit, scores.items(), key=lambda item: item[1])
