"""Step 7. Group issue phrases: multilingual sentence embeddings, then HDBSCAN (section 7, pass 2).

Clustering runs over every statement's phrase (identical phrases repeat), so a phrase that many reviews
write the same way forms a group of its own. Noise points form single-phrase groups.
-> issues/groups.json, issues/phrase_vectors.npz, group_id on each statement.
"""
import collections
import random
import sys

import numpy as np

from common import Run, read_jsonl, run_settings, write_json, write_jsonl

_model = None


def phrase_key(p):
    return " ".join(p.lower().split())


def embed(phrases, model_name):
    """L2-normalised vectors. Falls back to character n-gram TF-IDF + SVD when the model is unavailable."""
    global _model
    try:
        from sentence_transformers import SentenceTransformer
        if _model is None:
            _model = SentenceTransformer(model_name)
        v = _model.encode(phrases, batch_size=128, normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(v, dtype=np.float32), model_name
    except Exception as e:  # noqa: BLE001
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.preprocessing import normalize
        x = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1).fit_transform(phrases)
        k = max(2, min(128, x.shape[1] - 1, x.shape[0] - 1))
        v = TruncatedSVD(k, random_state=0).fit_transform(x) if x.shape[0] > 2 else x.toarray()
        return normalize(v).astype(np.float32), "tfidf-char-svd (fallback: %s)" % type(e).__name__


def load_vectors(run):
    z = np.load(run.p("issues", "phrase_vectors.npz"), allow_pickle=True)
    return {k: v for k, v in zip(z["keys"].tolist(), z["vectors"])}


def cluster(vectors, min_size):
    from sklearn.cluster import HDBSCAN
    if len(vectors) < max(min_size, 2) + 1:
        return np.full(len(vectors), -1)
    return HDBSCAN(min_cluster_size=min_size, metric="euclidean", copy=True).fit(vectors).labels_


def build_groups(sts, vec_of, labels, prefix, seed):
    rng = random.Random(seed)
    members = collections.defaultdict(list)
    noise_ix = {}
    for st, lab in zip(sts, labels):
        k = phrase_key(st["issue_phrase"])
        if lab >= 0:
            gid = "%s%d" % (prefix, lab)
        else:
            gid = noise_ix.setdefault(k, "%sn%d" % (prefix, len(noise_ix)))
        members[gid].append(st)
    groups = []
    for gid, ms in members.items():
        cnt = collections.Counter(phrase_key(m["issue_phrase"]) for m in ms)
        keys = list(cnt)
        mat = np.stack([vec_of[k] for k in keys])
        cen = (mat * np.array([cnt[k] for k in keys])[:, None]).sum(0)
        cen = cen / (np.linalg.norm(cen) or 1)
        order = np.argsort(-(mat @ cen))
        central = [{"phrase": keys[i], "n": cnt[keys[i]]} for i in order[:20]]
        sample = rng.sample(ms, min(5, len(ms)))
        groups.append({
            "group_id": gid, "clustered": not gid.startswith(prefix + "n"), "n_statements": len(ms),
            "n_reviews": len({m["review_id"] for m in ms}), "n_distinct": len(keys), "central_phrases": central,
            "quotes": [{"text": " ".join(m["text_span"].split()[:30]), "translation": m.get("translation")} for m in sample],
            "types": dict(collections.Counter(m["statement_type"] for m in ms).most_common()),
            "sentiments": dict(collections.Counter(m["sentiment"] for m in ms).most_common()),
            "ux_dimensions": dict(collections.Counter(m["ux_dimension"] for m in ms).most_common(3)),
            "statement_ids": [m["statement_id"] for m in ms]})
        for m in ms:
            m["group_id"] = gid
    groups.sort(key=lambda g: (-g["n_statements"], g["group_id"]))
    return groups


def group(run, sts, min_size, prefix="g"):
    """Embed (cached) and cluster the given statements; returns groups and sets st['group_id']."""
    s = run_settings(run)
    vec_path = run.p("issues", "phrase_vectors.npz")
    vec_of = load_vectors(run) if vec_path.exists() else {}
    keys = sorted({phrase_key(st["issue_phrase"]) for st in sts} - set(vec_of))
    model_used = None
    if keys:
        v, model_used = embed(keys, s["embedding_model"])
        vec_of.update(zip(keys, v))
        all_keys = sorted(vec_of)
        np.savez_compressed(vec_path, keys=np.array(all_keys, dtype=object), vectors=np.stack([vec_of[k] for k in all_keys]))
    labels = cluster(np.stack([vec_of[phrase_key(st["issue_phrase"])] for st in sts]), min_size) if sts else []
    return build_groups(sts, vec_of, labels, prefix, s["random_seed"]), model_used


def main(run, min_size=None):
    s = run_settings(run)
    min_size = int(min_size or s["min_cluster_size"])
    sts = read_jsonl(run.p("labels", "statements.jsonl"))
    groups, model_used = group(run, sts, min_size)
    write_jsonl(run.p("labels", "statements.jsonl"), sts, "statement")
    n_clusters = sum(g["clustered"] for g in groups)
    out = {"min_cluster_size": min_size, "embedding_model": model_used or s["embedding_model"], "n_phrases": len(sts),
           "n_distinct": len({phrase_key(st["issue_phrase"]) for st in sts}), "n_clusters": n_clusters,
           "n_groups": len(groups), "groups": groups}
    write_json(run.p("issues", "groups.json"), out)
    run.log("%d phrases, %d distinct. Embeddings and clustering formed %d clusters and %d single-phrase groups." % (
        out["n_phrases"], out["n_distinct"], n_clusters, len(groups) - n_clusters))
    run.update_record(counts={"group": {k: v for k, v in out.items() if k != "groups"}})
    return out


if __name__ == "__main__":
    main(Run(sys.argv[1]))
