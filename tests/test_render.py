"""Template contract: the sample data validates and renders; broken data and edited templates are refused."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import render_report  # noqa: E402

SAMPLE = json.load(open(ROOT / "templates" / "report_data.sample.json", encoding="utf-8"))


def test_sample_renders(tmp_path):
    out = tmp_path / "r.html"
    src = tmp_path / "d.json"
    src.write_text(json.dumps(SAMPLE), encoding="utf-8")
    render_report.main(src, render_report.TEMPLATE, out)
    html = out.read_text(encoding="utf-8")
    assert "__REPORT_DATA__" not in html and "{{TITLE}}" not in html
    assert "<title>ShopNest Review Report</title>" in html


def test_cross_reference_and_voice_checks():
    d = copy.deepcopy(SAMPLE)
    d["quotes"][0]["issue_id"] = "nope"
    d["summary"][0] = "Teams should look at this."
    errs = render_report.check_refs(d)
    assert any("unknown issue nope" in e for e in errs)
    assert any("prescriptive" in e for e in errs)


def test_template_hash_matches_release():
    assert render_report.check_template(render_report.TEMPLATE)


def test_edited_template_is_refused(tmp_path):
    t = tmp_path / "t.html"
    t.write_text(render_report.TEMPLATE.read_text(encoding="utf-8") + "<!-- edit -->", encoding="utf-8")
    with pytest.raises(SystemExit):
        render_report.check_template(t)
