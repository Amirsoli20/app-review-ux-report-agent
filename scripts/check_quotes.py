"""Step 6. Check that every statement's text span occurs verbatim in its review (gate 2).

Failures go back to statement-extractor once (task "fix_quotes"); spans that still fail are removed.
Writes labels/statements.jsonl in place and labels/quote_check.json.
"""
import sys
import unicodedata

import llm
from common import Run, read_jsonl, run_settings, write_json, write_jsonl


def norm(t):
    return " ".join(unicodedata.normalize("NFC", t or "").split())


def found(span, review):
    s = norm(span)
    return bool(s) and (s in norm(review["title"]) or s in norm(review["body"]) or s in norm(review["title"] + " " + review["body"]))


def main(run):
    s = run_settings(run)
    reviews = {r["review_id"]: r for r in read_jsonl(run.p("clean", "reviews.jsonl"))}
    sts = read_jsonl(run.p("labels", "statements.jsonl"))
    bad = [st for st in sts if not found(st["text_span"], reviews[st["review_id"]])]
    fixed = 0
    if bad:
        agent = llm.Agent("statement-extractor", s)
        chunks = [bad[i:i + 40] for i in range(0, len(bad), 40)]
        payloads = [{"task": "fix_quotes", "items": [{"statement_id": st["statement_id"], "review_title": reviews[st["review_id"]]["title"],
                                                      "review_body": reviews[st["review_id"]]["body"], "failed_span": st["text_span"],
                                                      "issue_phrase": st["issue_phrase"]} for st in c]} for c in chunks]

        def check(obj, payload):
            if not isinstance(obj, dict) or not isinstance(obj.get("fixes"), list):
                raise ValueError("the answer must be an object with a 'fixes' list")
            return []
        results = llm.map_batches(agent, payloads, run, None, check, s["ai_concurrency"], "quote batch")
        new = {}
        for res, _ in results:
            for f in (res or {}).get("fixes", []):
                if isinstance(f, dict) and f.get("text_span"):
                    new[f.get("statement_id")] = f["text_span"]
        for st in bad:
            span = new.get(st["statement_id"])
            if span and found(span, reviews[st["review_id"]]):
                st["text_span"] = span.strip()
                fixed += 1
    bad_ids = {st["statement_id"] for st in bad if not found(st["text_span"], reviews[st["review_id"]])}
    kept = [st for st in sts if st["statement_id"] not in bad_ids]
    write_jsonl(run.p("labels", "statements.jsonl"), kept, "statement")
    out = {"checked": len(sts), "failed": len(bad), "fixed": fixed, "removed": len(bad_ids), "kept": len(kept),
           "removed_ids": sorted(bad_ids)}
    write_json(run.p("labels", "quote_check.json"), out)
    run.log("%d statements quoted words not in the review. %d fixed on retry, %d removed: %d kept." % (
        len(bad), fixed, len(bad_ids), len(kept)))
    run.update_record(counts={"quotes": {k: v for k, v in out.items() if k != "removed_ids"}})
    return out


if __name__ == "__main__":
    main(Run(sys.argv[1]))
