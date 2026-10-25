"""Step 9. Assign every statement one frozen issue (or "other") and one journey stage (or "none").

The issue-assigner sees each statement with the issue proposed by its phrase group and the stage proposed
by its where-in-the-app phrase, and confirms or corrects both. -> labels/final.jsonl
"""
import sys

import llm
from common import TYPE_CODES, Run, read_jsonl, read_yaml, run_settings, write_json, write_jsonl


def frozen(run):
    issues = read_yaml(run.p("issues", "issues.yaml"))["issues"]
    structure = read_yaml(run.p("issues", "structure.yaml"))
    return issues, structure


def proposed_stage(st, structure, issue_stage):
    loc = " ".join(st["location_phrase"].lower().split())
    m = structure.get("location_to_stage") or {}
    if loc in m:
        return m[loc]
    return issue_stage.get(st.get("proposed_issue")) or "none"


def main(run, subset_ids=None):
    s = run_settings(run)
    issues, structure = frozen(run)
    src = run.p("labels", "final.jsonl") if subset_ids is not None else run.p("labels", "statements.jsonl")
    sts = read_jsonl(src)
    issue_ids = {i["issue_id"] for i in issues} | {"other"}
    stage_ids = {st["id"] for st in structure["stages"]} | {"none"}
    issue_stage = {i["issue_id"]: i["stage_id"] for i in issues}
    todo = [st for st in sts if subset_ids is None or st["statement_id"] in subset_ids]
    agent = llm.Agent("issue-assigner", s)
    ctx = {"issues": [{"issue_id": i["issue_id"], "name": i["name"], "definition": i["definition"]} for i in issues],
           "stages": [{"stage_id": st["id"], "name": st["name"], "desc": st["desc"]} for st in structure["stages"]]}
    bs = int(s["assignment_batch_size"])
    chunks = [todo[i:i + bs] for i in range(0, len(todo), bs)]
    rev = {v: k for k, v in TYPE_CODES.items()}
    # rows: [n, quote, translation, issue phrase, location phrase, type code, proposed issue, proposed stage]
    payloads = [dict(ctx, statements=[[k + 1, st["text_span"], st.get("translation"), st["issue_phrase"], st["location_phrase"],
                                       rev.get(st["statement_type"], "O"), st["proposed_issue"] or "other",
                                       proposed_stage(st, structure, issue_stage)] for k, st in enumerate(c)],
                     _ids=[st["statement_id"] for st in c]) for c in chunks]

    def check(obj, payload):
        if not isinstance(obj, dict) or not isinstance(obj.get("c"), list):
            raise ValueError('the answer must be an object {"c": [[n, issue_id, stage_id], ...]} (empty list when nothing changes)')
        probs = []
        n = len(payload["statements"])
        for x in obj["c"]:
            if not (isinstance(x, list) and len(x) == 3 and isinstance(x[0], int) and 1 <= x[0] <= n):
                probs.append("each change must be [n, issue_id, stage_id] with n from 1 to %d: %s" % (n, str(x)[:60]))
            elif x[1] not in issue_ids:
                probs.append("%s: unknown issue_id %s" % (x[0], x[1]))
            elif x[2] not in stage_ids:
                probs.append("%s: unknown stage_id %s" % (x[0], x[2]))
        return probs

    run.log("Assigning %d statements to %d issues and %d stages in %d batches (%s)." % (
        len(todo), len(issues), len(structure["stages"]), len(chunks), agent.model))
    results = llm.map_batches(agent, payloads, run, None, check, s["ai_concurrency"], "batch", return_last=True)
    by_id = {st["statement_id"]: st for st in sts}
    moved = to_other = kept_proposal = failed = stage_changed = 0
    for (res, err), p in zip(results, payloads):
        ok = isinstance(res, dict) and isinstance(res.get("c"), list)
        changes = {}
        for x in (res.get("c") if ok else []):
            if isinstance(x, list) and len(x) == 3 and x[1] in issue_ids and x[2] in stage_ids and isinstance(x[0], int):
                changes[x[0]] = x
        for row, sid in zip(p["statements"], p["_ids"]):
            st = by_id[sid]
            st["issue_id"], st["stage_id"] = row[6], row[7]
            if not ok:
                failed += 1
                continue
            x = changes.get(row[0])
            if x is None:
                kept_proposal += 1
                continue
            st["issue_id"], st["stage_id"] = x[1], x[2]
            if x[1] != row[6]:
                moved += 1
                to_other += x[1] == "other"
            else:
                kept_proposal += 1
            stage_changed += x[2] != row[7]
    write_jsonl(run.p("labels", "final.jsonl"), sts, "statement")
    n_other = sum(st["issue_id"] == "other" for st in sts)
    out = {"assigned": len(todo), "moved": moved, "set_to_other": to_other, "confirmed": kept_proposal, "stage_changed": stage_changed,
           "kept_proposal_after_failure": failed, "other_total": n_other, "subset": subset_ids is not None}
    write_json(run.p("labels", "assignment%s.json" % ("_retry" if subset_ids is not None else "")), out)
    run.log("Every statement checked against the issue list and the journey. %d moved to a better issue, %d set to other; %d statements are other in total." % (
        moved, to_other, n_other))
    run.update_record(counts={"assign" + ("_retry" if subset_ids is not None else ""): out}, prompts={agent.name: agent.version})
    return out


if __name__ == "__main__":
    main(Run(sys.argv[1]))
