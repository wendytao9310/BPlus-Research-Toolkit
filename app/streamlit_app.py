"""Researcher and participant views for a generated BPlus state profile."""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

DEFAULT = Path("data/reports/state_profile.json")
st.set_page_config(page_title="BPlus Status Dashboard", layout="wide")
path = Path(st.sidebar.text_input("State-profile file", str(DEFAULT)))
if not path.exists():
    st.error(f"Cannot find {path}. Run `python scripts/run_state_demo.py` first.")
    st.stop()

data = json.loads(path.read_text(encoding="utf-8"))
profile = data.get("profile", data)
view = st.sidebar.radio("View", ["Participant view", "Researcher view"])
st.title("BPlus Multimodal Status Dashboard")
st.caption(f"Participant {profile.get('participant_id')} · Session {profile.get('session_id')} · {data.get('note', '')}")

if view == "Participant view":
    st.info("This view shows status, confidence, and data quality only; it contains no raw research metrics.")
    for layer, title in (("task_state", "Page 1 · Task State"),
                         ("brain_state", "Page 2 · Brain Functional State"),
                         ("clinical_state", "Page 3 · Clinical / Psychological State")):
        st.subheader(title)
        st.table([{"Item": value.get("name_en") or value.get("zh") or key,
                   "Status": value.get("level") or value.get("level_zh"),
                   "Confidence": value.get("confidence")}
                  for key, value in profile.get(layer, {}).items()])
    st.subheader("Page 4 · Integrated Profile")
    integrated = profile.get("integrated") or {}
    st.metric("Integrated status", integrated.get("level", "Insufficient data"),
              f"score {integrated.get('score', 0):.3f}")
    st.write(f"Data quality: {(profile.get('data_quality') or {}).get('band')} · "
             f"Overall confidence: {(profile.get('confidence_overall') or {}).get('label')}")
else:
    quality = profile.get("data_quality") or {}
    integrated = profile.get("integrated") or {}
    col1, col2, col3 = st.columns(3)
    col1.metric("Data quality (DQ)", quality.get("score"), quality.get("band"))
    col2.metric("Overall confidence", (profile.get("confidence_overall") or {}).get("label"))
    col3.metric("Integrated score", f"{integrated.get('score', 0):.3f}")
    st.subheader("DQ components")
    st.table([{"Modality": key, "Score": (value or {}).get("score"), "Grade": (value or {}).get("label")}
              for key, value in (quality.get("components") or {}).items()])
    st.subheader("Three-layer status and traceable inputs")
    for layer in ("task_state", "brain_state", "clinical_state"):
        st.markdown(f"### {layer.replace('_', ' ').title()}")
        st.dataframe([{"Status": value.get("name_en") or value.get("zh") or key,
                       "Score": value.get("score"), "Level": value.get("level"),
                       "Confidence": value.get("confidence"),
                       "Evidence status": value.get("evidence_status"),
                       "Inputs": "; ".join(f"{item['metric']}={item['value']}" for item in value.get("inputs", []))}
                      for key, value in profile.get(layer, {}).items()], use_container_width=True)
    st.subheader("Quantitative features")
    flat = data.get("features_flat") or {}
    st.dataframe([{"Metric": key, "Value": value} for key, value in flat.items()], use_container_width=True)
    if data.get("truth"):
        st.subheader("Synthetic truth (DEMO only)")
        st.json(data["truth"])

