"""研究者/被试双视图 Dashboard（Streamlit）。

    uv pip install streamlit
    streamlit run app/streamlit_app.py

数据来源：`data/reports/state_profile.json`（由 scripts/run_state_demo.py 生成）
纪律：被试视图**不显示任何原始指标**；研究者视图展示全部量化特征与可追溯输入。
"""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="BPlus 状态 Dashboard", layout="wide")

DEFAULT = Path(__file__).resolve().parents[1] / "data" / "reports" / "state_profile.json"
path = st.sidebar.text_input("状态文件", str(DEFAULT))
if not Path(path).exists():
    st.error(f"找不到 {path}；请先运行：`python scripts/run_state_demo.py`")
    st.stop()

data = json.loads(Path(path).read_text(encoding="utf-8"))
profile, features = data["profile"], data.get("features", {})
truth = data.get("synthetic_truth", {})

view = st.sidebar.radio("视图", ["被试视图（Participant）", "研究者视图（Research）"])
st.title("BPlus 多模态状态评估 · Dashboard")
st.caption(f"参与者 {profile.get('participant_id')} · 会话 {profile.get('session_id')} · {data.get('note','')}")

if view.startswith("被试"):
    st.info("本视图仅显示状态、置信度与数据质量；不包含任何原始研究指标。")
    for layer, title in (("task_state", "第 1 页 · 任务状态"), ("brain_state", "第 2 页 · 脑功能状态"),
                         ("clinical_state", "第 3 页 · 临床／心理状态")):
        st.subheader(title)
        st.table([{"项目": v["zh"], "状态": v["level_zh"], "置信度": v["confidence"]}
                  for v in profile[layer].values()])
    st.subheader("第 4 页 · 综合状态画像")
    integ = profile["integrated"]
    st.metric("综合状态", integ["level_zh"], f"score {integ['score']:.3f}")
    st.caption(integ["note"])
    st.write(f"数据质量：{(profile.get('data_quality') or {}).get('band')} · "
             f"整体置信度：{profile['confidence_overall']['label_zh']}")
    st.caption(profile["confidence_overall"]["note"])
else:
    dq = profile.get("data_quality") or {}
    c1, c2, c3 = st.columns(3)
    c1.metric("数据质量 DQ", dq.get("score"), dq.get("band"))
    c2.metric("整体置信度", profile["confidence_overall"]["label"])
    c3.metric("综合分数", f"{integ['score']:.3f}" if (integ := profile["integrated"]) else "—")
    st.subheader("DQ 分项")
    st.table([{"模态": k, "分数": (v or {}).get("score"), "等级": (v or {}).get("label")}
              for k, v in (dq.get("components") or {}).items() if isinstance(v, dict)])
    st.subheader("三层状态与可追溯输入")
    for layer in ("task_state", "brain_state", "clinical_state"):
        st.markdown(f"**{layer}**")
        st.dataframe([{"状态": v["zh"], "分数": v["score"], "等级": v["level"],
                       "置信度": v["confidence"], "证据状态": v["evidence_status"],
                       "输入": "; ".join(f"{i['metric']}={i['value']}" for i in v["inputs"])}
                      for v in profile[layer].values()], use_container_width=True)
    st.subheader("量化特征")
    flat = {f"{g}.{k}": v for g, vals in features.items() if isinstance(vals, dict)
            for k, v in vals.items() if isinstance(v, (int, float))}
    st.dataframe([{"指标": k, "值": v} for k, v in flat.items()], use_container_width=True)
    if truth:
        st.subheader("合成真值（仅 DEMO）")
        st.json(truth)
