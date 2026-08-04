from __future__ import annotations

import shlex
from pathlib import Path
from typing import Dict, List
from ..td_dft_naming import workflow_calculation_stem


STAGE_NAMES = {
    "s0_opt": "01_S0_opt", "s0_freq": "02_S0_freq", "absorption": "03_absorption",
    "es_opt": "04_S1_opt", "emission": "05_emission",
}


def dependency_order(frequency_enabled: bool = True) -> List[str]:
    return ["s0_opt"] + (["s0_freq"] if frequency_enabled else []) + ["absorption", "es_opt", "emission"]


def build_slurm_script(config, stage: str, project: Path) -> str:
    directory_name = STAGE_NAMES[stage]
    name = workflow_calculation_stem(config, stage)
    scheduler = config.scheduler
    account = f"#SBATCH --account={scheduler.account}\n" if scheduler.account else ""
    predecessor = dependency_order(config.frequency.enabled)
    index = predecessor.index(stage)
    checks = ""
    if index:
        previous_stage = predecessor[index - 1]
        previous_directory = STAGE_NAMES[previous_stage]
        previous = workflow_calculation_stem(config, previous_stage)
        checks = (
            f'test -f "../{previous_directory}/{previous}.out" || {{ echo "Missing predecessor output"; exit 20; }}\n'
            f'grep -q "ORCA TERMINATED NORMALLY" "../{previous_directory}/{previous}.out" || {{ echo "Predecessor failed"; exit 21; }}\n'
        )
    executable = shlex.quote(config.orca.executable)
    return (
        "#!/bin/bash\nset -euo pipefail\n"
        f"#SBATCH --job-name={config.system.name}_{stage}\n"
        f"#SBATCH --nodes={scheduler.nodes}\n#SBATCH --ntasks={scheduler.ntasks}\n"
        f"#SBATCH --mem={scheduler.memory}\n#SBATCH --time={scheduler.walltime[stage]}\n"
        f"#SBATCH --partition={scheduler.partition}\n{account}"
        f'cd "{(project / directory_name).as_posix()}"\n{checks}'
        f'{executable} "{name}.inp" > "{name}.out"\n'
        f'grep -q "ORCA TERMINATED NORMALLY" "{name}.out"\n'
    )


def build_dependency_submit_script(config) -> str:
    order = dependency_order(config.frequency.enabled)
    lines = ["#!/bin/bash", "set -euo pipefail", ""]
    previous = ""
    for index, stage in enumerate(order, 1):
        name = STAGE_NAMES[stage]
        dependency = f" --dependency=afterok:${previous}" if previous else ""
        variable = f"jid{index}"
        lines.append(f'{variable}=$(sbatch --parsable{dependency} "{name}.slurm")')
        lines.append(f'echo "{stage}: ${variable}"')
        previous = variable
    return "\n".join(lines) + "\n"


def build_chained_script(config, project: Path) -> str:
    scheduler = config.scheduler
    lines = [
        "#!/bin/bash", "set -euo pipefail", f"#SBATCH --job-name={config.system.name}_tddft_pipeline",
        f"#SBATCH --nodes={scheduler.nodes}", f"#SBATCH --ntasks={scheduler.ntasks}",
        f"#SBATCH --mem={scheduler.memory}", "#SBATCH --time=96:00:00", "",
        "run_stage () {", "  stage_dir=\"$1\"", "  stem=\"$2\"", "  cd \"$stage_dir\"",
        f"  {shlex.quote(config.orca.executable)} \"$stem.inp\" > \"$stem.out\"",
        "  grep -q \"ORCA TERMINATED NORMALLY\" \"$stem.out\"", "  cd - >/dev/null", "}", "",
    ]
    for stage in dependency_order(config.frequency.enabled):
        directory_name = STAGE_NAMES[stage]
        name = workflow_calculation_stem(config, stage)
        lines.append(f'run_stage "{(project / directory_name).as_posix()}" "{name}"')
        lines.append(f'python -m TD_DFT.workflow.cli validate-stage "{project.as_posix()}" "{stage}"')
    return "\n".join(lines) + "\n"
