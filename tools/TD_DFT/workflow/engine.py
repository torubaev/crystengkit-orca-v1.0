from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import time
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .models import StageRecord, StageStatus, atomic_write_json, file_sha256, method_signature, records_to_dict
from .orca import extract_geometry, generate_input, validate_output, write_states_csv
from .scheduler import STAGE_NAMES, build_chained_script, build_dependency_submit_script, build_slurm_script, dependency_order
from ..td_dft_naming import workflow_calculation_stem


class WorkflowError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class WorkflowEngine:
    """Conservative sequential controller for the principal ORCA workflow."""

    def __init__(self, config, project_dir: str):
        config.validate()
        self.config = config
        self.project = Path(project_dir).expanduser().resolve()
        self.status_path = self.project / "workflow_status.json"
        self.results_dir = self.project / "results"
        self.records: Dict[str, StageRecord] = {}
        self._load_status()

    @property
    def stages(self) -> List[str]:
        return dependency_order(self.config.frequency.enabled)

    def stage_dir(self, stage: str) -> Path:
        return self.project / STAGE_NAMES[stage]

    def stage_input(self, stage: str) -> Path:
        return self.stage_dir(stage) / f"{workflow_calculation_stem(self.config, stage)}.inp"

    def stage_output(self, stage: str) -> Path:
        return self.stage_dir(stage) / f"{workflow_calculation_stem(self.config, stage)}.out"

    def stage_gbw(self, stage: str) -> Path:
        return self.stage_dir(stage) / f"{workflow_calculation_stem(self.config, stage)}.gbw"

    def result_path(self, artifact: str, suffix: str) -> Path:
        base = workflow_calculation_stem(self.config, "absorption").rsplit("_absorption", 1)[0]
        return self.results_dir / f"{base}_{artifact}{suffix}"

    def _load_status(self) -> None:
        if not self.status_path.is_file():
            return
        payload = json.loads(self.status_path.read_text(encoding="utf-8"))
        for stage, value in payload.get("stages", {}).items():
            value["status"] = StageStatus(value.get("status", StageStatus.NOT_STARTED))
            self.records[stage] = StageRecord(**value)

    def _save_status(self) -> None:
        atomic_write_json(self.status_path, {
            "schema_version": 1,
            "system": self.config.system.name,
            "updated_at": _now(),
            "principal_method_signature": method_signature(self.config),
            "stages": records_to_dict(self.records),
        })

    def _record(self, stage: str) -> StageRecord:
        record = self.records.setdefault(stage, StageRecord(stage_id=stage))
        record.input_file = str(self.stage_input(stage))
        record.output_file = str(self.stage_output(stage))
        record.wavefunction_file = str(self.stage_gbw(stage))
        record.method_signature = method_signature(self.config, include_excited_state=stage in {"absorption", "es_opt", "emission"})
        return record

    def _geometry_for(self, stage: str) -> Path:
        if stage == "s0_opt":
            return self.project / "input" / "initial_geometry.xyz"
        if stage in {"s0_freq", "absorption", "es_opt"}:
            return self.stage_dir("s0_opt") / f"{self.config.system.name}_S0_opt.xyz"
        return self.stage_dir("es_opt") / f"{self.config.system.name}_S{self.config.excited_states.target_root}_opt.xyz"

    def _wavefunction_for(self, stage: str) -> Optional[Path]:
        if stage in {"s0_freq", "absorption"}:
            return self.stage_gbw("s0_opt")
        if stage == "es_opt":
            return self.stage_gbw("absorption")
        if stage == "emission":
            return self.stage_gbw("es_opt")
        return None

    def prepare(self) -> None:
        for name in ("input", "templates", "benchmark", "scripts", "scheduler", "results", "logs", "restarts"):
            (self.project / name).mkdir(parents=True, exist_ok=True)
        source = Path(self.config.system.initial_xyz).expanduser()
        if not source.is_absolute():
            source = (Path.cwd() / source).resolve()
        if not source.is_file():
            raise WorkflowError(f"Initial geometry was not found: {source}")
        initial = self.project / "input" / "initial_geometry.xyz"
        if not initial.exists() or file_sha256(initial) != file_sha256(source):
            shutil.copy2(source, initial)
        for stage in self.stages:
            directory = self.stage_dir(stage)
            directory.mkdir(parents=True, exist_ok=True)
            geometry = self._geometry_for(stage)
            wavefunction = self._wavefunction_for(stage)
            relative_geometry = os.path.relpath(geometry, directory).replace("\\", "/")
            relative_gbw = os.path.relpath(wavefunction, directory).replace("\\", "/") if wavefunction else None
            constraint_geometry = geometry if geometry.is_file() else (self.project / "input" / "initial_geometry.xyz")
            expected = generate_input(self.config, stage, relative_geometry, relative_gbw, constraint_geometry)
            target = self.stage_input(stage)
            record = self._record(stage)
            record.geometry_file = str(geometry)
            if target.exists() and target.read_text(encoding="utf-8") != expected:
                if self._validated_completed(stage):
                    raise WorkflowError(f"Refusing to replace input for completed stage {stage}: {target}")
                self._archive_stage_files(stage, "regenerated")
            target.write_text(expected, encoding="utf-8")
        self._save_status()

    def _validated_completed(self, stage: str) -> bool:
        try:
            results = validate_output(self.stage_output(stage), stage, self.config.frequency.imaginary_frequency_threshold_cm1)
            reported_version = str(results.get("orca_version") or "")
            configured_version = str(self.config.orca.version or "")
            if reported_version and configured_version and reported_version != configured_version:
                raise WorkflowError(
                    f"ORCA version mismatch for {stage}: configured {configured_version}, output reports {reported_version}."
                )
            if stage in {"s0_opt", "absorption", "es_opt"} and not self.stage_gbw(stage).is_file():
                raise WorkflowError(f"Required converged wavefunction was not created for {stage}: {self.stage_gbw(stage)}")
            if (
                stage == "s0_freq"
                and results.get("large_imaginary_frequencies_cm1")
                and self.config.frequency.reject_large_imaginary_modes
                and not self.config.frequency.allow_continue_after_large_imaginary
            ):
                return False
            return True
        except Exception:
            return False

    def _archive_stage_files(self, stage: str, reason: str) -> Optional[Path]:
        candidates = [self.stage_input(stage), self.stage_output(stage), self.stage_gbw(stage)]
        existing = [path for path in candidates if path.exists()]
        if not existing:
            return None
        stamp = time.strftime("%Y%m%d-%H%M%S")
        destination = self.project / "restarts" / f"{stamp}_{stage}_{reason}"
        destination.mkdir(parents=True, exist_ok=False)
        for path in existing:
            shutil.copy2(path, destination / path.name)
        return destination

    def _check_dependency(self, stage: str) -> None:
        expected_signature = method_signature(self.config, include_excited_state=stage in {"absorption", "es_opt", "emission"})
        input_text = self.stage_input(stage).read_text(encoding="utf-8")
        match = re.search(r"(?im)^#\s*CrystEngKit method-signature:\s*(.+?)\s*$", input_text)
        actual_signature = match.group(1).strip() if match else ""
        if actual_signature != expected_signature:
            raise WorkflowError(
                f"Method inconsistency detected for {stage}.\nExpected: {expected_signature}\nFound: {actual_signature or '[missing signature]'}"
            )
        directory = self.stage_dir(stage)
        geometry = self._geometry_for(stage)
        wavefunction = self._wavefunction_for(stage)
        expected_text = generate_input(
            self.config,
            stage,
            os.path.relpath(geometry, directory).replace("\\", "/"),
            os.path.relpath(wavefunction, directory).replace("\\", "/") if wavefunction else None,
            geometry if geometry.is_file() else (self.project / "input" / "initial_geometry.xyz"),
        )
        if input_text != expected_text:
            raise WorkflowError(
                f"Input consistency check failed for {stage}. The generated principal input was modified; "
                "place alternative methods in a separate benchmark workflow."
            )
        index = self.stages.index(stage)
        if index == 0:
            return
        predecessor = self.stages[index - 1]
        predecessor_record = self.records.get(predecessor)
        if predecessor_record and predecessor_record.status in {StageStatus.FAILED, StageStatus.NEEDS_REVIEW}:
            raise WorkflowError(
                f"Stage {stage} cannot start: predecessor {predecessor} is {predecessor_record.status.value}."
            )
        if not self._validated_completed(predecessor):
            raise WorkflowError(f"Stage {stage} cannot start: predecessor {predecessor} is not validated as completed.")
        if not geometry.is_file():
            raise WorkflowError(f"Stage {stage} cannot start: required geometry is missing: {geometry}")
        if wavefunction and not wavefunction.is_file():
            raise WorkflowError(f"Stage {stage} cannot start: required wavefunction is missing: {wavefunction}")

    def validate_stage(self, stage: str, exit_code: Optional[int] = None) -> Dict:
        if stage not in self.stages:
            raise WorkflowError(f"Unknown or disabled stage: {stage}")
        record = self._record(stage)
        if exit_code not in (None, 0):
            record.status = StageStatus.FAILED
            record.exit_code = exit_code
            record.finished_at = _now()
            record.message = f"ORCA exited with code {exit_code}."
            self._save_status()
            raise WorkflowError(record.message)
        try:
            results = validate_output(self.stage_output(stage), stage, self.config.frequency.imaginary_frequency_threshold_cm1)
            reported_version = str(results.get("orca_version") or "")
            configured_version = str(self.config.orca.version or "")
            if reported_version and configured_version and reported_version != configured_version:
                raise WorkflowError(
                    f"ORCA version mismatch for {stage}: configured {configured_version}, output reports {reported_version}."
                )
            if stage in {"s0_opt", "absorption", "es_opt"} and not self.stage_gbw(stage).is_file():
                raise WorkflowError(f"Required converged wavefunction was not created for {stage}: {self.stage_gbw(stage)}")
            record.results = results
            record.exit_code = 0 if exit_code is not None else record.exit_code
            record.finished_at = _now()
            if stage == "s0_opt":
                destination = self.stage_dir(stage) / f"{self.config.system.name}_S0_opt.xyz"
                extract_geometry(self.stage_output(stage), destination, "Converged S0 geometry")
                record.geometry_file = str(destination)
            elif stage == "es_opt":
                root = self.config.excited_states.target_root
                destination = self.stage_dir(stage) / f"{self.config.system.name}_S{root}_opt.xyz"
                extract_geometry(self.stage_output(stage), destination, f"Converged S{root} geometry")
                record.geometry_file = str(destination)
                if not any("root" in line.lower() for line in self.stage_output(stage).read_text(encoding="utf-8", errors="replace").splitlines()):
                    record.warnings.append("No explicit root-character history was found; inspect the optimization before publication.")
            elif stage == "absorption":
                write_states_csv(results["states"], self.result_path("absorption-states", ".csv"))
            elif stage == "emission":
                self._write_emission_summary(results)
            if stage == "s0_freq" and results.get("large_imaginary_frequencies_cm1"):
                record.warnings.append("Large imaginary frequencies detected: " + ", ".join(map(str, results["large_imaginary_frequencies_cm1"])))
                if self.config.frequency.reject_large_imaginary_modes and not self.config.frequency.allow_continue_after_large_imaginary:
                    record.status = StageStatus.NEEDS_REVIEW
                    record.message = "Large imaginary frequency blocks automatic continuation."
                    self._save_status()
                    return results
            record.status = StageStatus.COMPLETED
            record.message = "Validated successfully."
            self._save_status()
            return results
        except Exception as exc:
            record.status = StageStatus.FAILED
            record.finished_at = _now()
            record.message = str(exc)
            self._save_status()
            raise

    def run_stage(self, stage: str) -> Dict:
        self._check_dependency(stage)
        record = self._record(stage)
        if self._validated_completed(stage):
            return self.validate_stage(stage)
        if self.stage_output(stage).exists():
            archive = self._archive_stage_files(stage, "failed-or-interrupted")
            record.warnings.append(f"Previous files preserved in {archive}")
            self.prepare()
        executable = Path(self.config.orca.executable).expanduser()
        if not executable.is_file():
            raise WorkflowError(f"ORCA executable was not found: {executable}")
        record.status = StageStatus.RUNNING
        record.started_at = _now()
        self._save_status()
        with self.stage_output(stage).open("w", encoding="utf-8", errors="replace") as output:
            process = subprocess.run(
                [str(executable), self.stage_input(stage).name], cwd=str(self.stage_dir(stage)),
                stdout=output, stderr=subprocess.STDOUT, shell=False,
            )
        return self.validate_stage(stage, process.returncode)

    def run_local(self) -> None:
        self.prepare()
        for stage in self.stages:
            record = self._record(stage)
            if record.status == StageStatus.NEEDS_REVIEW:
                raise WorkflowError(f"Workflow requires review before {stage}: {record.message}")
            self.run_stage(stage)
            if self._record(stage).status != StageStatus.COMPLETED:
                raise WorkflowError(f"Workflow stopped after {stage}: {self._record(stage).message}")
        self.write_reports()

    def import_completed_stage(self, stage: str, output_path: str, input_path: str, gbw_path: str) -> StageRecord:
        """Adopt a validated external stage into canonical workflow paths."""
        if stage not in {"s0_opt", "absorption", "es_opt"}:
            raise WorkflowError(f"External continuation is not supported from stage {stage}.")
        self.prepare()
        if self._validated_completed(stage):
            raise WorkflowError(f"Refusing to replace an already completed stage: {self.stage_output(stage)}")
        mappings = [
            (Path(output_path).resolve(), self.stage_output(stage)),
            (Path(input_path).resolve(), self.stage_input(stage)),
            (Path(gbw_path).resolve(), self.stage_gbw(stage)),
        ]
        for source, destination in mappings:
            if not source.is_file():
                raise FileNotFoundError(f"Required external artifact is missing: {source}")
            if destination.resolve() != source:
                shutil.copy2(source, destination)
        if stage == "absorption":
            s0_geometry = self.stage_dir("s0_opt") / f"{self.config.system.name}_S0_opt.xyz"
            extract_geometry(self.stage_output(stage), s0_geometry, "S0 geometry adopted from external absorption job")
        record_results = self.validate_stage(stage, 0)
        if stage == "absorption" and not any(
            int(item.get("state_index", -1)) == self.config.excited_states.target_root
            for item in record_results.get("states", [])
        ):
            record = self._record(stage)
            record.status = StageStatus.NEEDS_REVIEW
            record.message = f"Selected root {self.config.excited_states.target_root} is absent from the imported absorption output."
            self._save_status()
            raise WorkflowError(record.message)
        record = self._record(stage)
        record.message = f"Validated external {stage} stage; source output: {Path(output_path).resolve()}"
        record.results = record_results
        self._save_status()
        return record

    def next_stage_after(self, completed_stage: str) -> Optional[str]:
        index = self.stages.index(completed_stage)
        return self.stages[index + 1] if index + 1 < len(self.stages) else None

    def generate_slurm(self) -> Dict[str, str]:
        self.prepare()
        scheduler_dir = self.project / "scheduler"
        package_root = Path(__file__).resolve().parents[2]
        paths = {}
        for stage in self.stages:
            name = STAGE_NAMES[stage]
            path = scheduler_dir / f"{name}.slurm"
            script = build_slurm_script(self.config, stage, self.project)
            script += f'export PYTHONPATH="{package_root.as_posix()}:${{PYTHONPATH:-}}"\n'
            script += f'python -m TD_DFT.workflow.cli validate-stage "{self.project.as_posix()}" "{stage}"\n'
            path.write_text(script, encoding="utf-8", newline="\n")
            paths[stage] = str(path)
        submit = scheduler_dir / "submit_all.sh"
        submit.write_text(build_dependency_submit_script(self.config), encoding="utf-8", newline="\n")
        chained = scheduler_dir / "run_all.slurm"
        chained_text = build_chained_script(self.config, self.project)
        chained_text = chained_text.replace("set -euo pipefail\n", f'set -euo pipefail\nexport PYTHONPATH="{package_root.as_posix()}:${{PYTHONPATH:-}}"\n', 1)
        chained.write_text(chained_text, encoding="utf-8", newline="\n")
        paths.update({"submit": str(submit), "chained": str(chained)})
        return paths

    def submit_slurm(self) -> Dict[str, str]:
        if self.config.execution.scheduler != "slurm":
            raise WorkflowError("Only SLURM submission is implemented and tested.")
        paths = self.generate_slurm()
        job_ids: Dict[str, str] = {}
        previous = ""
        for stage in self.stages:
            command = ["sbatch", "--parsable"]
            if previous:
                command.append(f"--dependency=afterok:{previous}")
            command.append(paths[stage])
            process = subprocess.run(command, cwd=str(self.project / "scheduler"), capture_output=True, text=True, shell=False)
            if process.returncode != 0:
                record = self._record(stage); record.status = StageStatus.FAILED
                record.message = f"SLURM submission failed: {(process.stderr or process.stdout).strip()}"
                self._save_status()
                raise WorkflowError(record.message)
            job_id = process.stdout.strip().split(";", 1)[0]
            if not job_id:
                raise WorkflowError(f"SLURM returned no job ID for {stage}.")
            record = self._record(stage); record.status = StageStatus.SUBMITTED
            record.scheduler_job_id = job_id; record.message = "Submitted to SLURM."
            job_ids[stage] = job_id; previous = job_id
            self._save_status()
        return job_ids

    def _write_emission_summary(self, results: Dict) -> None:
        states = results.get("states", [])
        root = self.config.excited_states.target_root
        state = next((item for item in states if int(item.get("state_index", -1)) == root), None)
        if not state:
            raise WorkflowError(f"Selected emitting root {root} was not found in emission output.")
        absorption = self._record("absorption").results.get("states", [])
        absorbed = next((item for item in absorption if int(item.get("state_index", -1)) == root), None)
        payload = {
            "root": root, "energy_eV": state["energy_ev"], "wavelength_nm": state["wavelength_nm"],
            "oscillator_strength": state.get("oscillator_strength", 0.0),
            "stokes_shift_eV": float(absorbed["energy_ev"]) - float(state["energy_ev"]) if absorbed else None,
            "stokes_shift_nm": float(state["wavelength_nm"]) - float(absorbed["wavelength_nm"]) if absorbed else None,
            "note": "The Stokes shift in eV is the physically more meaningful comparison.",
        }
        atomic_write_json(self.result_path("emission-summary", ".json"), payload)
        with self.result_path("emission-summary", ".csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(payload))
            writer.writeheader(); writer.writerow(payload)

    def write_reports(self) -> None:
        provenance = {
            "generated_at": _now(), "orca_version": self.config.orca.version,
            "orca_executable": self.config.orca.executable, "method_signature": method_signature(self.config),
            "selection_rule": self.config.excited_states.selection_rule, "source_files": {},
        }
        for stage in self.stages:
            record = self._record(stage)
            provenance["source_files"][stage] = {
                "input": record.input_file, "output": record.output_file, "geometry": record.geometry_file,
                "input_sha256": file_sha256(Path(record.input_file)) if Path(record.input_file).is_file() else None,
                "output_sha256": file_sha256(Path(record.output_file)) if Path(record.output_file).is_file() else None,
            }
        atomic_write_json(self.result_path("provenance", ".json"), provenance)
        summary = {"system": self.config.system.name, "method_signature": method_signature(self.config), "stages": records_to_dict(self.records)}
        atomic_write_json(self.result_path("workflow-summary", ".json"), summary)
        with self.result_path("workflow-summary", ".csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle); writer.writerow(["Stage", "Status", "Message", "Input", "Output", "Warnings"])
            for stage in self.stages:
                record = self._record(stage)
                writer.writerow([stage, record.status.value, record.message, record.input_file, record.output_file, "; ".join(record.warnings)])
