"""Run the real local encoder on literary retrieval and paraphrased memories.

From apps/api: python -m evals.local_search --cache-dir /path/to/model/cache
No hosted inference, database, personal books, or credentials are used.
"""
import argparse
import asyncio
import json
import statistics
import time

from app.providers.embeddings.local import LocalEmbeddings
from app.providers.embeddings.space import EmbeddingSpace, LOCAL_MODEL, LOCAL_REVISION, QUERY_PROMPT
from tests.fixtures.eval_gold import GOLD_BOOK, GOLD_QUERIES


# Authored independently of model output; keep difficult cases in the suite.
MEMORIES = [
    ("I took his silence as grief, not indifference.", "Did I think his lack of speech meant he was mourning?"),
    ("The map seems unreliable to me; its maker had a reason to mislead travelers.", "What was my earlier suspicion about the cartographer's honesty?"),
    ("I felt the locked door was about her fear of remembering childhood.", "How did I interpret that inaccessible room and her suppressed past?"),
    ("When the daughter leaves, I see an act of freedom rather than abandonment.", "Was I sympathetic to the young woman's decision to depart?"),
    ("The factory ruins make me think of a community robbed of its livelihood.", "What did the derelict workplace suggest to me about economic loss?"),
    ("I wondered if the recurring birds represented the possibility of escape.", "Which repeated animal image did I associate with getting away?"),
    ("The narrator hides his own mistakes, so I doubt his account of the quarrel.", "Why was I skeptical of the storyteller's version of that argument?"),
    ("That meal reminded me of belonging: everyone had a place at the table.", "When did I notice hospitality creating a sense of inclusion?"),
    ("I read the storm as a release of emotions she could no longer contain.", "What connection did I draw between violent weather and pent-up feelings?"),
    ("The borrowed coat suggested she was trying on another person's identity.", "What did I say the clothing revealed about her changing sense of self?"),
]
DISTRACTORS = [
    "I liked the rhythm of the second paragraph.", "The town square sounds beautiful in autumn.",
    "I need to look up that unfamiliar nautical term.", "The chapter ended sooner than I expected.",
    "I found the description of the orchard very vivid.", "I wonder how far apart these villages are.",
    "The dog seems happy to see its owner again.", "I noticed a change from past to present tense.",
    "The recipe in the appendix looks difficult.", "The grandfather's joke made me laugh.",
]


async def evaluate(cache_dir: str, max_query_seconds: float):
    import numpy as np
    space = EmbeddingSpace("local", LOCAL_MODEL, 1024, LOCAL_REVISION, QUERY_PROMPT, max_tokens=2048)
    client = LocalEmbeddings(space, device="cpu", cache_dir=cache_dir, threads=4)
    started = time.perf_counter()
    documents = np.array(await client.embed([chunk.text for chunk in GOLD_BOOK.all_chunks]))
    preparation_seconds = time.perf_counter() - started
    recalls, reciprocal_ranks, query_seconds = [], [], []
    for query in GOLD_QUERIES:
        started = time.perf_counter()
        vector = np.array(await client.embed_single(query.query))
        query_seconds.append(time.perf_counter() - started)
        ranked = [GOLD_BOOK.all_chunks[i].id for i in (documents @ vector).argsort()[::-1]]
        relevant = set(query.relevant_chunk_ids)
        recalls.append(len(set(ranked[:5]) & relevant) / len(relevant))
        reciprocal_ranks.append(next((1 / rank for rank, item in enumerate(ranked, 1) if item in relevant), 0))
    memories = np.array(await client.embed([item[0] for item in MEMORIES] + DISTRACTORS))
    memory_hits = []
    for expected, (_, query) in enumerate(MEMORIES):
        vector = np.array(await client.embed_single(query))
        memory_hits.append(expected in (memories @ vector).argsort()[::-1][:3])
    report = {
        "model": space.model, "revision": space.revision, "device": "cpu", "threads": 4,
        "literary_queries": len(recalls), "recall_at_5": statistics.mean(recalls),
        "mrr": statistics.mean(reciprocal_ranks), "memory_hits_at_3": sum(bool(hit) for hit in memory_hits),
        "memory_queries": len(memory_hits), "cold_prepare_seconds": preparation_seconds,
        "warm_query_max_seconds": max(query_seconds), "warm_query_median_seconds": statistics.median(query_seconds),
    }
    print(json.dumps(report, indent=2))
    assert report["recall_at_5"] >= 0.8, "Literary recall fell below 0.8"
    assert report["mrr"] >= 0.9, "The first relevant passage ranks too low"
    assert all(memory_hits), "A paraphrased earlier thought was missed in the first three results"
    assert max(query_seconds) <= max_query_seconds, "Warm queries exceeded the CPU latency budget"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", default=".readagain/models")
    parser.add_argument("--max-query-seconds", type=float, default=2.0)
    args = parser.parse_args()
    asyncio.run(evaluate(args.cache_dir, args.max_query_seconds))
