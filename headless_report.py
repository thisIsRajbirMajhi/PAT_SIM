"""Intuitive reporting layer for headless.py.

Adds ANSI colors, progress bar, TL;DR, breakdowns, leaderboards,
failure buckets, regression diff, repro scripts, and an HTML report.

Wire-up: see the 3-line patch to headless.py at the bottom of this file.
"""
import json
import os
import shutil
import sys
import time
from collections import Counter, defaultdict

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[31m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN    = "\033[36m"
    B_RED   = "\033[91m"
    B_GREEN = "\033[92m"
    B_YELLOW= "\033[93m"
    B_BLUE  = "\033[94m"
    B_MAG   = "\033[95m"
    B_CYAN  = "\033[96m"


_COLOR_MODE = "auto"   # auto | always | never

def set_color_mode(mode: str):
    global _COLOR_MODE
    _COLOR_MODE = mode

def _color_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if _COLOR_MODE == "never":
        return False
    if _COLOR_MODE == "always":
        return True
    return sys.stdout.isatty()

def c(text, *codes) -> str:
    s = _fold_console(str(text))
    if not _color_enabled() or not codes:
        return s
    return "".join(codes) + s + C.RESET


_ASCII_FOLD = str.maketrans({
    "╔": "+", "╗": "+", "╚": "+", "╝": "+",
    "═": "-", "║": "|", "─": "-", "│": "|",
    "✓": "v", "✗": "x", "█": "#", "░": ".",
    "→": ">", "·": ".",
})

def _fold_console(s: str) -> str:
    """Fold box-drawing glyphs to ASCII when stdout can't encode them
    (e.g. Windows cp1252 console). UTF-8 terminals are untouched."""
    try:
        s.encode(sys.stdout.encoding or "utf-8")
        return s
    except Exception:
        return s.translate(_ASCII_FOLD)


VERDICT_STYLE = {
    "STRICT-PASS":       (C.B_GREEN, "\u2713"),
    "INTERMITTENT-PASS": (C.B_YELLOW, "~"),
    "FAIL":              (C.B_RED, "\u2717"),
    "ERROR":             (C.B_MAG, "!"),
}

def verdict_str(v: str) -> str:
    col, glyph = VERDICT_STYLE.get(v, ("", "?"))
    return c(f"{glyph} {v}", col, C.BOLD)


# ---------------------------------------------------------------------------
# Live progress
# ---------------------------------------------------------------------------
class Progress:
    def __init__(self, total, width=28, enabled=True):
        self.total = max(int(total), 1)
        self.width = width
        self.enabled = enabled and _color_enabled()
        self.tallies = Counter()
        self.worst_lock = (None, 1e9)   # (case, lock)
        self.best_lock  = (None, -1.0)
        self.started = time.perf_counter()
        self._last_len = 0

    def update(self, i, r):
        self.tallies[r["verdict"]] += 1
        lp = r.get("lock_pct", 0.0)
        if lp < self.worst_lock[1]:
            self.worst_lock = (r["case"], lp)
        if lp > self.best_lock[1]:
            self.best_lock = (r["case"], lp)
        self._render(i, r)

    def _render(self, i, r):
        if not self.enabled:
            return
        pct = i / self.total
        filled = int(self.width * pct)
        bar = c("\u2588" * filled, C.B_GREEN) + c("\u2591" * (self.width - filled), C.DIM)
        elapsed = time.perf_counter() - self.started
        eta = (elapsed / i) * (self.total - i) if i else 0
        verdict = verdict_str(r["verdict"])
        tally = (f'{c(str(self.tallies["STRICT-PASS"]), C.B_GREEN)}S '
                 f'{c(str(self.tallies["INTERMITTENT-PASS"]), C.B_YELLOW)}I '
                 f'{c(str(self.tallies["FAIL"]), C.B_RED)}F '
                 f'{c(str(self.tallies["ERROR"]), C.B_MAG)}E')
        worst = (c(f'{self.worst_lock[0]}@{self.worst_lock[1]:.0f}%', C.B_RED)
                 if self.worst_lock[0] else "-")
        line = (f'[{bar}] {i:>3}/{self.total} {verdict:<22} {tally} '
                f'| worst {worst} | ETA {eta:>4.0f}s | {r["case"]:<14}')
        pad = max(self._last_len - len(_strip_ansi(line)), 0)
        sys.stdout.write("\r" + line + " " * pad)
        sys.stdout.flush()
        self._last_len = len(_strip_ansi(line))
        if i == self.total:
            sys.stdout.write("\n")
            sys.stdout.flush()


def _strip_ansi(s: str) -> str:
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


# ---------------------------------------------------------------------------
# TL;DR banner
# ---------------------------------------------------------------------------
def print_tldr(results, wall_s):
    sp = sum(1 for r in results if r["verdict"] == "STRICT-PASS")
    ip = sum(1 for r in results if r["verdict"] == "INTERMITTENT-PASS")
    fl = sum(1 for r in results if r["verdict"] == "FAIL")
    er = sum(1 for r in results if r["verdict"] == "ERROR")
    total = len(results)
    pct = 100.0 * (sp + ip) / total if total else 0.0

    tracking = [r for r in results if r.get("frames")]
    worst = min(tracking, key=lambda r: r.get("lock_pct", 0.0), default=None)
    best  = max(tracking, key=lambda r: r.get("lock_pct", 0.0), default=None)

    W = 74
    def line(txt, *codes):
        return c("\u2551 " + txt.ljust(W - 2) + " \u2551", *codes)

    print()
    print(c("\u2554" + "\u2550" * W + "\u2557", C.B_CYAN, C.BOLD))
    print(line(f'TL;DR: {sp + ip}/{total} passed ({pct:.1f}%) in {wall_s:.1f}s',
               C.B_CYAN, C.BOLD))
    print(line(
        f'\u2713 {sp} STRICT   ~ {ip} INTERMITTENT   '
        f'\u2717 {fl} FAIL   ! {er} ERROR',
        C.B_CYAN))
    if best:
        print(line(f'Best : {best["case"]:<14} lock {best["lock_pct"]:>5.1f}%  '
                   f'rmse {best["rmse"]:>5.2f}'))
    if worst:
        print(line(f'Worst: {worst["case"]:<14} lock {worst["lock_pct"]:>5.1f}%  '
                   f'rmse {worst["rmse"]:>5.2f}'))
    print(c("\u255a" + "\u2550" * W + "\u255d", C.B_CYAN, C.BOLD))


# ---------------------------------------------------------------------------
# Breakdown by severity / tag
# ---------------------------------------------------------------------------
def _breakdown_table(title, key_fn, results):
    buckets = defaultdict(lambda: Counter())
    for r in results:
        k = key_fn(r) or "-"
        buckets[k][r["verdict"]] += 1
    if not buckets:
        return
    print()
    print(c(f"=== {title} ===", C.BOLD, C.B_CYAN))
    print(c(f'{"KEY":<18}{"TOT":>5}{"PASS":>7}{"INT":>6}{"FAIL":>6}{"ERR":>6}{"PASS%":>8}',
            C.BOLD))
    print(c("-" * 56, C.DIM))
    for k in sorted(buckets.keys()):
        b = buckets[k]
        t = sum(b.values())
        p, i, f, e = b["STRICT-PASS"], b["INTERMITTENT-PASS"], b["FAIL"], b["ERROR"]
        pct = 100.0 * (p + i) / t if t else 0.0
        col = C.B_GREEN if pct >= 90 else (C.B_YELLOW if pct >= 60 else C.B_RED)
        print(f'{k:<18}{t:>5}{c(f"{p:>7}", C.B_GREEN)}{c(f"{i:>6}", C.B_YELLOW)}'
              f'{c(f"{f:>6}", C.B_RED)}{c(f"{e:>6}", C.B_MAG)}{c(f"{pct:>7.1f}%", col)}')


def print_severity_summary(results):
    _breakdown_table("Severity breakdown", lambda r: r.get("severity"), results)

def print_tag_summary(results):
    def tag_of(r):
        tags = r.get("tags") or []
        return tags[0] if tags else None
    _breakdown_table("Primary-tag breakdown", tag_of, results)


# ---------------------------------------------------------------------------
# Leaderboards
# ---------------------------------------------------------------------------
def print_leaderboards(results, n=5):
    tracking = [r for r in results if r.get("frames")]
    if not tracking:
        return
    print()
    print(c("=== Leaderboards ===", C.BOLD, C.B_CYAN))
    top = sorted(tracking, key=lambda r: r.get("lock_pct", 0), reverse=True)[:n]
    bot = sorted(tracking, key=lambda r: r.get("lock_pct", 0))[:n]
    def row(r, col):
        return (f'  {r["case"]:<14} lock {c(f"{r["lock_pct"]:>5.1f}%", col)}  '
                f'rmse {r["rmse"]:>5.2f}  p95 {r["p95"]:>5.2f}  '
                f'1st {str(r["first_lock"]):>5}')
    print(c(f"TOP {n} (best lock%):", C.B_GREEN))
    for r in top:
        print(row(r, C.B_GREEN))
    print(c(f"BOTTOM {n} (worst lock%):", C.B_RED))
    for r in bot:
        print(row(r, C.B_RED))


# ---------------------------------------------------------------------------
# Failure cause buckets
# ---------------------------------------------------------------------------
_CAUSE_PATTERNS = [
    ("timeout",     "timeout"),
    ("exception",   "Traceback"),
    ("rmse",        "rmse "),
    ("lock",        "lock "),
    ("first_lock",  "first_lock "),
    ("losses",      "losses "),
    ("acq/valid",   "intermittent rule"),
]

def _classify(reason: str) -> str:
    for name, needle in _CAUSE_PATTERNS:
        if needle in (reason or ""):
            return name
    return "other"

def print_failure_buckets(results):
    fails = [r for r in results if r["verdict"] in ("FAIL", "ERROR")]
    if not fails:
        return
    print()
    print(c("=== Failure causes ===", C.BOLD, C.B_CYAN))
    buckets = defaultdict(list)
    for r in fails:
        buckets[_classify(r.get("reason", ""))].append(r["case"])
    for cause in sorted(buckets.keys()):
        cases = buckets[cause]
        print(f'  {c(cause, C.B_RED, C.BOLD):<24} '
              f'{c(str(len(cases)), C.BOLD)} case(s): {", ".join(cases)}')


# ---------------------------------------------------------------------------
# Regression diff vs last run
# ---------------------------------------------------------------------------
def load_previous_run(runs_dir="runs", exclude_path=None):
    if not os.path.isdir(runs_dir):
        return None, None
    snaps = sorted(
        (p for p in (os.path.join(runs_dir, f) for f in os.listdir(runs_dir)
                     if f.startswith("headless_") and f.endswith(".json"))),
        key=os.path.getmtime, reverse=True)
    for p in snaps:
        if exclude_path and os.path.abspath(p) == os.path.abspath(exclude_path):
            continue
        try:
            with open(p) as f:
                return json.load(f), p
        except Exception:
            continue
    return None, None

def print_regression_diff(prev_payload, results):
    if not prev_payload:
        print()
        print(c("(no previous run to diff against)", C.DIM))
        return
    prev = {r["case"]: r["verdict"] for r in prev_payload.get("results", [])}
    now  = {r["case"]: r["verdict"] for r in results}
    new_pass, new_fail, regressed, recovered = [], [], [], []
    for k, v in now.items():
        pv = prev.get(k)
        if pv is None:
            continue
        was_ok = pv in ("STRICT-PASS", "INTERMITTENT-PASS")
        is_ok  = v  in ("STRICT-PASS", "INTERMITTENT-PASS")
        if is_ok and not was_ok:  recovered.append(k)
        if not is_ok and was_ok:  regressed.append(k)
        if v  == "STRICT-PASS" and pv != "STRICT-PASS": new_pass.append(k)
        if v  == "FAIL"        and pv != "FAIL":        new_fail.append(k)
    print()
    print(c("=== Regression diff vs previous run ===", C.BOLD, C.B_CYAN))
    if not (regressed or recovered):
        print(c("  \u2713 no verdict changes since last run", C.B_GREEN))
    if regressed:
        print(c(f"  \u2717 REGRESSED ({len(regressed)}): ", C.B_RED, C.BOLD)
              + ", ".join(regressed))
    if recovered:
        print(c(f"  \u2713 RECOVERED ({len(recovered)}): ", C.B_GREEN, C.BOLD)
              + ", ".join(recovered))
    if new_pass:
        print(c(f"  \u2191 new STRICT ({len(new_pass)}): ", C.B_GREEN)
              + ", ".join(new_pass))
    if new_fail:
        print(c(f"  \u2193 new FAIL ({len(new_fail)}): ", C.B_RED)
              + ", ".join(new_fail))


# ---------------------------------------------------------------------------
# Repro scripts
# ---------------------------------------------------------------------------
def write_repro_scripts(results, stamp, runs_dir="runs"):
    fails = [r for r in results if r["verdict"] in ("FAIL", "ERROR")]
    if not fails:
        return None, None
    sh_path = os.path.join(runs_dir, f"repro_{stamp}.sh")
    ps_path = os.path.join(runs_dir, f"repro_{stamp}.ps1")
    sh = ["#!/usr/bin/env bash",
          "# Auto-generated. Reruns only failing cases.",
          "set -u"]
    ps = ["# Auto-generated. Reruns only failing cases."]
    for r in fails:
        key = r.get("bkey") or r["case"].split("-")[0]
        sd  = r["seed"]
        # try scenario-name lookup; fall back to key (works for X/E/R)
        cmd = f"python headless.py --scenario {key} --seed {sd}"
        sh.append(f'echo "== {r["case"]} =="; {cmd} || true')
        ps.append(f'Write-Host "== {r["case"]} =="; {cmd}')
    with open(sh_path, "w") as f:
        f.write("\n".join(sh) + "\n")
    os.chmod(sh_path, 0o755)
    with open(ps_path, "w") as f:
        f.write("\n".join(ps) + "\n")
    return sh_path, ps_path


# ---------------------------------------------------------------------------
# HTML report
# ---------------------------------------------------------------------------
_HTML_CSS = """
body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
     margin:20px;background:#0f1720;color:#e6edf3}
h1{margin:0 0 4px 0;font-size:22px}
h2{margin-top:28px;border-bottom:1px solid #30363d;padding-bottom:4px;font-size:16px}
.muted{color:#7d8590}
.banner{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px 18px;margin:12px 0}
.banner .big{font-size:26px;font-weight:600}
table{border-collapse:collapse;width:100%;margin-top:10px;font-size:13px}
th,td{padding:6px 9px;border-bottom:1px solid #21262d;text-align:left;white-space:nowrap}
th{cursor:pointer;background:#161b22;position:sticky;top:0}
tr:hover{background:#161b22}
.pass{color:#3fb950;font-weight:600}
.int {color:#d29922;font-weight:600}
.fail{color:#f85149;font-weight:600}
.err {color:#d2a8ff;font-weight:600}
.sev-CORE          {color:#58a6ff}
.sev-HARD          {color:#d29922}
.sev-EXTREME       {color:#f85149}
.sev-EXPECTED-HARD {color:#8b949e}
.tag{background:#21262d;border-radius:6px;padding:1px 6px;margin-right:3px;
     font-size:11px;color:#c9d1d9}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px}
.card .n{font-size:22px;font-weight:600}
a{color:#58a6ff}
"""

_HTML_JS = """
document.querySelectorAll('th').forEach((th,i)=>{
  th.addEventListener('click',()=>{
    const t=th.closest('table');
    const rows=[...t.tBodies[0].rows];
    const dir=th.dataset.d==='asc'?-1:1; th.dataset.d=dir===1?'asc':'desc';
    rows.sort((a,b)=>{const x=a.cells[i].innerText,y=b.cells[i].innerText;
      const nx=parseFloat(x),ny=parseFloat(y);
      if(!isNaN(nx)&&!isNaN(ny))return (nx-ny)*dir;
      return x.localeCompare(y)*dir;});
    rows.forEach(r=>t.tBodies[0].appendChild(r));
  });
});
"""

def _html_escape(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
                   .replace(">", "&gt;").replace('"', "&quot;"))

def write_html_report(results, family, summary, path):
    def cls(v):
        return {"STRICT-PASS":"pass","INTERMITTENT-PASS":"int",
                "FAIL":"fail","ERROR":"err"}.get(v,"")
    total = len(results)
    sp, ip, fl, er = summary["strict"], summary["intermittent"], summary["fail"], summary["error"]
    pct = 100.0 * (sp + ip) / total if total else 0.0
    ok = (fl == 0 and er == 0)

    parts = []
    parts.append("<!doctype html><html><head><meta charset='utf-8'>")
    parts.append(f"<title>headless report {summary['stamp']}</title>")
    parts.append(f"<style>{_HTML_CSS}</style></head><body>")
    parts.append(f"<h1>Headless PAT report <span class='muted'>"
                 f"{_html_escape(summary['stamp'])}</span></h1>")
    parts.append(f"<div class='banner'><div class='big'>{sp+ip}/{total} "
                 f"passed ({pct:.1f}%)</div><div class='muted'>"
                 f"{sp} strict &middot; {ip} intermittent &middot; "
                 f"{fl} fail &middot; {er} error &middot; "
                 f"wall {summary['wall_s']}s</div>")
    if summary.get("final"):
        col = "#3fb950" if ok else "#f85149"
        parts.append(f"<div style='margin-top:8px;color:{col};font-weight:600'>"
                     f"{_html_escape(summary['final'])}</div>")
    parts.append("</div>")

    # leaderboard cards
    tracking = [r for r in results if r.get("frames")]
    if tracking:
        best = max(tracking, key=lambda r: r.get("lock_pct", 0))
        worst = min(tracking, key=lambda r: r.get("lock_pct", 0))
        parts.append("<h2>Highlights</h2><div class='grid'>")
        parts.append(f"<div class='card'><div class='muted'>Best lock</div>"
                     f"<div class='n pass'>{best['lock_pct']:.1f}%</div>"
                     f"<div class='muted'>{_html_escape(best['case'])}</div></div>")
        parts.append(f"<div class='card'><div class='muted'>Worst lock</div>"
                     f"<div class='n fail'>{worst['lock_pct']:.1f}%</div>"
                     f"<div class='muted'>{_html_escape(worst['case'])}</div></div>")
        parts.append(f"<div class='card'><div class='muted'>Strict passes</div>"
                     f"<div class='n pass'>{sp}</div></div>")
        parts.append(f"<div class='card'><div class='muted'>Failures</div>"
                     f"<div class='n fail'>{fl}</div></div>")
        parts.append("</div>")

    # family table
    parts.append("<h2>Family aggregate</h2><table><thead><tr>"
                 "<th>Family</th><th>Total</th><th>Strict</th><th>Int</th>"
                 "<th>Fail</th><th>Err</th><th>Mean lock</th><th>Worst rmse</th>"
                 "</tr></thead><tbody>")
    for k in sorted(family.keys()):
        d = family[k]
        ml = (sum(d["locks"]) / len(d["locks"])) if d["locks"] else 0.0
        wr = max(d["rmses"]) if d["rmses"] else 0.0
        parts.append(f"<tr><td>{_html_escape(k)}</td><td>{d['total']}</td>"
                     f"<td class='pass'>{d['strict']}</td>"
                     f"<td class='int'>{d['intermittent']}</td>"
                     f"<td class='fail'>{d['fail']}</td>"
                     f"<td class='err'>{d['error']}</td>"
                     f"<td>{ml:.1f}%</td><td>{wr:.2f}</td></tr>")
    parts.append("</tbody></table>")

    # full results
    parts.append("<h2>All cases</h2><table><thead><tr>"
                 "<th>Case</th><th>Seed</th><th>Fr</th><th>Lock%</th><th>RMSE</th>"
                 "<th>P95</th><th>1st</th><th>Valid%</th><th>Loss</th><th>Acq</th>"
                 "<th>Avg ms</th><th>Severity</th><th>Tags</th><th>Benchmark</th>"
                 "<th>Verdict</th><th>Reason</th></tr></thead><tbody>")
    for r in results:
        tags = "".join(f"<span class='tag'>{_html_escape(t)}</span>"
                       for t in r.get("tags", []))
        sev = r.get("severity", "")
        parts.append(
            f"<tr><td>{_html_escape(r['case'])}</td>"
            f"<td>{r['seed']}</td><td>{r['frames']}</td>"
            f"<td>{r['lock_pct']}</td><td>{r['rmse']}</td><td>{r['p95']}</td>"
            f"<td>{r['first_lock']}</td><td>{r['valid_pct']}</td>"
            f"<td>{r['losses']}</td><td>{r['acq']}</td><td>{r['avg_ms']}</td>"
            f"<td class='sev-{_html_escape(sev)}'>{_html_escape(sev)}</td>"
            f"<td>{tags}</td><td>{_html_escape(r.get('benchmark',''))}</td>"
            f"<td class='{cls(r['verdict'])}'>{_html_escape(r['verdict'])}</td>"
            f"<td>{_html_escape(r['reason'])}</td></tr>")
    parts.append("</tbody></table>")
    parts.append(f"<script>{_HTML_JS}</script></body></html>")
    with open(path, "w") as f:
        f.write("".join(parts))


# ---------------------------------------------------------------------------
# Top-level convenience: call once at end of main()
# ---------------------------------------------------------------------------
def report(results, family, summary, prev_payload, runs_dir="runs", write_html=True):
    """Print enriched report and write HTML + repro scripts."""
    print_tldr(results, summary["wall_s"])
    print_severity_summary(results)
    print_tag_summary(results)
    print_leaderboards(results)
    print_failure_buckets(results)
    print_regression_diff(prev_payload, results)

    stamp = summary["stamp"]
    sh, ps = write_repro_scripts(results, stamp, runs_dir=runs_dir)
    if sh:
        print(c(f"\nRepro scripts -> {sh} + {ps}", C.B_CYAN))

    if not write_html:
        return None
    html = os.path.join(runs_dir, f"headless_{stamp}.html")
    write_html_report(results, family, summary, html)
    print(c(f"HTML report -> {html}", C.B_CYAN))
    return html