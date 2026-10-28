# Complete report review

This evaluation grades saved final reports with their complete retrieved evidence and explicit case-specific reference outcomes. It does not rely on a trace preview, generate another report, record an analyst disposition, or alter the running app.

Run with `.venv/bin/python -m scripts.evaluate_demo_reports --run` from the original project. Without `--run`, the script only exports the JSONL data. The manifest reuses the evaluation and avoids submitting an identical dataset twice.

Two model graders assess evidence grounding and recommendation quality. The input includes the local deterministic citation-check result. References are authored synthetic demonstration expectations, not expert-adjudicated customer truth. Apple's reference accounts for the flagged chat added after the original base-population scenario. Do not use these three cases to claim production accuracy or a reliable false-negative rate.

The script refuses to export a case without its final report or retrieved evidence. All report/evidence text is explicitly included; fields are not taken from a paginated trace. Model graders can still make mistakes. Review actual failures instead of changing the rubric merely to produce a pass.

The Platform evaluation is a separate report-based run. Historical trace grades remain unchanged. Keep the portable JSONL and rubric locally; consult OpenAI's documented Evals transition timeline when choosing a long-term evaluation platform.
