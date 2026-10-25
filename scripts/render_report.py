"""Render the App Review UX report.

Usage: python render_report.py report_data.json report-template.html out/report.html
       python render_report.py --run runs/<app-id>_<date>      (step 15: HTML and PDF)

The template is fixed. This script only validates the data and injects it.
It never changes layout, styles or scripts. Any per-run difference in the
page must come from report_data.json.
"""
import html, json, shutil, subprocess, sys
from pathlib import Path
import jsonschema

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "schemas" / "report-data.schema.json"
TEMPLATE = ROOT / "templates" / "report-template.html"
TEMPLATE_HASH = ROOT / "templates" / "report-template.sha256"

# The template is a page body. As a standalone file it gets the same document skeleton the released sample
# report (docs/ShopNest Review Report.html) was published with: UTF-8, mobile viewport, base styles.
SKELETON_HEAD = ('<!doctype html><html><head><meta charset=utf8><meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">'
                 '<style>:root{color-scheme:light;box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}'
                 'html{scroll-padding-top:env(safe-area-inset-top,0px)}body{margin:0;padding:0;font:14px -apple-system,BlinkMacSystemFont,sans-serif;background:#fff;color:#000}'
                 'img{max-width:100%}[hidden]:not([hidden=until-found i]){display:none!important}</style></head><body>')
SKELETON_TAIL = "</body></html>"

def check_refs(d):
    ids = {i["id"] for i in d["issues"]}
    errs = []
    for q in d["quotes"]:
        if q["issue_id"] not in ids: errs.append("quote for unknown issue " + q["issue_id"])
    for st in d["journey"]["stages"]:
        for k in ("top_problem", "top_strength"):
            if st[k] and st[k] not in ids: errs.append("stage %s: unknown %s %s" % (st["name"], k, st[k]))
    for t in d["teams"]:
        for i in t["primary"] + t["secondary"]:
            if i not in ids: errs.append("team %s: unknown issue %s" % (t["name"], i))
    for i in d["issues"]:
        key = "n_high" if i["type"] == "Praise" else "n_low"
        if key not in i: errs.append("issue %s missing %s" % (i["id"], key))
        elif not 0 <= i[key] <= i["n"]: errs.append("issue %s: %s out of range" % (i["id"], key))
        if len(i["counts"]) != len(d["countries"]): errs.append("issue %s: counts length != countries" % i["id"])
    for t in d["summary"]:
        if len(t.split()) > 45: errs.append("summary item over 45 words: " + t[:40])
    banned = ("should", "recommend", "we suggest", "must fix", "priority")
    for t in d["summary"] + [d["patterns"]["caption"]] + list(d["glossary_examples"].values()):
        low = t.lower()
        for w in banned:
            if w in low: errs.append("prescriptive wording '%s' in: %s" % (w, t[:50]))
    return errs

def check_template(template_path):
    """Conformance check 12.8: the template must be the released version."""
    import hashlib
    if not TEMPLATE_HASH.exists(): return None
    want = TEMPLATE_HASH.read_text().split()[0]
    got = hashlib.sha256(Path(template_path).read_bytes()).hexdigest()
    if got != want:
        sys.exit("Template hash %s does not match the released version %s" % (got[:12], want[:12]))
    return got

def main(data_path, template_path, out_path, schema_path=SCHEMA):
    d = json.load(open(data_path, encoding="utf-8"))
    jsonschema.validate(d, json.load(open(schema_path, encoding="utf-8")))
    errs = check_refs(d)
    if errs:
        sys.exit("Report data failed checks:\n- " + "\n- ".join(errs))
    check_template(template_path)
    tpl = open(template_path, encoding="utf-8").read()
    assert tpl.count("__REPORT_DATA__") == 1 and tpl.count("{{TITLE}}") == 1, "template placeholders changed"
    payload = json.dumps(d, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--")
    title = html.escape(d["meta"]["app_short"] + " Review Report")
    out = tpl.replace("{{TITLE}}", title).replace("__REPORT_DATA__", payload)
    if not out.lstrip().lower().startswith("<!doctype"):
        out = SKELETON_HEAD + "\n" + out + "\n" + SKELETON_TAIL
    open(out_path, "w", encoding="utf-8").write(out)
    print("wrote", out_path)

def find_browser():
    for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Chromium.app/Contents/MacOS/Chromium",
              "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"):
        if Path(p).exists(): return p
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome", "msedge"):
        if shutil.which(name): return shutil.which(name)
    return None

def to_pdf(html_path, pdf_path):
    """Print the rendered HTML to PDF with a headless Chromium-family browser."""
    b = find_browser()
    if not b: return "no Chromium-family browser found; PDF skipped"
    import tempfile
    with tempfile.TemporaryDirectory() as prof:
        cmd = [b, "--headless=new", "--disable-gpu", "--no-first-run", "--no-pdf-header-footer", "--user-data-dir=" + prof,
               "--virtual-time-budget=8000", "--window-size=1200,1600", "--print-to-pdf=" + str(pdf_path), Path(html_path).resolve().as_uri()]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if not Path(pdf_path).exists(): return "PDF export failed: " + p.stderr[-300:]
    return None

def render_run(run_dir):
    run = Path(run_dir)
    rep = run / "report"
    main(rep / "report_data.json", TEMPLATE, rep / "report.html")
    err = to_pdf(rep / "report.html", rep / "report.pdf")
    if err: print(err)
    else: print("wrote", rep / "report.pdf")
    return err

if __name__ == "__main__":
    if sys.argv[1:2] == ["--run"]:
        render_run(sys.argv[2])
    else:
        main(*sys.argv[1:4])
