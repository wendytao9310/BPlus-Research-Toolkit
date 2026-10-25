#!/usr/bin/env python
"""Grace-friendly BPlus launcher. Uses only the Python standard-library GUI."""
from __future__ import annotations

import queue
import csv
import json
import os
import sys
import threading
import traceback
import webbrowser
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
_default_work_root = Path.home() / "Library" / "Application Support" / "BPlus Research Toolkit"
WORK_ROOT = (Path(os.environ.get("BPLUS_USER_DATA_DIR", _default_work_root)) if FROZEN else ROOT)
DATA_ROOT = WORK_ROOT / "data"
DATA_ROOT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("BPLUS_CONFIG_DIR", str(ROOT / "configs"))
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "src"))

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from bplus.gui import run_session
from bplus.analysis import (analyze_mmn_epochs, analyze_vft_hbo, build_analysis_package,
                            read_vft_scoring, review_package, write_vft_scoring_template)
from bplus.preflight import run_preflight
from bplus.reports import generate_multimodal_report, generate_session_report
from bplus.fnirs import (ShimadzuFolderImporter, analyze_interview,
                         build_fnirs_analysis_package, export_report_pdf, write_analysis_outputs)
from bplus.eeg import (analyze_cgx_brainvision, read_curry_metadata, run_mmn_simulation,
                       write_cgx_outputs)
from bplus.clinical import apply_clinical_assessment
from bplus.behavior_export import export_all_behavior_sessions, export_behavior_session
from bplus.multimodal_merge import (build_behavior_analysis_package, discover_analysis_packages,
                                    merge_analysis_packages, write_behavior_analysis_package,
                                    write_integrated_package)
from bplus.import_session import (load_import_session, manifest_path, run_unified_analysis,
                                  stage_file, stage_folder, summarize_import_session)

PARADIGMS = ["rest", "mmn", "vft", "nback", "emotion"]


