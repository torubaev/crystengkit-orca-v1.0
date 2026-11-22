from pathlib import Path
import sys


ORCA_INPUT = Path(__file__).resolve().parents[1] / "tools" / "Orca_input"
sys.path.insert(0, str(ORCA_INPUT))

from calculation_report import append_tool_use_record, parse_tool_use_records, render_report


def test_tool_records_round_trip_in_execution_order(tmp_path):
    output = tmp_path / "job.out"
    output.write_text("ORCA TERMINATED NORMALLY\n", encoding="utf-8")

    append_tool_use_record(output, "ORCA", purpose="electronic-structure calculation", exit_code=0)
    append_tool_use_record(output, "orca_2aim", purpose="WFN/WFX generation")
    append_tool_use_record(output, "Multiwfn", "failed", purpose="ESP/MEP cube generation")

    records = parse_tool_use_records(output)
    assert [record["tool"] for record in records] == ["ORCA", "orca_2aim", "Multiwfn"]
    assert records[-1]["status"] == "failed"


def test_report_lists_only_parsed_tool_records_in_order(tmp_path):
    output = tmp_path / "job.out"
    output.write_text("plain ORCA output\n", encoding="utf-8")
    append_tool_use_record(output, "ORCA", purpose="electronic-structure calculation")
    append_tool_use_record(output, "orca_2aim", purpose="WFN/WFX generation")

    lines = render_report(
        {
            "settings": {},
            "execution_evidence": {},
            "post_processing": {},
            "analysis_files": {},
            "tool_use_records": parse_tool_use_records(output),
        },
        "https://example.invalid",
    )
    report = "\n".join(lines)
    assert "Tools actually used (execution order)" in report
    assert report.index("1. ORCA") < report.index("2. orca_2aim")
    assert "Multiwfn" not in report


def test_parser_ignores_malformed_records(tmp_path):
    output = tmp_path / "job.out"
    output.write_text(
        '# CRYSTENGKIT_TOOL_USE not-json\n'
        '# CRYSTENGKIT_TOOL_USE {"status": "completed"}\n',
        encoding="utf-8",
    )
    assert parse_tool_use_records(output) == []
