"""Shared helpers: project paths, settings, run folders, JSON/JSONL IO with schema checks, run record."""
import datetime as dt
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "schemas"
TEMPLATES = ROOT / "templates"
AGENTS = ROOT / ".claude" / "agents"
SKILLS = ROOT / ".claude" / "skills"
RUNS = ROOT / "runs"

STATEMENT_TYPES = ["Bug report", "Complaint", "Feature request", "Praise", "Question", "Comparison", "Other"]
SENTIMENTS = ["Positive", "Negative", "Neutral", "Mixed"]
SEVERITIES = ["Blocker", "Major", "Minor", "Cosmetic"]
UX_DIMENSIONS = ["Usability", "Reliability", "Performance", "Visual design", "Content and copy",
                 "Functionality", "Trust and safety", "Value and pricing", "Support", "Accessibility"]
# Short codes the AI steps write instead of full label names (fewer output tokens); code expands them.
TYPE_CODES = {"B": "Bug report", "C": "Complaint", "F": "Feature request", "P": "Praise", "Q": "Question", "X": "Comparison", "O": "Other"}
SENTIMENT_CODES = {"+": "Positive", "-": "Negative", "0": "Neutral", "m": "Mixed"}
SEVERITY_CODES = {"1": "Blocker", "2": "Major", "3": "Minor", "4": "Cosmetic"}
DIMENSION_CODES = {"US": "Usability", "RE": "Reliability", "PE": "Performance", "VD": "Visual design", "CC": "Content and copy",
                   "FU": "Functionality", "TS": "Trust and safety", "VP": "Value and pricing", "SU": "Support", "AC": "Accessibility"}


def decode(codes, v):
    """Expand a short code; full names pass through unchanged; null stays None."""
    if v is None or v == "":
        return None
    v = str(v)
    return codes.get(v, v)


TEAMS = ["Mobile engineering", "Backend and platform engineering", "QA and release", "UX design",
         "UI and visual design", "Content and localization", "Product management", "Payments and billing",
         "Marketing and CRM", "Customer support", "Operations and fulfilment", "Security and privacy",
         "Accessibility"]


# ---------- settings ----------

def parse_value(v):
    """Parse a --set override value with YAML rules (numbers, booleans, lists)."""
    return yaml.safe_load(v)


def load_settings(overrides=None):
    s = yaml.safe_load(open(ROOT / "config" / "settings.yaml", encoding="utf-8"))
    for k, v in (overrides or {}).items():
        cur = s
        parts = k.split(".")
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = v
    return s


# ---------- run folder ----------

class Run:
    """A run folder: runs/<app-id>_<date>/ with the PRD sub-folders."""

    SUBDIRS = ["raw", "clean", "labels", "issues", "validation", "stats", "report", "data", "ai"]

    def __init__(self, path):
        self.path = Path(path)
        for d in self.SUBDIRS:
            (self.path / d).mkdir(parents=True, exist_ok=True)

    def p(self, *parts):
        return self.path.joinpath(*parts)

    # run record
    @property
    def record_path(self):
        return self.p("run.json")

    def record(self):
        if self.record_path.exists():
            return json.load(open(self.record_path, encoding="utf-8"))
        return {}

    def update_record(self, **kw):
        r = self.record()
        for k, v in kw.items():
            if isinstance(v, dict) and isinstance(r.get(k), dict):
                r[k].update(v)
            else:
                r[k] = v
        write_json(self.record_path, r)
        return r

    def log(self, msg):
        line = "[%s] %s" % (dt.datetime.now().strftime("%H:%M:%S"), msg)
        print(line, flush=True)
        with open(self.p("run.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")


def run_from_args(argv=None):
    """Scripts take the run folder as their first argument."""
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        sys.exit("usage: %s <run-folder>" % sys.argv[0])
    return Run(argv[0])


def run_settings(run):
    return run.record().get("settings") or load_settings()


# ---------- IO ----------

_schema_cache = {}


def schema(name):
    if name not in _schema_cache:
        _schema_cache[name] = json.load(open(SCHEMAS / (name + ".schema.json"), encoding="utf-8"))
    return _schema_cache[name]


def validate(obj, schema_name):
    jsonschema.validate(obj, schema(schema_name))


def is_valid(obj, schema_name):
    try:
        validate(obj, schema_name)
        return True
    except jsonschema.ValidationError:
        return False


def write_json(path, obj, schema_name=None):
    if schema_name:
        validate(obj, schema_name)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, default=_default)
    os.replace(tmp, path)