class Launcher(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("BPlus Multimodal Experiment System")
        self.geometry("1180x780")
        self.minsize(1040, 720)
        self.participant = tk.StringVar(value="TEST001")
        self.session = tk.StringVar(value="1")
        self.operator = tk.StringVar(value="Grace")
        self.age = tk.StringVar(value="")
        self.mode = tk.StringVar(value="VISUAL_DEMO")
        self.backend = tk.StringVar(value="simulated")
        self.latest_report: Path | None = None
        self.analysis_parts: dict[str, object] = {"mmn": None, "vft": None, "vft_scoring": None}
        # Start with one short, low-risk paradigm. Operators can explicitly add
        # others after the first successful visual smoke test.
        self.selected = {name: tk.BooleanVar(value=name == "rest") for name in PARADIGMS}
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self._build()
        self.after(150, self._poll)

    def _build(self) -> None:
        colors = {"bg": "#f3f6fa", "surface": "#ffffff", "navy": "#17365d",
                  "blue": "#246bce", "blue_hover": "#1c58ac", "text": "#172230",
                  "muted": "#667587", "line": "#dbe3ed", "soft": "#edf4ff"}
        self.configure(background=colors["bg"])

        def label(parent, text, *, size=12, weight="normal", color=None, **kwargs):
            return tk.Label(parent, text=text, font=("Arial", size, weight),
                            fg=color or colors["text"], bg=parent.cget("bg"), **kwargs)

        def button(parent, text, command, *, primary=False, width=22):
            # macOS Aqua may ignore a Tk button's custom background while still
            # honoring its foreground. Keep primary text dark-blue so it stays
            # legible on both Aqua and non-macOS themes.
            bg = colors["soft"] if primary else colors["surface"]
            fg = "#0d4f9d" if primary else colors["navy"]
            return tk.Button(parent, text=text, command=command, width=width,
                             font=("Arial", 11, "bold" if primary else "normal"),
                             fg=fg, bg=bg, activeforeground=fg,
                             activebackground="#dceaff" if primary else colors["soft"],
                             relief="flat", bd=0, highlightthickness=1,
                             highlightbackground=colors["blue"] if primary else colors["line"],
                             padx=12, pady=9, cursor="pointinghand")

        def card(parent):
            return tk.Frame(parent, bg=colors["surface"], highlightthickness=1,
                            highlightbackground=colors["line"], padx=18, pady=16)

        header = tk.Frame(self, bg=colors["navy"], height=92, padx=30, pady=18)
        header.pack(fill="x"); header.pack_propagate(False)
        brand = tk.Frame(header, bg=colors["navy"]); brand.pack(side="left", fill="y")
        label(brand, "BPlus", size=23, weight="bold", color="white").pack(anchor="w")
        label(brand, "Multimodal Experiment and Research Report Platform", size=11,
              color="#cbd8e7").pack(anchor="w", pady=(2, 0))
        status = tk.Frame(header, bg="#24486f", padx=12, pady=7); status.pack(side="right", pady=9)
        label(status, "RESEARCH MODE  ·  NOT FOR CLINICAL DIAGNOSIS", size=10, weight="bold",
              color="#e8f1fb").pack()

        body = tk.Frame(self, bg=colors["bg"], padx=26, pady=20); body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, minsize=330)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        left = tk.Frame(body, bg=colors["bg"]); left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        identity = card(left); identity.pack(fill="x", pady=(0, 12))
        label(identity, "Current Session", size=16, weight="bold", color=colors["navy"]).pack(anchor="w")
        label(identity, "All imported files must belong to the same participant and session", size=10,
              color=colors["muted"]).pack(anchor="w", pady=(3, 12))
        fields = (("Participant ID", self.participant), ("Session ID", self.session),
                  ("Age (6–18 years)", self.age), ("Operator / Reviewer", self.operator))
        for row, (field_name, variable) in enumerate(fields):
            label(identity, field_name, size=10, weight="bold", color=colors["muted"]).pack(anchor="w", pady=(5, 3))
            tk.Entry(identity, textvariable=variable, font=("Arial", 12), relief="flat", bd=0,
                     highlightthickness=1, highlightbackground=colors["line"],
                     highlightcolor=colors["blue"]).pack(fill="x", ipady=7)

        settings = card(left); settings.pack(fill="x")
        label(settings, "Run Settings", size=16, weight="bold", color=colors["navy"]).pack(anchor="w")
        label(settings, "Mode", size=10, weight="bold", color=colors["muted"]).pack(anchor="w", pady=(12, 3))
        mode_grid = tk.Frame(settings, bg=colors["surface"]); mode_grid.pack(fill="x")
        for index, value in enumerate(("DEMO", "VISUAL_DEMO", "PILOT", "REAL")):
            tk.Radiobutton(mode_grid, text=value, value=value, variable=self.mode,
                           bg=colors["surface"], activebackground=colors["surface"],
                           fg=colors["text"], selectcolor=colors["surface"],
                           font=("Arial", 10)).grid(row=index // 2, column=index % 2,
                                                    sticky="w", pady=3, padx=(0, 12))
        label(settings, "Paradigms", size=10, weight="bold", color=colors["muted"]).pack(anchor="w", pady=(12, 3))
        task_labels = {"rest": "Rest  Baseline", "mmn": "MMN  Auditory", "vft": "VFT  Language",
                       "nback": "N-back  Working Memory", "emotion": "Emotion  Affective"}
        task_grid = tk.Frame(settings, bg=colors["surface"]); task_grid.pack(fill="x")
        for index, name in enumerate(PARADIGMS):
            tk.Checkbutton(task_grid, text=task_labels[name], variable=self.selected[name],
                           bg=colors["surface"], activebackground=colors["surface"],
                           selectcolor=colors["surface"], font=("Arial", 10),
                           anchor="w").grid(row=index // 2, column=index % 2,
                                             sticky="w", pady=3, padx=(0, 8))
        task_grid.columnconfigure(0, weight=1); task_grid.columnconfigure(1, weight=1)

        right = tk.Frame(body, bg=colors["bg"]); right.grid(row=0, column=1, sticky="nsew")
        intro = tk.Frame(right, bg=colors["bg"]); intro.pack(fill="x", pady=(0, 12))
        label(intro, "Today's Workflow", size=20, weight="bold", color=colors["navy"]).pack(anchor="w")
        label(intro, "After acquisition, stage each modality first, then analyze everything together and generate one report.",
              size=11, color=colors["muted"]).pack(anchor="w", pady=(3, 0))

        workflow = tk.Frame(right, bg=colors["bg"]); workflow.pack(fill="x")
        steps = [
            ("01", "Run Experiment", "Preflight will run automatically again when the experiment starts.", [
                ("Run Preflight Check", self.preflight, False, 19),
                ("Start Experiment", self.start, True, 18),
                ("View Responses", self.show_responses, False, 17),
            ]),
            ("02", "Import and Unified Analysis", "Import complete EEG, fNIRS, and behavioral packages; importing does not start analysis.", [
                ("Open Multimodal Data Center", self.open_import_center, True, 25),
                ("Add Clinical/Psychological Data", self.open_clinical_entry, False, 22),
            ]),
            ("03", "Review and Export", "Only opens an existing complete report; missing results are never filled automatically.", [
                ("Open Complete Session Report", self.open_latest_report, True, 24),
                ("Export Research Behavioral Data", self.export_behavior_data, False, 22),
            ]),
        ]
        for number, title, description, actions in steps:
            panel = card(workflow); panel.pack(fill="x", pady=(0, 10))
            top = tk.Frame(panel, bg=colors["surface"]); top.pack(fill="x")
            badge = tk.Frame(top, bg=colors["soft"], width=42, height=42)
            badge.pack(side="left", padx=(0, 12)); badge.pack_propagate(False)
            label(badge, number, size=11, weight="bold", color=colors["blue"]).place(relx=.5, rely=.5, anchor="center")
            copy = tk.Frame(top, bg=colors["surface"]); copy.pack(side="left", fill="x", expand=True)
            label(copy, title, size=15, weight="bold", color=colors["navy"]).pack(anchor="w")
            label(copy, description, size=10, color=colors["muted"], wraplength=650,
                  justify="left").pack(anchor="w", pady=(2, 0))
            actions_row = tk.Frame(panel, bg=colors["surface"]); actions_row.pack(fill="x", pady=(12, 0))
            for action_text, command, primary, width in actions:
                control = button(actions_row, action_text, command, primary=primary, width=width)
                control.pack(side="left", padx=(0, 8))
                if action_text == "Start Experiment":
                    self.start_button = control

        utility = tk.Frame(right, bg=colors["bg"]); utility.pack(fill="x", pady=(2, 8))
        button(utility, "System Tools", self.open_advanced_tools, width=14).pack(side="right")
        label(utility, "Legacy migration and system checks are under System Tools.", size=10,
              color=colors["muted"]).pack(side="left", pady=10)

        log_card = card(right); log_card.pack(fill="both", expand=True)
        log_head = tk.Frame(log_card, bg=colors["surface"]); log_head.pack(fill="x")
        label(log_head, "Run Log", size=12, weight="bold", color=colors["navy"]).pack(side="left")
        label(log_head, "Detailed information is retained when errors occur", size=10, color=colors["muted"]).pack(side="right")
        self.log = tk.Text(log_card, height=5, wrap="word", state="disabled", relief="flat",
                           bg="#f8fafc", fg=colors["text"], font=("Menlo", 10), padx=9, pady=7,
                           highlightthickness=1, highlightbackground=colors["line"])
        self.log.pack(fill="both", expand=True, pady=(9, 0))

    def open_latest_report(self) -> None:
        """Open an existing report without silently regenerating a partial one."""
        participant = self.participant.get().strip()
        session = self.session.get().strip()
        candidates: list[Path] = []
        if self.latest_report and self.latest_report.exists():
            candidates.append(self.latest_report)
        preferred = (DATA_ROOT / "reports" / "multimodal" /
                     f"sub-{participant}_ses-{session}" / "report.html")
        if preferred.exists():
            candidates.append(preferred)
        candidates.extend((DATA_ROOT / "reports").glob(
            f"**/sub-{participant}_ses-{session}*_report.html"))
        candidates = [path for path in candidates if path.exists()]
        if not candidates:
            messagebox.showinfo(
                "No Complete Report Found",
                "No generated report was found for this participant and session.\n\n"
                "Open the Multimodal Data Center, import the data packages, then click Run Unified Analysis and Generate Complete Report.")
            return
        report = max(candidates, key=lambda path: path.stat().st_mtime)
        self.latest_report = report
        webbrowser.open(report.as_uri())
        self._write(f"[REPORT OPENED] {report}")

    def open_advanced_tools(self) -> None:
        """Keep legacy/developer routes available without competing with the SOP."""
        dialog = tk.Toplevel(self)
        dialog.title("Advanced / Compatibility Tools")
        dialog.geometry("600x340")
        ttk.Label(dialog, text="System Tools", font=("Arial", 19, "bold")).pack(pady=(20, 5))
        ttk.Label(dialog, text="This section retains only legacy JSON report migration and system checks.\n"
                               "The file-by-file MMN/VFT import workflow is retired and is not used in the current formal experiment.",
                  justify="center").pack(pady=(0, 14))
        actions = ttk.Frame(dialog); actions.pack(fill="both", expand=True, padx=34)
        tools = (
            ("Generate Report from Reviewed JSON Package", self.import_multimodal_report),
            ("Developer: Run Automated Tests", self.tests),
        )
        for row, (label, command) in enumerate(tools):
            ttk.Button(actions, text=label, command=command, style="Action.TButton").grid(
                row=row, column=0, sticky="ew", pady=5)
        actions.columnconfigure(0, weight=1)
        ttk.Button(dialog, text="Close", command=dialog.destroy, style="Quiet.TButton").pack(pady=(8, 18))

    def _write(self, text: str) -> None:
        self.log.configure(state="normal"); self.log.insert("end", text + "\n")
        self.log.see("end"); self.log.configure(state="disabled")
        print(text, flush=True)

    def _selection(self) -> list[str]:
        return [name for name in PARADIGMS if self.selected[name].get()]

    def preflight(self) -> bool:
        selected = self._selection()
        if not selected:
            messagebox.showerror("BPlus", "Select at least one paradigm."); return False
        passed = True
        try:
            for paradigm in selected:
                report = run_preflight(self.participant.get().strip(), self.session.get().strip(),
                                       mode=self.mode.get(), paradigm=paradigm,
                                       out_dir=DATA_ROOT / "session")
                self._write(f"[{report['verdict']}] {paradigm} preflight → {report['path']}")
                passed &= report["verdict"] == "PASS"
        except Exception:
            self._write(traceback.format_exc())
            messagebox.showerror("BPlus", "A preflight error occurred. Details were written to the window and logs/launcher.log.")
            return False
        return passed

    def start(self) -> None:
        if not self.preflight():
            messagebox.showerror("BPlus", "Preflight did not pass. The experiment was not started. Review the log below.")
            return
        self.start_button.configure(state="disabled")
        # Read Tk variables on the Tk main thread. PsychoPy is launched in a
        # separate process for VISUAL_DEMO because macOS requires its window
        # lifecycle to run on that process's main thread.
        age_text = self.age.get().strip()
        if age_text and (not age_text.isdigit() or not 6 <= int(age_text) <= 18):
            messagebox.showerror("BPlus", "Age must be an integer from 6 to 18.")
            self.start_button.configure(state="normal")
            return
        args = (self.mode.get(), self._selection(), self.participant.get().strip(),
                self.session.get().strip(), int(age_text) if age_text else None)
        threading.Thread(target=self._run_selected, args=args, daemon=True).start()

    def _run_selected(self, mode: str, selected: list[str], participant: str, session: str,
                      age: int | None) -> None:
        try:
            dummy = mode in {"DEMO", "PILOT"}
            for paradigm in selected:
                self.events.put(("log", f"[RUNNING] {paradigm}"))
                if mode == "VISUAL_DEMO":
                    import subprocess
                    command = ([sys.executable, "--bplus-run-session", paradigm, participant, session,
                                str(DATA_ROOT / "session")] if FROZEN else
                               [sys.executable, str(ROOT / "scripts" / "run_session.py"),
                                "--paradigm", paradigm, "--participant", participant,
                                "--session", session, "--mode", "VISUAL_DEMO", "--visual-demo",
                                "--out", str(DATA_ROOT / "session")])
                    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
                    if completed.returncode == 130:
                        self.events.put(("aborted", completed.stdout.strip()))
                        return
                    if completed.returncode:
                        raise RuntimeError(completed.stderr or completed.stdout)
                    self.events.put(("log", completed.stdout.strip()))
                else:
                    result = run_session(paradigm, participant, session, DATA_ROOT / "session",
                                         dummy=dummy, mode=mode, pilot_staff=(mode == "PILOT"))
                    self.events.put(("log", f"[PASS] {paradigm}: {result.behavior_log}"))
            report = generate_session_report(DATA_ROOT / "session", DATA_ROOT / "reports",
                                             participant_id=participant, session_id=session,
                                             paradigms=selected, age=age)
            self.events.put(("report", str(report)))
            self.events.put(("done", "Session completed successfully"))
        except Exception:
            self.events.put(("error", traceback.format_exc()))

    def tests(self) -> None:
        if FROZEN:
            messagebox.showinfo("Developer Tests", "Developer tests are run in the source distribution and are not bundled into the standalone app.")
            return
        import subprocess
        result = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT,
                                capture_output=True, text=True)
        self._write(result.stdout.strip() or result.stderr.strip())

    def show_responses(self) -> None:
        files = sorted((DATA_ROOT / "session").glob(
            f"sub-{self.participant.get().strip()}_ses-{self.session.get().strip()}_*_behavior.csv"),
            key=lambda path: path.stat().st_mtime, reverse=True)
        if not files:
            messagebox.showinfo("Participant Responses", "No behavioral records were found for this participant and session.")
            return
        dialog = tk.Toplevel(self)
        dialog.title("Participant Response Records")
        dialog.geometry("920x560")
        text = tk.Text(dialog, wrap="none", font=("Menlo", 12))
        text.pack(fill="both", expand=True, padx=12, pady=12)
        for path in files:
            text.insert("end", f"\n=== {path.name} ===\n")
            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            responded = [row for row in rows if row.get("responded") == "1"]
            if not responded:
                text.insert("end", "No keypress or rating response\n")
            for row in responded:
                text.insert("end", f"Trial {row.get('trial_index', '')}  Condition {row.get('condition', '')}  "
                                   f"Key {row.get('key', '')}  RT {row.get('rt_ms', '')} ms  "
                                   f"Pleasantness {row.get('valence', '')}  Arousal {row.get('arousal', '')}\n")
        text.configure(state="disabled")

    def show_report(self) -> None:
        try:
            report = generate_session_report(
                DATA_ROOT / "session", DATA_ROOT / "reports",
                participant_id=self.participant.get().strip(), session_id=self.session.get().strip(),
                paradigms=self._selection(),
                age=int(self.age.get()) if self.age.get().strip().isdigit() else None,
            )
            self.latest_report = report
            webbrowser.open(report.as_uri())
            self._write(f"[REPORT] {report}")
        except Exception:
            self._write(traceback.format_exc())
            messagebox.showerror("BPlus", "Report generation failed. Detailed errors are shown at the bottom of the window.")

    def import_multimodal_report(self) -> None:
        package = filedialog.askopenfilename(
            title="Select a BPlus Multimodal Analysis Package",
            filetypes=[("JSON analysis package", "*.json")],
        )
        if not package:
            return
        try:
            paths = generate_multimodal_report(package, DATA_ROOT / "reports" / "multimodal",
                                               require_review=True)
            self.latest_report = paths["html"]
            webbrowser.open(paths["html"].as_uri())
            self._write(f"[MULTIMODAL REPORT] {paths['html']}")
            messagebox.showinfo("BPlus", "The four-page status report and researcher appendix were generated.")
        except Exception:
            self._write(traceback.format_exc())
            messagebox.showerror("BPlus", "Multimodal report generation failed. Check the input package and the error details below.")

    def open_import_center(self) -> None:
        participant = self.participant.get().strip()
        session = self.session.get().strip()
        if not participant or not session:
            messagebox.showerror("BPlus", "Enter the participant ID and session ID first.")
            return
        dialog = tk.Toplevel(self)
        dialog.title("Multimodal Data Import Center")
        dialog.geometry("960x700")
        ttk.Label(dialog, text="Multimodal Data Import Center", font=("Arial", 20, "bold")).pack(pady=(18, 4))
        ttk.Label(dialog, text=f"Participant {participant} · Session {session}  —  Import complete packages first, then analyze once").pack()
        ttk.Label(dialog, text="Preprocessed MMN results are optional; manual VFT scoring records valid words, repetitions, and invalid words.",
                  foreground="#5f6f82").pack(pady=(4, 0))
        status = tk.Text(dialog, height=16, wrap="word", state="disabled")
        status.pack(fill="both", expand=True, padx=24, pady=12)

        def refresh() -> None:
            manifest = load_import_session(DATA_ROOT / "imports",
                                           participant_id=participant, session_id=session)
            lines = []
            for row in summarize_import_session(manifest):
                if row["modality"] in {"eye", "physiology"}:
                    lines.append(f"{row['label']:<10}  Raw-file parser not yet connected (results will not be fabricated)")
                    continue
                label = "Staged" if row["status"].startswith("STAGED") else "Not imported"
                line = f"{row['label']:<10}  {label:<12}  {row['file_count']} files"
                if row["root"]:
                    line += f"\n    {row['root']}"
                if row["issues"]:
                    line += "\n    Preflight notes: " + "; ".join(row["issues"])
                lines.append(line)
            status.configure(state="normal")
            status.delete("1.0", "end")
            status.insert("end", "\n\n".join(lines))
            status.configure(state="disabled")

        def choose(modality: str) -> None:
            folder = filedialog.askdirectory(title=f"Select the complete {dict(eeg='EEG', fnirs='fNIRS', behavior='behavioral', eye='eye-tracking', physiology='heart-rate/physiology', clinical='clinical/psychological')[modality]} data package",
                                             parent=dialog)
            if not folder:
                return
            try:
                path, entry = stage_folder(DATA_ROOT / "imports", participant_id=participant,
                                           session_id=session, modality=modality, folder=folder)
                self._write(f"[{entry['label']} STAGED] {entry['inventory']['file_count']} files · {path}")
                refresh()
            except Exception as exc:
                messagebox.showerror("Data Package Import Failed", str(exc), parent=dialog)

        def choose_supplement(modality: str) -> None:
            is_mmn = modality == "mmn_epochs"
            selected = filedialog.askopenfilename(
                title="Select the preprocessed MMN epoch file" if is_mmn else "Select the completed VFT manual-scoring sheet",
                filetypes=[("MMN NPZ", "*.npz")] if is_mmn else [("VFT CSV", "*.csv")],
                parent=dialog)
            if not selected:
                return
            try:
                path, entry = stage_file(
                    DATA_ROOT / "imports", participant_id=participant,
                    session_id=session, modality=modality, file=selected)
                self._write(f"[{entry['label']} STAGED] {entry['file']['path']} · {path}")
                refresh()
            except Exception as exc:
                messagebox.showerror("Supplementary File Import Failed", str(exc), parent=dialog)

        def create_vft_template() -> None:
            initial = f"sub-{participant}_ses-{session}_vft_scoring.csv"
            selected = filedialog.asksaveasfilename(
                title="Create a VFT Manual-Scoring Sheet", defaultextension=".csv",
                initialfile=initial, filetypes=[("CSV", "*.csv")], parent=dialog)
            if not selected:
                return
            try:
                write_vft_scoring_template(selected)
                self._write(f"[VFT SCORING SHEET CREATED] {selected}")
                messagebox.showinfo(
                    "VFT Scoring Sheet Created",
                    "Enter each block's word record, valid words, repetitions, invalid words, and reviewer.\n\n"
                    "After saving, click Import Completed VFT Scoring Sheet.", parent=dialog)
            except Exception as exc:
                messagebox.showerror("Could Not Create VFT Scoring Sheet", str(exc), parent=dialog)

        buttons = ttk.Frame(dialog); buttons.pack(fill="x", padx=20)
        choices = (("eeg", "Import Complete EEG Package"), ("fnirs", "Import Complete fNIRS Package"),
                   ("behavior", "Import Behavioral Data Package"))
        for index, (modality, label) in enumerate(choices):
            ttk.Button(buttons, text=label, command=lambda value=modality: choose(value)).grid(
                row=index // 3, column=index % 3, padx=5, pady=4, sticky="ew")
        for column in range(3):
            buttons.columnconfigure(column, weight=1)
        supplements = ttk.LabelFrame(dialog, text="Optional / Manually Supplemented Data")
        supplements.pack(fill="x", padx=24, pady=(10, 2))
        ttk.Button(supplements, text="Import Preprocessed MMN Results (NPZ)",
                   command=lambda: choose_supplement("mmn_epochs")).grid(row=0, column=0, padx=6, pady=8, sticky="ew")
        ttk.Button(supplements, text="Create VFT Manual-Scoring Sheet",
                   command=create_vft_template).grid(row=0, column=1, padx=6, pady=8, sticky="ew")
        ttk.Button(supplements, text="Import Completed VFT Scoring Sheet",
                   command=lambda: choose_supplement("vft_scoring")).grid(row=0, column=2, padx=6, pady=8, sticky="ew")
        for column in range(3):
            supplements.columnconfigure(column, weight=1)
        ttk.Button(dialog, text="Run Unified Analysis and Generate Complete Report",
                   command=lambda: (dialog.destroy(), self.merge_participant_report())).pack(pady=16)
        refresh()

    def merge_participant_report(self) -> None:
        """Analyze every staged modality once, then create one integrated report."""
        participant = self.participant.get().strip()
        session = self.session.get().strip()
        reviewer = self.operator.get().strip()
        try:
            if not participant or not session:
                raise ValueError("Enter the participant ID and session ID first.")
            age_text = self.age.get().strip()
            age = int(age_text) if age_text.isdigit() and 6 <= int(age_text) <= 18 else None
            session_manifest = manifest_path(DATA_ROOT / "imports", participant, session)
            if not session_manifest.exists():
                raise ValueError("No data package has been imported. Open the Multimodal Data Import Center first.")
            manifest = load_import_session(DATA_ROOT / "imports",
                                           participant_id=participant, session_id=session)
            rows = [row for row in summarize_import_session(manifest) if row["status"] != "NOT_STAGED"]
            names = "\n".join(f"• {row['label']}: {row['file_count']} files" for row in rows)
            if not messagebox.askyesno(
                    "Confirm Unified Analysis",
                    f"Participant: {participant}\nSession: {session}\nStaged data:\n\n{names}\n\n"
                    "Batch analysis, quality control, and unified reporting will start now. Continue?"):
                return
            self._write("[UNIFIED ANALYSIS] Analyzing all staged data packages. Please wait…")
            def worker() -> None:
                try:
                    result = run_unified_analysis(session_manifest, project_root=WORK_ROOT,
                                                  reviewer=reviewer, age=age)
                    self.events.put(("unified_done", json.dumps({
                        "report": str(result["report"]), "package": str(result["package"]),
                        "present": result["integrated"]["data_quality"]["components"]["present_modalities"],
                        "missing": result["integrated"]["data_quality"]["components"]["missing_modalities"],
                    }, ensure_ascii=False)))
                except Exception:
                    self.events.put(("unified_error", traceback.format_exc()))
            threading.Thread(target=worker, daemon=True).start()
        except Exception as exc:
            self._write(traceback.format_exc())
            messagebox.showerror("Participant Data Merge Failed", str(exc))

    def import_shimadzu_fnirs(self) -> None:
        folder = filedialog.askdirectory(title="Select the participant's complete fNIRS data package")
        if not folder:
            return
        try:
            participant = self.participant.get().strip()
            session = self.session.get().strip()
            if not participant or not session:
                raise ValueError("Enter the participant ID and session ID first.")
            path, entry = stage_folder(DATA_ROOT / "imports", participant_id=participant,
                                       session_id=session, modality="fnirs", folder=folder)
            self._write(f"[fNIRS STAGED] {entry['inventory']['file_count']} files · {path}")
            messagebox.showinfo("BPlus", "The complete fNIRS package was added to this session.\nIt has not been analyzed and no report has been generated.")
        except Exception as exc:
            self._write(traceback.format_exc())
            code = getattr(exc, "code", "FNIRS_IMPORT_ERROR")
            messagebox.showerror("fNIRS Import Failed", f"{code}\n{exc}")

    def run_eeg_simulation(self) -> None:
        if not messagebox.askyesno(
                "EEG Software Simulation Validation",
                "This function generates a complete synthetic MMN dataset to test the software workflow.\n\n"
                "The result must not be used as real participant data, a research conclusion, or a clinical judgment. Continue?"):
            return
        curry = filedialog.askopenfilename(
            title="Select a CURRY .cdt file (read-only extraction of sampling rate and channel configuration)",
            filetypes=[("CURRY EEG", "*.cdt"), ("All files", "*")],
        )
        if not curry:
            return
        participant = self.participant.get().strip() or "TEST001"
        session = self.session.get().strip() or "1"
        simulation_id = participant if participant.startswith("SIM-") else f"SIM-{participant}"
        self._write("[EEG SIMULATION] Reading CURRY configuration and running the complete MMN software workflow…")

        def worker() -> None:
            try:
                sfreq, channels, metadata = read_curry_metadata(curry)
                output = (DATA_ROOT / "analysis" / "eeg_simulation" /
                          f"sub-{simulation_id}_ses-{session}" / "BPlus_Output")
                paths = run_mmn_simulation(output, participant_id=simulation_id,
                                           session_id=session, sfreq=sfreq,
                                           channel_names=channels, source_metadata=metadata)
                manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
                result = manifest["analysis"]
                summary = {"html": str(paths["html"]), "manifest": str(paths["manifest"]),
                           "amplitude": result["features"]["mmn_amplitude_uv"],
                           "latency": result["features"]["mmn_latency_ms"],
                           "qc": result["qc"]["status"]}
                self.events.put(("eeg_sim_done", json.dumps(summary, ensure_ascii=False)))
            except Exception:
                self.events.put(("eeg_sim_error", traceback.format_exc()))

        threading.Thread(target=worker, daemon=True).start()

    def import_eeg_data(self) -> None:
        folder = filedialog.askdirectory(title="Select the participant's complete EEG data package")
        if not folder:
            return
        participant = self.participant.get().strip()
        session = self.session.get().strip()
        if not participant or not session:
            messagebox.showerror("EEG Import Failed", "Enter the participant ID and session ID first.")
            return
        try:
            path, entry = stage_folder(DATA_ROOT / "imports", participant_id=participant,
                                       session_id=session, modality="eeg", folder=folder)
            self._write(f"[EEG STAGED] {entry['inventory']['file_count']} files · {path}")
            warning = "\nPreflight notes: " + "; ".join(entry["issues"]) if entry["issues"] else ""
            messagebox.showinfo("BPlus", "The complete EEG package was added to this session.\nIt has not been analyzed and no report has been generated." + warning)
        except Exception as exc:
            self._write(traceback.format_exc())
            messagebox.showerror("EEG Import Failed", str(exc))

    def open_clinical_entry(self) -> None:
        participant = self.participant.get().strip()
        session = self.session.get().strip()
        if not participant or not session:
            messagebox.showerror("BPlus", "Enter the participant ID and session ID first.")
            return
        dialog = tk.Toplevel(self); dialog.title("Clinical / Psychological Data Entry")
        dialog.geometry("820x680")
        ttk.Label(dialog, text="Clinical / Psychological Data Entry", font=("Arial", 20, "bold")).pack(pady=(18, 4))
        ttk.Label(dialog, text="A clinician enters the current result and status. The system displays the entry verbatim and does not diagnose automatically.",
                  wraplength=760).pack(pady=(0, 10))
        form = ttk.Frame(dialog); form.pack(fill="both", expand=True, padx=24)
        ttk.Label(form, text="Measure").grid(row=0, column=0, sticky="w", padx=6, pady=5)
        ttk.Label(form, text="Current Result").grid(row=0, column=1, sticky="w", padx=6, pady=5)
        ttk.Label(form, text="Current Status (Clinician Entry)").grid(row=0, column=2, sticky="w", padx=6, pady=5)
        definitions = [
            ("K-SADS Clinical Interview", "k_sads_status", "k_sads_interpretation"),
            ("CDRS-R（17–113）", "cdrs_r_total", "cdrs_r_status"),
            ("CDI（0–54）", "cdi_total", "cdi_status"),
            ("PHQ-9（0–27）", "phq9_total", "phq9_status"),
            ("PHQ-15（0–30）", "phq15_total", "phq15_status"),
            ("SDQ Parent Version (0–40)", "sdq_parent_total", "sdq_parent_status"),
        ]
        variables: dict[str, tk.StringVar] = {}
        existing = {}
        manifest = load_import_session(DATA_ROOT / "imports",
                                       participant_id=participant, session_id=session)
        clinical_entry = (manifest.get("modalities") or {}).get("clinical") or {}
        existing_path = clinical_entry.get("file", {}).get("path")
        if existing_path and Path(existing_path).exists():
            try:
                existing_payload = json.loads(Path(existing_path).read_text(encoding="utf-8"))
                existing = existing_payload.get("assessment") or {}
            except Exception:
                existing = {}
        for row, (label, result_key, state_key) in enumerate(definitions, 1):
            variables[result_key] = tk.StringVar(value=str(existing.get(result_key, "")))
            variables[state_key] = tk.StringVar(value=str(existing.get(state_key, "")))
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=7)
            ttk.Entry(form, textvariable=variables[result_key], width=24).grid(row=row, column=1, sticky="ew", padx=6)
            ttk.Entry(form, textvariable=variables[state_key], width=34).grid(row=row, column=2, sticky="ew", padx=6)
        clinician = tk.StringVar(value=self.operator.get().strip())
        note = tk.StringVar(value="")
        ttk.Label(form, text="Clinician / Assessor").grid(row=7, column=0, sticky="w", padx=6, pady=7)
        ttk.Entry(form, textvariable=clinician).grid(row=7, column=1, columnspan=2, sticky="ew", padx=6)
        ttk.Label(form, text="Assessment Notes").grid(row=8, column=0, sticky="w", padx=6, pady=7)
        ttk.Entry(form, textvariable=note).grid(row=8, column=1, columnspan=2, sticky="ew", padx=6)
        form.columnconfigure(2, weight=1)

        def save() -> None:
            try:
                assessment = {key: variable.get() for key, variable in variables.items()}
                # Validate ranges and required reviewer without creating a report.
                validated = apply_clinical_assessment(
                    {"features": {}, "sources": {}, "analysis": {}}, assessment,
                    clinician=clinician.get(), note=note.get())
                cleaned = validated["features"]["clinical"]
                output = (DATA_ROOT / "imports" / f"sub-{participant}_ses-{session}" /
                          "clinical_assessment.json")
                output.parent.mkdir(parents=True, exist_ok=True)
                payload = {"participant_id": participant, "session_id": session,
                           "assessment": cleaned, "clinician": clinician.get().strip(),
                           "note": note.get().strip()}
                output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                path, _ = stage_file(
                    DATA_ROOT / "imports", participant_id=participant,
                    session_id=session, modality="clinical", file=output)
                self._write(f"[CLINICAL/PSYCHOLOGICAL DATA STAGED] {output} · {path}")
                messagebox.showinfo("Clinical Data Staged",
                                    "The data were added to this session. They have not been analyzed and no separate report was generated.\n\n"
                                    "Click Run Unified Analysis and Generate Complete Report in the Multimodal Data Center.",
                                    parent=dialog)
                dialog.destroy()
            except Exception as exc:
                messagebox.showerror("Clinical Data Save Failed", str(exc), parent=dialog)

        ttk.Button(dialog, text="Confirm and Add to Unified Analysis", command=save).pack(pady=(8, 20))

    def export_behavior_data(self) -> None:
        choice = messagebox.askyesnocancel(
            "Export Behavioral Task Data",
            "Choose the export scope:\n\nYes = current participant and session\nNo = all participant sessions on this computer\nCancel = do not export")
        if choice is None:
            return
        try:
            output = DATA_ROOT / "exports" / "behavior"
            if choice:
                participant = self.participant.get().strip()
                session = self.session.get().strip()
                if not participant or not session:
                    raise ValueError("Enter the participant ID and session ID first.")
                result = export_behavior_session(DATA_ROOT / "session", output,
                                                 participant_id=participant, session_id=session)
                self._write(f"[BEHAVIORAL DATA EXPORTED] {result['zip']}")
                messagebox.showinfo(
                    "Behavioral Data Export Complete",
                    f"Research-analysis data package generated:\n{result['zip']}\n\n"
                    "Includes trial-level CSV, BIDS events.tsv, summary tables, data dictionary, QC, and provenance inventory.")
            else:
                result = export_all_behavior_sessions(DATA_ROOT / "session", output)
                self._write(f"[BATCH BEHAVIORAL EXPORT] {result['n_sessions']} participant sessions → {output}")
                messagebox.showinfo(
                    "Batch Export Complete",
                    f"Exported {result['n_sessions']} participant sessions.\n\nDirectory: {output}\n"
                    f"Cohort summary: {result['cohort_summary']}")
        except Exception as exc:
            self._write(traceback.format_exc())
            messagebox.showerror("Behavioral Data Export Failed", str(exc))

    def open_result_center(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("MMN / VFT Results Center")
        dialog.geometry("760x520")
        ttk.Label(dialog, text="MMN / VFT Results Center", font=("Arial", 20, "bold")).pack(pady=(20, 6))
        ttk.Label(dialog, text="Import analysis data → automated calculation and QC → manual VFT scoring → researcher review → status report",
                  wraplength=700).pack(pady=(0, 14))
        status = tk.Text(dialog, height=11, wrap="word", state="disabled")
        status.pack(fill="both", expand=True, padx=24, pady=8)

        def say(message: str) -> None:
            status.configure(state="normal"); status.insert("end", message + "\n"); status.see("end")
            status.configure(state="disabled")

        def load_mmn() -> None:
            path = filedialog.askopenfilename(title="Select Preprocessed MMN NPZ", filetypes=[("NPZ", "*.npz")])
            if not path:
                return
            try:
                import numpy as np
                with np.load(path, allow_pickle=False) as data:
                    standard_key = "standard_epochs_uv" if "standard_epochs_uv" in data else "standard_epochs"
                    deviant_key = "deviant_epochs_uv" if "deviant_epochs_uv" in data else "deviant_epochs"
                    self.analysis_parts["mmn"] = analyze_mmn_epochs(
                        data[standard_key], data[deviant_key], data["times_ms"],
                        [str(x) for x in data["channel_names"]])
                say(f"[IMPORTED] MMN: {Path(path).name}, QC {self.analysis_parts['mmn']['qc']['status']}")
            except Exception as exc:
                messagebox.showerror("MMN Import Failed", str(exc), parent=dialog)

        def load_vft() -> None:
            path = filedialog.askopenfilename(title="Select VFT HbO NPZ", filetypes=[("NPZ", "*.npz")])
            if not path:
                return
            try:
                import numpy as np
                with np.load(path, allow_pickle=False) as data:
                    self.analysis_parts["vft"] = analyze_vft_hbo(
                        data["hbo"], float(data["fs"]), task_windows=data["task_windows"].tolist(),
                        rest_windows=data["rest_windows"].tolist(),
                        channel_names=[str(x) for x in data["channel_names"]] if "channel_names" in data else None)
                say(f"[IMPORTED] VFT HbO: {Path(path).name}, QC {self.analysis_parts['vft']['qc']['status']}")
            except Exception as exc:
                messagebox.showerror("VFT Import Failed", str(exc), parent=dialog)

        def create_scoring() -> None:
            path = filedialog.asksaveasfilename(title="Save VFT Manual-Scoring Sheet", defaultextension=".csv",
                                                initialfile=f"sub-{self.participant.get()}_ses-{self.session.get()}_vft_scoring.csv")
            if path:
                write_vft_scoring_template(path); say(f"[CREATED] VFT manual-scoring sheet: {path}")

        def load_scoring() -> None:
            path = filedialog.askopenfilename(title="Select Completed VFT Scoring Sheet", filetypes=[("CSV", "*.csv")])
            if not path:
                return
            try:
                self.analysis_parts["vft_scoring"] = read_vft_scoring(path)
                say(f"[IMPORTED] VFT scoring: {self.analysis_parts['vft_scoring']['totals']['valid_words']} valid words")
            except Exception as exc:
                messagebox.showerror("VFT Scoring Import Failed", str(exc), parent=dialog)

        reviewer = tk.StringVar(value=self.operator.get().strip())
        review_row = ttk.Frame(dialog); review_row.pack(fill="x", padx=24, pady=8)
        ttk.Label(review_row, text="Researcher / Reviewer:").pack(side="left")
        ttk.Entry(review_row, textvariable=reviewer, width=24).pack(side="left", padx=6)

        def save_and_report() -> None:
            try:
                age_text = self.age.get().strip()
                if not age_text.isdigit() or not 6 <= int(age_text) <= 18:
                    raise ValueError("An integer age from 6 to 18 is required before generating a formal report.")
                package = build_analysis_package(self.participant.get().strip(), self.session.get().strip(),
                                                 age=int(age_text), **self.analysis_parts)
                qc_ok = package["data_quality"]["band"] == "ACCEPTABLE"
                if not qc_ok:
                    raise ValueError("MMN/VFT data did not pass QC or are incomplete and cannot be approved.")
                package = review_package(package, reviewer=reviewer.get(), decision="APPROVED",
                                         note="Approved after the researcher reviewed data provenance, QC, and scoring in the Results Center")
                folder = DATA_ROOT / "analysis"
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / f"sub-{self.participant.get()}_ses-{self.session.get()}_analysis.json"
                path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
                paths = generate_multimodal_report(path, DATA_ROOT / "reports" / "multimodal",
                                                   require_review=True)
                self.latest_report = paths["html"]
                webbrowser.open(paths["html"].as_uri())
                say(f"[REVIEWED AND GENERATED] {paths['html']}")
            except Exception as exc:
                messagebox.showerror("Formal Status Report Cannot Be Generated", str(exc), parent=dialog)

        buttons = ttk.Frame(dialog); buttons.pack(fill="x", padx=24, pady=(4, 20))
        for label, command in (("1 Import MMN", load_mmn), ("2 Import VFT HbO", load_vft),
                               ("3 Create VFT Scoring Sheet", create_scoring), ("4 Import VFT Scoring", load_scoring),
                               ("5 Review and Generate Report", save_and_report)):
            ttk.Button(buttons, text=label, command=command).pack(side="left", padx=4)

    def _poll(self) -> None:
        try:
            while True:
                kind, text = self.events.get_nowait()
                self._write(text)
                if kind == "done":
                    self.start_button.configure(state="normal")
                    messagebox.showinfo("BPlus", "This experiment session is complete and the status report was generated.\nClick Open Complete Session Report to view it.")
                elif kind == "report":
                    self.latest_report = Path(text)
                    self._write(f"[REPORT] {text}")
                elif kind == "error":
                    self.start_button.configure(state="normal")
                    messagebox.showerror("BPlus", "Run failed. Detailed errors are shown at the bottom of the window and written to logs/launcher.log.")
                elif kind == "aborted":
                    self.start_button.configure(state="normal")
                    messagebox.showinfo("BPlus", "The participant pressed T. This paradigm was stopped safely.")
                elif kind == "eeg_sim_done":
                    result = json.loads(text)
                    self.latest_report = Path(result["html"])
                    webbrowser.open(self.latest_report.as_uri())
                    self._write(f"[EEG SIMULATION PASS] MMN {result['amplitude']:.2f} µV · "
                                f"{result['latency']:.0f} ms · Report {result['html']}")
                    messagebox.showinfo(
                        "EEG Simulation Test Complete",
                        f"QC: {result['qc']}\nMMN: {result['amplitude']:.2f} µV\n"
                        f"Latency: {result['latency']:.0f} ms\n\n"
                        "The software-simulation validation report has been opened. It must not be used as a real participant result.")
                elif kind == "eeg_sim_error":
                    self._write(text)
                    messagebox.showerror("EEG Simulation Test Failed", "Detailed errors are shown at the bottom of the window.")
                elif kind == "eeg_import_done":
                    result = json.loads(text)
                    self.latest_report = Path(result["html"])
                    webbrowser.open(self.latest_report.as_uri())
                    self._write(f"[EEG IMPORT COMPLETE] QC {result['qc']} · {result['sfreq']:.0f} Hz · "
                                f"Usable channels {result['usable']}/{result['total']} · {result['html']}")
                    mmn_text = "Calculated" if result["mmn"] else "Not calculated (event codes cannot yet be mapped unambiguously)"
                    messagebox.showinfo(
                        "EEG Import and Automated Analysis Complete",
                        f"EEG QC: {result['qc']}\nSampling rate: {result['sfreq']:.0f} Hz\n"
                        f"Duration: {result['duration']:.1f} s\nUsable channels: {result['usable']}/{result['total']}\n"
                        f"MMN: {mmn_text}\n\nThe EEG research report has been opened.")
                elif kind == "eeg_import_error":
                    self._write(text)
                    messagebox.showerror("EEG Import Failed", "Detailed errors are shown at the bottom of the window. Confirm that .vhdr, .vmrk, and .eeg are in the same folder.")
                elif kind == "unified_done":
                    result = json.loads(text)
                    self.latest_report = Path(result["report"])
                    webbrowser.open(self.latest_report.as_uri())
                    present = ", ".join(result["present"]) or "None"
                    missing = ", ".join(result["missing"]) or "None"
                    self._write(f"[UNIFIED COMPLETE REPORT] {result['report']}")
                    messagebox.showinfo("Unified Analysis Complete",
                                        f"Analyzed: {present}\nNot imported / not connected: {missing}\n\n"
                                        f"Integrated analysis package: {result['package']}\nReport: {result['report']}")
                elif kind == "unified_error":
                    self._write(text)
                    messagebox.showerror("Unified Analysis Failed", "Detailed reasons are shown at the bottom of the window. Raw data were not modified.")
        except queue.Empty:
            pass
        self.after(150, self._poll)


def _run_frozen_visual_helper(arguments: list[str]) -> int:
    """Run one visual paradigm in a child process of the frozen app."""
    if len(arguments) != 5:
        print("Invalid frozen-session arguments", file=sys.stderr)
        return 2
    _, paradigm, participant, session, output = arguments
    try:
        result = run_session(paradigm, participant, session, output,
                             mode="VISUAL_DEMO", visual_demo=True)
        print(f"[PASS] {paradigm}: {result.behavior_log}")
        return 0
    except KeyboardInterrupt:
        print("The participant stopped the paradigm with T.")
        return 130
    except Exception:
        traceback.print_exc()
        return 1


def _run_frozen_self_test(arguments: list[str]) -> int:
    """Exercise the frozen application without opening experiment windows."""
    if len(arguments) != 2:
        print("Usage: --bplus-self-test OUTPUT_DIRECTORY", file=sys.stderr)
        return 2
    output_root = Path(arguments[1]).expanduser().resolve()
    session_dir = output_root / "session"
    report_dir = output_root / "reports"
    participant = "FROZEN-SMOKE"
    session = "1"
    try:
        for paradigm in PARADIGMS:
            result = run_session(paradigm, participant, session, session_dir,
                                 dummy=True, mode="DEMO")
            print(f"[PASS] {paradigm}: {result.behavior_log}")
        report = generate_session_report(
            session_dir, report_dir, participant_id=participant,
            session_id=session, paradigms=PARADIGMS,
        )
        print(f"[PASS] report: {report}")
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--bplus-run-session":
        raise SystemExit(_run_frozen_visual_helper(sys.argv[1:]))
    if len(sys.argv) > 1 and sys.argv[1] == "--bplus-self-test":
        raise SystemExit(_run_frozen_self_test(sys.argv[1:]))
    Launcher().mainloop()
