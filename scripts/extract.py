"""Step 5. Split reviews into statements with the statement-extractor sub-agent -> labels/statements.jsonl.

Batches of `extraction_batch_size` reviews run in parallel. A batch whose records fail the schema or the
extraction rules is resent once with the errors; records that still fail are dropped and counted (gate 1).
"""
import sys

import jsonschema

from common import (DIMENSION_CODES, SENTIMENT_CODES, SEVERITY_CODES, SEVERITIES, TYPE_CODES, Run, decode, read_json, read_jsonl, run_settings, schema, words, write_json,
                    write_jsonl)
import llm

ITEM_SCHEMA = None


def app_context(app):
    notes = [{"version": v["version"], "date": v["date"], "notes": v["notes"][:300]} for v in app["versions"][:4]]
    return {"name": app["name"], "category": app["category"], "subtitle": app.get("subtitle"),
            "description": app["description"][:1500], "in_app_purchases": [i["name"] for i in app["in_app_purchases"][:8]],
            "recent_versions": notes}


def record_problems(st, ids):
    """Rule violations for one statement; an empty list means the record is kept."""
    global ITEM_SCHEMA
    if ITEM_SCHEMA is None:
        ITEM_SCHEMA = schema("extractor_output")["properties"]["statements"]["items"]
    p = []
    if st.get("_bad"):
        return [st["_bad"]]
    try:
        jsonschema.validate(st, ITEM_SCHEMA)
    except jsonschema.ValidationError as e:
        return ["schema: %s" % e.message[:160]]
    if st["review_id"] not in ids:
        p.append("unknown review_id %s" % st["review_id"])
    if words(st["issue_phrase"]) > 8:
        p.append("issue_phrase over 8 words: %s" % st["issue_phrase"])
    if words(st["location_phrase"]) > 5:
        p.append("location_phrase over 5 words: %s" % st["location_phrase"])
    if st["statement_type"] in ("Bug report", "Complaint") and st["severity"] not in SEVERITIES:
        p.append("severity missing for %s in %s" % (st["statement_type"], st["review_id"]))
    return p


def decode_rows(obj, payload):
    """Expand the compact answer {"s": [[i, span, translation, issue, location, T, S, V, D, conf]], "x": [i]} into
    statement dicts keyed by review_id. Malformed rows become records that fail the rule check."""
    if not isinstance(obj, dict) or not isinstance(obj.get("s"), list):
        raise ValueError('the answer must be an object {"s": [rows], "x": [review numbers]}')
    ids = {r["i"]: r["_id"] for r in payload["reviews"]}
    out = []
    for row in obj["s"]:
        if not isinstance(row, list) or len(row) != 10:
            out.append({"review_id": None, "_bad": "row must have 10 values: %s" % str(row)[:80]})
            continue
        i, span, tr, issue, loc, t, se, sv, dim, conf = row
        out.append({"review_id": ids.get(i, "unknown review %s" % i), "text_span": span, "translation": tr,
                    "issue_phrase": issue, "location_phrase": loc, "statement_type": decode(TYPE_CODES, t),
                    "sentiment": decode(SENTIMENT_CODES, se), "severity": decode(SEVERITY_CODES, sv),
                    "ux_dimension": decode(DIMENSION_CODES, dim), "confidence": conf})
    return {"statements": out, "excluded": [ids[i] for i in obj.get("x") or [] if i in ids]}


def check_batch(obj, payload):
    obj = decode_rows(obj, payload)
    ids = {r["_id"] for r in payload["reviews"]}
    problems = []
    for st in obj.get("statements", []):
        problems += record_problems(st, ids)
    covered = {s.get("review_id") for s in obj.get("statements", [])} | set(obj.get("excluded") or [])
    missing = ids - covered
    if missing:
        problems.append("reviews with neither statements nor an 'excluded' entry: %s" % ", ".join(sorted(missing)))
    return problems


def normalize(st):
    if st["statement_type"] not in ("Bug report", "Complaint"):
        st["severity"] = None
    if st.get("translation") is not None and not str(st["translation"]).strip():
        st["translation"] = None
    for k in ("text_span", "issue_phrase", "location_phrase"):
        st[k] = st[k].strip()
    return st


def main(run):
    s = run_settings(run)
    app = read_json(run.p("app.json"))
    reviews = read_jsonl(run.p("clean", "reviews.jsonl"))
    agent = llm.Agent("statement-extractor", s)
    ctx = app_context(app)
    bs = int(s["extraction_batch_size"])
    batches = [reviews[i:i + bs] for i in range(0, len(reviews), bs)]
    payloads = [{"app": ctx, "reviews": [{"i": k + 1, "stars": r["rating"], "lang": r["language"], "title": r["title"],
                                          "body": r["body"], "_id": r["review_id"]} for k, r in enumerate(b)]} for b in batches]
    run.log("Extracting statements from %d reviews in %d batches (%s)." % (len(reviews), len(batches), agent.model))
    results = llm.map_batches(agent, payloads, run, None, check_batch, s["ai_concurrency"], "batch", return_last=True)

    statements, excluded, dropped, failed_batches, missing = [], [], 0, [], 0
    for (res, err), p in zip(results, payloads):
        ids = {r["_id"] for r in p["reviews"]}
        try:
            res = decode_rows(res, p)
        except ValueError as e:
            failed_batches.append(err or str(e))
            missing += len(ids)
            continue
        per_review = {}
        for st in res.get("statements", []):
            if record_problems(st, ids):
                dropped += 1
                continue
            st = normalize(st)
            k = per_review.get(st["review_id"], 0) + 1
            per_review[st["review_id"]] = k
            st = {"statement_id": "%s_s%d" % (st["review_id"], k), **st,
                  "issue_id": None, "stage_id": None, "group_id": None, "proposed_issue": None, "second_pass": None}
            statements.append(st)
        ex = set(res.get("excluded") or []) & ids
        excluded += sorted(ex - set(per_review))
        missing += len(ids - set(per_review) - ex)
    write_jsonl(run.p("labels", "statements.jsonl"), statements, "statement")
    write_json(run.p("labels", "extraction.json"), {"excluded_reviews": excluded, "dropped_records": dropped,
                                                    "failed_batches": failed_batches, "missing_reviews": missing,
                                                    "batches": len(batches), "prompt_version": agent.version})
    run.log("%d reviews became %d statements in %d batches; %d reviews had no meaningful text; %d records dropped by the schema gate%s." % (
        len(reviews), len(statements), len(batches), len(excluded), dropped,
        ("; %d batches failed" % len(failed_batches)) if failed_batches else ""))
    run.update_record(counts={"extract": {"reviews": len(reviews), "statements": len(statements), "batches": len(batches),
                                          "excluded_reviews": len(excluded), "dropped_records": dropped,
                                          "failed_batches": len(failed_batches), "missing_reviews": missing}},
                      prompts={agent.name: agent.version})
    return statements


if __name__ == "__main__":
    main(Run(sys.argv[1]))