def read_json(path):
    return json.load(open(path, encoding="utf-8"))


def write_jsonl(path, records, schema_name=None):
    if schema_name:
        for r in records:
            validate(r, schema_name)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, default=_default) + "\n")


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def write_yaml(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(obj, f, allow_unicode=True, sort_keys=False, width=110)


def read_yaml(path):
    return yaml.safe_load(open(path, encoding="utf-8"))


def _default(o):
    try:
        import numpy as np
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
    except ImportError:
        pass
    if isinstance(o, (set, tuple)):
        return list(o)
    if isinstance(o, (dt.date, dt.datetime)):
        return o.isoformat()
    raise TypeError("not JSON serializable: %r" % type(o))


# ---------- small utilities ----------

def sha(text, n=12):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:n]


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def words(text):
    return len(re.findall(r"\S+", text or ""))


class Timer:
    def __init__(self):
        self.t0 = time.time()

    def s(self):
        return round(time.time() - self.t0, 1)


COUNTRY_NAMES = {
    "us": "United States", "gb": "United Kingdom", "de": "Germany", "fr": "France", "jp": "Japan",
    "ca": "Canada", "au": "Australia", "cn": "China", "kr": "South Korea", "it": "Italy", "es": "Spain",
    "br": "Brazil", "mx": "Mexico", "in": "India", "nl": "Netherlands", "ru": "Russia", "tr": "Türkiye",
    "se": "Sweden", "ch": "Switzerland", "tw": "Taiwan", "hk": "Hong Kong", "pl": "Poland", "be": "Belgium",
    "at": "Austria", "no": "Norway", "dk": "Denmark", "fi": "Finland", "ie": "Ireland", "nz": "New Zealand",
    "sg": "Singapore", "my": "Malaysia", "th": "Thailand", "id": "Indonesia", "ph": "Philippines",
    "vn": "Vietnam", "sa": "Saudi Arabia", "ae": "United Arab Emirates", "il": "Israel", "za": "South Africa",
    "ar": "Argentina", "cl": "Chile", "co": "Colombia", "pt": "Portugal", "cz": "Czechia", "gr": "Greece",
    "hu": "Hungary", "ro": "Romania", "ua": "Ukraine", "eg": "Egypt", "pe": "Peru",
}

LANGUAGE_NAMES = {
    "en": "English", "de": "German", "fr": "French", "es": "Spanish", "it": "Italian", "pt": "Portuguese",
    "nl": "Dutch", "sv": "Swedish", "no": "Norwegian", "nb": "Norwegian", "da": "Danish", "fi": "Finnish",
    "pl": "Polish", "cs": "Czech", "sk": "Slovak", "hu": "Hungarian", "ro": "Romanian", "el": "Greek",
    "tr": "Turkish", "ru": "Russian", "uk": "Ukrainian", "ja": "Japanese", "ko": "Korean", "zh": "Chinese",
    "zh-cn": "Chinese", "zh-tw": "Chinese", "ar": "Arabic", "he": "Hebrew", "hi": "Hindi", "th": "Thai",
    "vi": "Vietnamese", "id": "Indonesian", "ms": "Malay", "tl": "Tagalog", "ca": "Catalan", "hr": "Croatian",
    "sl": "Slovenian", "bg": "Bulgarian", "et": "Estonian", "lv": "Latvian", "lt": "Lithuanian",
    "af": "Afrikaans", "sw": "Swahili", "fa": "Persian", "ur": "Urdu", "bn": "Bengali", "ta": "Tamil",
}


def language_name(code):
    if not code:
        return "Unknown"
    code = code.lower()
    return LANGUAGE_NAMES.get(code) or LANGUAGE_NAMES.get(code.split("-")[0]) or code.upper()


def country_name(code):
    return COUNTRY_NAMES.get(code.lower(), code.upper())
