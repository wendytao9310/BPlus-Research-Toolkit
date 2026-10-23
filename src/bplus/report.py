"""Command-line entry point for BPlus v2.7 participant reports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .reports import generate_multimodal_report, generate_session_report


def _plain(value: str, prefix: str) -> str:
    return value[len(prefix):] if value.startswith(prefix) else value


def generate_report(subject: str, session: str, *, root: str | Path = ".") -> Path:
    project = Path(root).resolve()
    participant_id = _plain(subject, "sub-")
    session_id = _plain(session, "ses-")
    analysis = project / "data" / "analysis" / f"sub-{participant_id}_ses-{session_id}_analysis.json"
    if analysis.exists():
        return generate_multimodal_report(
            analysis, project / "data" / "reports" / "multimodal", require_review=True)["html"]
    session_dir = project / "data" / "session"
    paradigms = []
    prefix = f"sub-{participant_id}_ses-{session_id}_"
    suffix = "_behavior.csv"
    for path in sorted(session_dir.glob(f"{prefix}*{suffix}")):
        name = path.name[len(prefix):-len(suffix)]
        if name and name not in paradigms:
            paradigms.append(name)
    if not paradigms:
        raise FileNotFoundError(f"未找到 sub-{participant_id} ses-{session_id} 的分析包或行为记录")
    metadata_path = session_dir / f"sub-{participant_id}_ses-{session_id}_metadata.json"
    age = None
    if metadata_path.exists():
        age = json.loads(metadata_path.read_text(encoding="utf-8")).get("age")
    return generate_session_report(session_dir, project / "data" / "reports",
                                   participant_id=participant_id, session_id=session_id,
                                   paradigms=paradigms, age=age)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m bplus.report")
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate", help="生成 v2.7 被试报告")
    generate.add_argument("--subject", required=True)
    generate.add_argument("--session", required=True)
    generate.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    path = generate_report(args.subject, args.session, root=args.root)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
