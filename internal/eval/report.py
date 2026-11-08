"""Report generator for RAG evaluation comparisons.

Generates HTML and JSON reports comparing model performance across
evaluation runs.
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from typing import Any

from app.eval.models import ModelComparison, ComparisonResult


class ComparisonReport:
    """Generate comparison reports between model runs."""

    def __init__(self, comparison: ModelComparison, results: list[dict[str, Any]]) -> None:
        self.comparison = comparison
        self.results = results

    def to_dict(self) -> dict[str, Any]:
        """Return report as a dictionary."""
        return {
            "comparison_id": str(self.comparison.id),
            "name": self.comparison.name,
            "status": self.comparison.status,
            "created_by": self.comparison.created_by,
            "created_at": self.comparison.created_at.isoformat(),
            "completed_at": self.comparison.completed_at.isoformat() if self.comparison.completed_at else None,
            "metrics": self.results,
            "summary": self._compute_summary(),
        }

    def _compute_summary(self) -> dict[str, Any]:
        """Compute summary statistics across all metrics."""
        if not self.results:
            return {
                "total_metrics": 0,
                "significant_improvements": 0,
                "significant_regressions": 0,
                "overall_trend": "no_data",
            }

        significant_improvements = sum(1 for r in self.results if r.get("significant", False) and (r.get("difference") or 0) > 0)
        significant_regressions = sum(1 for r in self.results if r.get("significant", False) and (r.get("differe
nce") or 0) < 0)

        if significant_improvements > significant_regressions:
            trend = "improving"
        elif significant_regressions > significant_improvements:
            trend = "regressing"
        else:
            trend = "stable"

        return {
            "total_metrics": len(self.results),
            "significant_improvements": significant_improvements,
            "significant_regressions": significant_regressions,
            "overall_trend": trend,
        }

    def to_html(self) -> str:
        """Generate HTML report."""
        summary = self._compute_summary()
        rows = []
        for r in self.results:
            diff = r.get("difference")
            diff_str = f"{diff:+.4f}" if diff is not None else "N/A"
            significant = "✓" if r.get("significant", False) else "✗"
            pval = r.get("p_value")
            pval_str = f"{pval:.4f}" if pval is not None else "N/A"
            rows.append(f"""
            <tr>
                <td>{r.get('metric_name', 'N/A')}</td>
                <td>{diff_str}</td>
                <td>{significant}</td>
                <td>{pval_str}</td>
                <td><pre>{json.dumps(r.get('results', {}), indent=2)}</pre></td>
            </tr>
            """)

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Evaluation Comparison: {self.comparison.name}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; }}
        h1 {{ color: #333; }}
        .summary {{ background: #f5f5f5; padding: 20px; border-radius: 8px; margin-bottom: 30px; }}
        .summary-item {{ display: inline-block; margin-right: 30px; }}
        .summary-value {{ font-size: 24px; font-weight: bold; color: #2563eb; }}
        .summary-label {{ font-size: 14px; color: #666; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
        th {{ background: #f8fafc; padding: 12px; text-align: left; border-bottom: 2px solid #e2e8f0; }}
        td {{ padding: 12px; border-bottom: 1px solid #e2e8f0; font-family: monospace; font-size: 14px; }}
        tr:hover {{ background: #f1f5f9; }}
        .significant-true {{ color: #10b981; font-weight: bold; }}
        .significant-false {{ color: #94a3b8; }}
        .positive {{ color: #10b981; }}
        .negative {{ color: #ef4444; }}
        .neutral {{ color: #64748b; }}
        pre {{ font-size: 12px; margin: 0; }}
    </style>
</head>
<body>
    <h1>📊 Evaluation Comparison: {self.comparison.name}</h1>
    <p>Created: {self.comparison.created_at.isoformat()}</p>
    {f'<p>Completed: {self.comparison.completed_at.isoformat()}</p>' if self.comparison.completed_at else ''}

    <div class="summary">
        <div class="summary-item">
            <div class="summary-value">{summary['total_metrics']}</div>
            <div class="summary-label">Metrics Compared</div>
        </div>
        <div class="summary-item">
            <div class="summary-value summary-value-positive">{summary['significant_improvements']}</div>
            <div class="summary-label">Significant Improvements</div>
        </div>
        <div class="summary-item">
            <div class="summary-value summary-value-negative">{summary['significant_regressions']}</div>
            <div class="summary-label">Significant Regressions</div>
        </div>
        <div class="summary-item">
            <div class="summary-value summary-value-neutral">{summary['overall_trend'].upper()}</div>
            <div class="summary-label">Overall Trend</div>
        </div>
    </div>

    <table>
        <thead>
            <tr>
                <th>Metric</th>
                <th>Difference</th>
                <th>Significant</th>
                <th>P-Value</th>
                <th>Results (per run)</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>
</body>
</html>"""
        return html

    def save(self, path: str, fmt: str = "html") -> None:
        """Save report to file."""
        if fmt == "html":
            content = self.to_html()
        elif fmt == "json":
            content = json.dumps(self.to_dict(), indent=2)
        else:
            raise ValueError(f"Unknown format: {fmt}")

        with open(path, "w") as f:
            f.write(content)


def generate_comparison_report(
    comparison: ModelComparison,
    results: list[dict[str, Any]],
    output_path: str | None = None,
    fmt: str = "html",
) -> dict[str, Any]:
    """Generate a comparison report.

    Args:
        comparison: The comparison model instance.
        results: List of comparison result dicts.
        output_path: Optional path to save the report.
        fmt: Output format ('html' or 'json').

    Returns:
        The report data as a dictionary.
    """
    report = ComparisonReport(comparison, results)
    if output_path:
        report.save(output_path, fmt)
    return report.to_dict()


def generate_markdown_report(
    comparison: ModelComparison,
    results: list[dict[str, Any]],
) -> str:
    """Generate a markdown comparison report."""
    summary = ComparisonReport(comparison, results)._compute_summary()
    lines = [
        f"# Evaluation Comparison: {comparison.name}",
        "",
        f"Created: {comparison.created_at.isoformat()}",
    ]
    if comparison.completed_at:
        lines.append(f"Completed: {comparison.completed_at.isoformat()}")
    lines.extend([
        "",
        "## Summary",
        f"- Total metrics compared: {summary['total_metrics']}",
        f"- Significant improvements: {summary['significant_improvements']}",
        f"- Significant regressions: {summary['significant_regressions']}",
        f"- Overall trend: {summary['overall_trend']}",
        "",
        "## Results",
        "",
        "| Metric | Difference | Significant | P-Value |",
        "|--------|------------|-------------|---------|",
    ])
    for r in results:
        diff = r.get("difference")
        diff_str = f"{diff:+.4f}" if diff is not None else "N/A"
        sig = "✓" if r.get("significant", False) else "✗"
        pval = r.get("p_value")
        pval_str = f"{pval:.4f}" if pval is not None else "N/A"
        lines.append(f"| {r.get('metric_name', 'N/A')} | {diff_str} | {sig} | {pval_str} |")
    return "\n".join(lines)
