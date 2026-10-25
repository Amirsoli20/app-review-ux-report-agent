"""Step 10. Second, independent labeling pass on a stratified sample, and Cohen's kappa (FR-13).

The second-rater uses a different prompt, reads the whole review, and never sees the first pass labels or
phrases. -> validation/validation.json, second_pass on the sampled statements in labels/final.jsonl.
"""
import collections
import math
import random
import sys

import llm
from assign_labels import frozen
from common import SENTIMENT_CODES, SEVERITY_CODES, TYPE_CODES, Run, decode, read_jsonl, run_settings, write_json, write_jsonl
from statlib import kappa


def sample(sts, share, min_per, seed):
    rng = random.Random(seed)
    by = collections.defaultdict(list)
    for st in sts:
        by[st["issue_id"]].append(st)
    out = []
    for k in sorted(by):
        xs = sorted(by[k], key=lambda x: x["statement_id"])
        n = max(math.ceil(share * len(xs)), min(min_per, len(xs)))
        out += rng.sample(xs, min(n, len(xs)))
    return sorted(out, key=lambda x: x["statement_id"])


def main(run):
    s = run_settings(run)
    issues, structure = frozen(run)
    sts = read_jsonl(run.p("labels", "final.jsonl"))
    reviews = {r["review_id"]: r for r in read_jsonl(run.p("clean", "reviews.jsonl"))}
    picked = sample(sts, float(s["second_pass_share"]), int(s["second_pass_min_per_issue"]), s["random_seed"])
    issue_ids = {i["issue_id"] for i in issues} | {"other"}
    stage_ids = {st["id"] for st in structure["stages"]} | {"none"}
    ctx = {"issues": [{"issue_id": i["issue_id"], "name": i["name"], "definition": i["definition"]} for i in issues],
           "stages": [{"stage_id": st["id"], "name": st["name"], "desc": st["desc"]} for st in structure["stages"]]}
    bs = int(s["second_pass_batch_size"])
    chunks = [picked[i:i + bs] for i in range(0, len(picked), bs)]

    def payload_for(c):
        """Each review once, with its sampled statements as [n, quote, translation] (n numbers statements in the batch)."""
        groups, ids = [], []
        for st in c:
            ids.append(st["statement_id"])
            r = reviews[st["review_id"]]
            if not groups or groups[-1]["_rid"] != r["review_id"]:
                groups.append({"_rid": r["review_id"], "title": r["title"], "body": r["body"][:1500], "statements": []})
            groups[-1]["statements"].append([len(ids), st["text_span"], st.get("translation")])
        return dict(ctx, reviews=groups, _ids=ids)
    payloads = [payload_for(c) for c in chunks]
    agent = llm.Agent("second-rater", s)

    def rows(obj, n):
        if not isinstance(obj, dict) or not isinstance(obj.get("r"), list):
            raise ValueError('the answer must be an object {"r": [[n, issue_id, stage_id, type, sentiment, severity], ...]}')
        good, probs = {}, []
        for x in obj["r"]:
            if not (isinstance(x, list) and len(x) == 6 and isinstance(x[0], int) and 1 <= x[0] <= n):
                probs.append("each row must be [n, issue_id, stage_id, type, sentiment, severity]: %s" % str(x)[:60])
            elif x[1] not in issue_ids:
                probs.append("%s: unknown issue_id %s" % (x[0], x[1]))
            elif x[2] not in stage_ids:
                probs.append("%s: unknown stage_id %s" % (x[0], x[2]))
            else:
                good[x[0]] = {"issue_id": x[1], "stage_id": x[2], "statement_type": decode(TYPE_CODES, x[3]),
                              "sentiment": decode(SENTIMENT_CODES, x[4]), "severity": decode(SEVERITY_CODES, x[5])}
        missing = sorted(set(range(1, n + 1)) - set(good))
        if missing and not probs:
            probs.append("missing statements: %s" % ", ".join(map(str, missing[:20])))
        return good, probs

    def check(obj, payload):
        return rows(obj, len(payload["_ids"]))[1]

    run.log("Second pass on %d statements (%.0f%%, stratified by issue) in %d batches (%s)." % (
        len(picked), 100 * len(picked) / max(1, len(sts)), len(chunks), agent.model))
    results = llm.map_batches(agent, payloads, run, None, check, s["ai_concurrency"], "batch", return_last=True)
    second = {}
    for (res, _), p in zip(results, payloads):
        try:
            good, _ = rows(res, len(p["_ids"]))
        except ValueError:
            continue
        for n, x in good.items():
            second[p["_ids"][n - 1]] = x
    pairs = []
    by_id = {st["statement_id"]: st for st in sts}
    for sid, x in second.items():
        st = by_id[sid]
        st["second_pass"] = x
        pairs.append({"statement_id": sid, "main": {k: st.get(k) for k in x}, "second": x})
    write_jsonl(run.p("labels", "final.jsonl"), sts, "statement")

    def col(key, rows):
        return [str(r["main"].get(key)) for r in rows], [str(r["second"].get(key)) for r in rows]
    k = {}
    for key in ("issue_id", "stage_id", "statement_type", "sentiment"):
        a, b = col(key, pairs)
        k[key] = kappa(a, b) if pairs else None
    sev_rows = [r for r in pairs if r["main"].get("severity")]
    a, b = col("severity", sev_rows)
    k["severity"] = kappa(a, b) if len(sev_rows) >= 10 else None
    per_issue = {}
    for i in sorted(issue_ids - {"other"}):
        a = ["1" if r["main"]["issue_id"] == i else "0" for r in pairs]
        b = ["1" if r["second"]["issue_id"] == i else "0" for r in pairs]
        n_main, n_second = a.count("1"), b.count("1")
        per_issue[i] = {"kappa": kappa(a, b) if (n_main or n_second) else None, "n_main": n_main, "n_second": n_second,
                        "n_both": sum(x == y == "1" for x, y in zip(a, b))}
    out = {"n": len(pairs), "requested": len(picked), "share": len(pairs) / max(1, len(sts)), "kappa": k,
           "per_issue": per_issue, "prompt_version": agent.version, "pairs": pairs}
    write_json(run.p("validation", "validation.json"), out)
    run.log("%d statements labeled again with a different prompt. Issue κ = %s." % (
        len(pairs), "n/a" if k["issue_id"] is None else "%.2f" % k["issue_id"]))
    run.update_record(counts={"second_pass": {"n": len(pairs), "requested": len(picked), "kappa": k}},
                      prompts={agent.name: agent.version})
    return out


if __name__ == "__main__":
    main(Run(sys.argv[1]))
