"""被试报告（4 页）与研究者报告 —— 严格的可见性分离（§36、§49-51）。

铁律：**被试报告中不得出现任何原始研究指标**（μV、μM、r、p、SHAP、概率、d′…）。
`PARTICIPANT_FORBIDDEN_TOKENS` + `assert_participant_clean()` 把这条纪律变成可测试的断言。
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

# 被试端**硬禁止**：原始指标与单位（§36 的核心）
PARTICIPANT_FORBIDDEN_TOKENS = [
    "μV", "uV", "µV", "μM", "uM", "HbO", "HbR", "SHAP", "d′", "d'", "SCI", "SDNN",
    "z-score", "置信区间", "分位数", "r =", "r=", "p =", "p=",
]
# 数值 + 单位 的通用模式（防止"3.2 μV"这类泄露）
RAW_VALUE_PATTERN = r"\d+(?:\.\d+)?\s*(?:μV|µV|uV|μM|uM|ms|Hz|%|SD)"

# 被试端**软提醒**：技术术语。允许出现在"不是诊断概率"这类必要的解释句里，
# 但出现次数会被记录，供报告审阅者人工检查（不直接判失败）。
PARTICIPANT_SOFT_TOKENS = ["MMN", "EEG", "fNIRS", "NVC", "GLM", "SHAP", "概率", "眼动仪", "d′"]

LAYER_TITLES = {
    "task_state": ("Task State", "TASK STATE"),
    "brain_state": ("Brain Functional State", "BRAIN FUNCTIONAL STATE"),
    "clinical_state": ("Clinical / Psychological State", "CLINICAL / PSYCHOLOGICAL STATE"),
}
EXPLAIN = {
    "task_state": "This page describes task-performance status in this session, based on key responses and physiological changes during the tasks.",
    "brain_state": "This page describes overall characteristics of brain activity during this session. These are research measures, not a diagnosis.",
    "clinical_state": "This page is based on questionnaires and clinical interviews and is interpreted by clinical staff; the system does not make automatic judgments.",
    "integrated": "This page combines the three sections above and reports data quality and confidence.",
}

STATE_NAMES = {
    "cognitive_load": "Cognitive load", "attention": "Attention stability",
    "emotional_arousal": "Emotional arousal", "task_adaptation": "Task adaptation",
    "recovery": "Recovery", "pfc_activity": "Prefrontal functional activity",
    "executive_control": "Executive-control load", "sensory_processing": "Sensory processing",
    "emotion_processing": "Emotion processing", "eeg_fnirs_coordination": "EEG-fNIRS coordination",
    "brain_recovery": "Brain functional recovery", "depressive_symptoms": "Depressive symptoms",
    "anxiety_symptoms": "Anxiety symptoms", "sleep_concerns": "Sleep-related difficulties",
    "social_functioning": "Social functioning",
}


def assert_participant_clean(text: str) -> None:
    """被试报告的硬性守卫：不得出现任何原始指标或"数值+单位"。"""
    import re

    hits = [t for t in PARTICIPANT_FORBIDDEN_TOKENS if t in text]
    if re.search(RAW_VALUE_PATTERN, text):
        hits.append("数值+单位")
    if hits:
        raise AssertionError(f"被试报告泄露研究侧指标：{sorted(set(hits))}")


def participant_soft_warnings(text: str) -> list[str]:
    """返回被试报告里出现的软提醒术语（供人工审阅；不阻断出报告）。"""
    return sorted({t for t in PARTICIPANT_SOFT_TOKENS if t in text})


def render_participant_pages(profile: dict) -> list[dict]:
    """生成 4 页被试报告（纯状态 + 置信度 + 数据质量 + 解释）。"""
    pages = []
    dq = profile.get("data_quality") or {}
    conf = profile.get("confidence_overall") or {}
    for layer in ("task_state", "brain_state", "clinical_state"):
        title_zh, title_en = LAYER_TITLES[layer]
        rows = [{"name": STATE_NAMES.get(v.get("key", ""), v.get("name_en") or v.get("label_en") or v.get("key", "")),
                 "level": v.get("level", ""), "confidence": _conf_zh(v["confidence"])}
                for v in (profile.get(layer) or {}).values()]
        pages.append({
            "page": len(pages) + 1, "title_zh": title_zh, "title_en": title_en,
            "rows": rows, "explain": EXPLAIN[layer],
            "data_quality": dq.get("band") or dq.get("band_zh"),
            "confidence_note": conf.get("note", ""),
        })
    integ = profile.get("integrated") or {}
    pages.append({
        "page": 4, "title_zh": "Integrated State Profile", "title_en": "INTEGRATED STATE PROFILE",
        "rows": [{"name": "Integrated status", "level": integ.get("level", integ.get("level_zh", "")),
                  "confidence": _conf_zh(conf.get("label_zh") or conf.get("label"))}],
        "explain": EXPLAIN["integrated"],
        "data_quality": dq.get("band") or dq.get("band_zh"),
        "confidence_note": conf.get("note", ""),
    })
    return pages


def _conf_zh(label: str | None) -> str:
    return label or ""


def render_partner_markdown(profile: dict) -> str:            # 兼容旧命名
    return render_participant_markdown(profile)


def render_participant_markdown(profile: dict) -> str:
    lines = [f"# Participant Status Report", "",
             f"- Participant: {profile.get('participant_id','—')}  Session: {profile.get('session_id','—')}", ""]
    for page in render_participant_pages(profile):
        lines += [f"## Page {page['page']} · {page['title_zh']}", ""]
        lines += ["| Measure | Status | Confidence |", "| --- | --- | --- |"]
        lines += [f"| {r['name']} | {r['level']} | {r['confidence']} |" for r in page["rows"]]
        lines += ["", f"> {page['explain']}", f"> Data quality: {page['data_quality']}", ""]
        if page.get("confidence_note"):
            lines += [f"> {page['confidence_note']}", ""]
    text = "\n".join(lines)
    assert_participant_clean(text)
    return text


def render_researcher_markdown(profile: dict, features: dict | None = None) -> str:
    lines = ["# Researcher Report (RESEARCH ONLY)", "",
             f"- Participant: {profile.get('participant_id','—')}  Session: {profile.get('session_id','—')}",
             f"- Data quality: {(profile.get('data_quality') or {}).get('score')} "
             f"({(profile.get('data_quality') or {}).get('band')})",
             f"- Overall confidence: {(profile.get('confidence_overall') or {}).get('label')}", ""]
    for layer in ("task_state", "brain_state", "clinical_state"):
        title_zh, title_en = LAYER_TITLES[layer]
        lines += [f"## {title_zh} / {title_en}", "",
                  "| Status | Score | Level | Confidence | Evidence status | Input measures |", "| --- | --- | --- | --- | --- | --- |"]
        for v in (profile.get(layer) or {}).values():
            inputs = "; ".join(f"{i['metric']}={i['value']:.3g}(w={i['weight']})" for i in v["inputs"]) or "—"
            lines.append(f"| {STATE_NAMES.get(v.get('key',''), v.get('name_en') or v.get('label_en') or v.get('key',''))} | {v['score']:.3f} | {v['level']} | {v['confidence']} | "
                         f"{v['evidence_status']} | {inputs} |")
        lines.append("")
    integ = profile.get("integrated") or {}
    lines += ["## Integrated Profile", "",
              f"- Integrated score: {integ.get('score')} ({integ.get('level')})",
              f"- Layer scores: {integ.get('layer_scores')}",
              f"- Weights: {integ.get('weights')}", ""]
    if features:
        lines += ["## Quantitative Features (RESEARCH ONLY)", "", "| Measure | Value |", "| --- | --- |"]
        for group, vals in features.items():
            if isinstance(vals, dict):
                for k, v in vals.items():
                    if isinstance(v, (int, float)):
                        lines.append(f"| {group}.{k} | {v:.4g} |")
        lines.append("")
    return "\n".join(lines)


def to_html(profile: dict, features: dict | None = None, *, title: str = "BPlus Status Report") -> str:
    """自包含 HTML（内联 CSS，无外部依赖）：上层被试 4 页 + 下层研究者附录。"""
    css = """body{font:15px/1.7 -apple-system,"PingFang SC",sans-serif;margin:0;background:#f7f8fa;color:#1a1a1a}
.wrap{max-width:920px;margin:0 auto;padding:28px}.card{background:#fff;border-radius:14px;padding:22px;margin:16px 0;
box-shadow:0 1px 3px rgba(0,0,0,.06)}h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:20px 0 10px}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #eee;padding:8px 10px;text-align:left;font-size:14px}
.pill{display:inline-block;padding:2px 10px;border-radius:999px;background:#eef2ff;color:#2f4bd4;font-size:13px}
.muted{color:#666;font-size:13px}details{margin-top:14px}summary{cursor:pointer;color:#2f4bd4}"""
    pages = render_participant_pages(profile)
    body = [f'<div class="wrap"><h1>{escape(title)}</h1>',
            f'<p class="muted">Participant {escape(str(profile.get("participant_id","—")))} · Session '
            f'{escape(str(profile.get("session_id","—")))}</p>']
    for page in pages:
        rows = "".join(f"<tr><td>{escape(r['name'])}</td><td><span class='pill'>{escape(r['level'])}</span></td>"
                       f"<td>{escape(r['confidence'])}</td></tr>" for r in page["rows"])
        body.append(f"""<div class="card"><h2>Page {page['page']} · {escape(page['title_zh'])}</h2>
<table><tr><th>Measure</th><th>Status</th><th>Confidence</th></tr>{rows}</table>
<p class="muted">{escape(page['explain'])}</p>
<p class="muted">Data quality: {escape(str(page['data_quality']))}</p></div>""")
    if features is not None:
        body.append('<div class="card"><details><summary>Researcher Appendix (RESEARCH ONLY — DO NOT SHOW TO PARTICIPANTS)</summary>'
                    + _md_tables_to_html(render_researcher_markdown(profile, features)) + "</details></div>")
    body.append("</div>")
    return f"<!doctype html><html lang='en'><meta charset='utf-8'><style>{css}</style><body>{''.join(body)}</body></html>"


def _md_tables_to_html(md: str) -> str:
    out, in_table = [], False
    for line in md.splitlines():
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            tag = "th" if not in_table else "td"
            out.append("<tr>" + "".join(f"<{tag}>{escape(c)}</{tag}>" for c in cells) + "</tr>")
            in_table = True
        else:
            if in_table:
                out.append("</table>")
                in_table = False
            if line.startswith("## "):
                out.append(f"<h3>{escape(line[3:])}</h3>")
            elif line.startswith("# "):
                out.append(f"<h2>{escape(line[2:])}</h2>")
            elif line.strip():
                out.append(f"<p>{escape(line)}</p>")
            if line.startswith("|") is False and len(out) and out[-1].startswith("<table") is False and in_table is False:
                pass
    if in_table:
        out.append("</table>")
    txt = "".join(out)
    # 把连续 <tr> 包进表格
    return txt.replace("<tr>", "<table><tr>", 1).replace("</table>", "</table>", 1) if "<tr>" in txt and "<table>" not in txt else txt
