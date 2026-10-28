"""Semantic ranking of already-authorized historical comparisons."""
import hashlib
import json
import math
import re

from . import runtime as rt
from .config import settings


DIMENSIONS = 512


def _vector(value):
    if (not isinstance(value, list) or len(value) != DIMENSIONS
            or any(not isinstance(x, (int, float)) or not math.isfinite(x) for x in value)
            or not any(value)):
        raise RuntimeError('Invalid prior-case embedding; semantic search did not complete')
    return value


def _embed(tool, texts):
    response = tool.client.embeddings.create(
        model=settings.embedding_model, input=texts, dimensions=DIMENSIONS)
    tool.tokens += response.usage.total_tokens if response.usage else 0
    # Match by index, not response array position.
    items = {item.index: _vector(item.embedding) for item in response.data}
    if len(response.data) != len(texts) or set(items) != set(range(len(texts))):
        raise RuntimeError('Incomplete prior-case embeddings; semantic search did not complete')
    return [items[i] for i in range(len(texts))]


def rank_prior_cases(tool, candidates, query):
    """Call only after family, time, status and account authorization filters."""
    search = (query.strip() or 'Comparable reviewed trading cases: '
              + ', '.join(tool.ctx['families']))[:4000]
    terms = set(re.findall(r'\w+', search.lower()))
    vectors, missing = {}, []
    for i, record in enumerate(candidates):
        # Bound input length; the original text remains the returned source.
        text = record['text'][:4000]
        identity = [settings.embedding_model, DIMENSIONS, record['case_id'],
                    record['origin'], record['closed_at'], text]
        digest = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
        key = 'prior_case_embedding:v1:' + digest
        cached = rt.meta_get(key)
        if cached is not None:
            vectors[i] = _vector(cached)
        else:
            missing.append((i, key, text))
    for offset in range(0, len(missing), 64):
        batch = missing[offset:offset + 64]
        embedded = _embed(tool, [text for _, _, text in batch])
        for (i, key, _), vector in zip(batch, embedded):
            rt.meta_set(key, vector)
            vectors[i] = vector
    query_vector = _embed(tool, [search])[0]
    query_norm = math.sqrt(sum(x*x for x in query_vector))
    scored = []
    for i, record in enumerate(candidates):
        vector = vectors[i]
        semantic = sum(a*b for a, b in zip(query_vector, vector)) / (
            query_norm * math.sqrt(sum(x*x for x in vector)))
        lexical = len(terms & set(re.findall(r'\w+', record['text'].lower())))
        scored.append((semantic, lexical, record))
    scored.sort(key=lambda item: (item[0], item[1], item[2]['closed_at'],
                                  item[2]['case_id']), reverse=True)
    rt.audit(tool.run_id, 'prior_case_search', {
        'method': 'OpenAI embeddings + cosine similarity',
        'model': settings.embedding_model, 'dimensions': DIMENSIONS,
        'eligible_count': len(candidates), 'embedded_count': len(missing),
        'cache_hit_count': len(candidates) - len(missing),
        'returned_count': min(3, len(scored)),
    })
    return scored[:3]
