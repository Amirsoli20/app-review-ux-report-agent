"""Step 14. Audit the report text: every number must match stats.json (gate 7) and no prescriptive
wording may appear (gate 8). Failing slots are rewritten once by the report-auditor; anything still
failing is replaced by code-written text and flagged. -> report/report_data.json, report/audit.json
"""
import re
import sys

import llm
import report_sections
from common import Run, read_json, run_settings, write_json
from write_report import BANNED, assemble, check_slots, facts, fallback_slots, measures_used

NUM = re.compile(r"(?<![\w.])[-−+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])[-−+]?\d+(?:\.\d+)?")


def numbers_in(text):
    """Numbers written in a text slot, with their decimals. Version labels such as 8.5 are skipped when
    preceded by 'v' or 'version'."""
    out = []
    for m in NUM.finditer(text):
        pre = text[max(0, m.start() - 9):m.start()].lower()
        if re.search(r"(v|version |versions )$", pre):
            continue
        raw = m.group(0).replace("−", "-").replace(",", "").lstrip("+")
        dec = len(raw.split(".")[1]) if "." in raw else 0
        out.append((m.group(0), float(raw), dec))
    return out


def allowed_numbers(obj, acc=None):
    acc = acc if acc is not None else set()
    if isinstance(obj, bool):
        return acc
    if isinstance(obj, (int, float)):
        acc.add(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            allowed_numbers(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            allowed_numbers(v, acc)
    elif isinstance(obj, str):
        for _, v, _ in numbers_in(obj):
            acc.add(v)
    return acc


def matches(value, dec, allowed, structural):
    if dec == 0 and abs(value) in structural:
        return True
    for a in allowed:
        for x in (a, abs(a), 100 * a, abs(100 * a)):
            if round(x, dec) == round(abs(value), dec) or round(x, dec) == round(value, dec):
                return True
    return False


def audit_text(text, allowed, structural):
    bad = [tok for tok, v, d in numbers_in(text) if not matches(v, d, allowed, structural)]
    voice = [m.group(0) for m in BANNED.finditer(text)]
    return len(numbers_in(text)), bad, voice


def main(run):
    s = run_settings(run)
    stats = read_json(run.p("stats", "stats.json"))
    draft = read_json(run.p("report", "slots.draft.json"))
    slots = draft["slots"]
    allowed = allowed_numbers(stats)
    # fixed reference values the text may cite: p thresholds, Cramér's V and Cohen's d bands, κ bands and limit
    allowed |= {0.001, 0.01, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, float(s["kappa_flag"]), 100 * float(s["other_limit"])}
    rep = stats["report"]
    structural = {float(x) for x in range(0, 13)} | {float(len(rep["countries"])), float(len(rep["issues"])), 95.0, 100.0}
    need = measures_used(rep)
    fb = fallback_slots(stats)
    agent = llm.Agent("report-auditor", s)
    fx = facts(stats)
    checked = mismatches = voice_hits = rewritten = replaced = 0
    log = []

    def fix(path, text, getter_fb):
        nonlocal checked, mismatches, voice_hits, rewritten, replaced
        n, bad, voice = audit_text(text, allowed, structural)
        checked += n
        if not bad and not voice:
            return text
        mismatches += len(bad)
        voice_hits += len(voice)
        try:
            out = llm.call(agent, {"slot": path, "text": text, "numbers_not_in_data": bad, "banned_words": voice, "facts": fx},
                           run, None, lambda o: [] if isinstance(o, dict) and isinstance(o.get("text"), str) and o["text"].strip() else ["need {\"text\": ...}"],
                           tag="audit " + path)
            new = out["text"].strip()
        except RuntimeError:
            new = None
        if new is not None:
            _, bad2, voice2 = audit_text(new, allowed, structural)
            if not bad2 and not voice2:
                rewritten += 1
                log.append({"slot": path, "before": text, "after": new, "numbers": bad, "voice": voice, "result": "rewritten"})
                return new
        replaced += 1
        alt = getter_fb()
        log.append({"slot": path, "before": text, "after": alt, "numbers": bad, "voice": voice, "result": "replaced by code text"})
        return alt

    fb_sum = fb["summary"]
    slots["summary"] = [fix("summary[%d]" % k, t, lambda k=k: fb_sum[min(k, len(fb_sum) - 1)]) for k, t in enumerate(slots["summary"])]
    for k in ("problems_title", "strengths_title", "caption"):
        slots["patterns"][k] = fix("patterns." + k, slots["patterns"][k], lambda k=k: fb["patterns"][k])
    for k in list(slots["glossary_examples"]):
        slots["glossary_examples"][k] = fix("glossary_examples." + k, slots["glossary_examples"][k], lambda k=k: fb["glossary_examples"][k])
    # rewritten text must still respect the slot limits; a slot that does not is replaced by code text
    from common import words
    from write_report import CAPTION_OPEN
    for k, t in enumerate(slots["summary"]):
        if words(t) > 45 or len(t) > 330:
            slots["summary"][k] = fb_sum[min(k, len(fb_sum) - 1)]
            replaced += 1
    for k in ("problems_title", "strengths_title"):
        t = slots["patterns"][k]
        if words(t) > 14 or len(t) > 90:
            slots["patterns"][k] = fb["patterns"][k]
            replaced += 1
    cap = slots["patterns"]["caption"]
    if not cap.startswith(CAPTION_OPEN) or words(cap) > 70 or len(cap) > 480:
        slots["patterns"]["caption"] = fb["patterns"]["caption"]
        replaced += 1
    for k, t in slots["glossary_examples"].items():
        if words(t) > 25 or len(t) > 180:
            slots["glossary_examples"][k] = fb["glossary_examples"][k]
            replaced += 1
    if check_slots(slots, need):
        log.append({"slot": "all", "problems": check_slots(slots, need), "result": "all slots replaced by code text"})
        slots = fb
    unresolved = replaced
    out = {"numbers_checked": checked, "mismatches": mismatches, "voice_matches": voice_hits, "rewritten": rewritten,
           "replaced_by_code_text": replaced, "unresolved": unresolved, "log": log}
    data = assemble(stats, slots)
    data["reliability"] = report_sections.reliability(run, stats, out)
    data["workflow"] = report_sections.workflow(run, stats, out)
    write_json(run.p("report", "report_data.json"), data, "report-data")
    write_json(run.p("report", "audit.json"), out)
    run.log("Report audit: %d numbers checked against the data, %d mismatches, %d prescriptive words; %d slots rewritten, %d replaced by code text." % (
        checked, mismatches, voice_hits, rewritten, replaced))
    run.update_record(counts={"audit": {k: v for k, v in out.items() if k != "log"}}, prompts={agent.name: agent.version})
    return out


if __name__ == "__main__":
    main(Run(sys.argv[1]))
