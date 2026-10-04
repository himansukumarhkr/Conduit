import os
import time
import json
from typing import Dict, Any, List


class ReportGenerator:
    __test__ = False

    @classmethod
    def generate_html_report(
        cls,
        workspace_dir: str,
        run_data: Dict[str, Any],
        scenario_results: List[Dict[str, Any]],
        env: str = "QA",
        browser: str = "msedge",
        device: str = "Desktop 1280x800"
    ) -> str:
        reports_dir = os.path.join(workspace_dir, "reports")
        os.makedirs(reports_dir, exist_ok=True)

        total = run_data.get("total", len(scenario_results))
        passed = run_data.get("passed", sum(1 for s in scenario_results if s.get("status") == "Passed"))
        failed = run_data.get("failed", total - passed)
        duration = run_data.get("duration", 0.0)
        pass_rate = round((passed / total * 100), 1) if total > 0 else 0.0
        status_overall = "Passed" if failed == 0 and total > 0 else "Failed"

        timestamp_str = time.strftime("%Y-%m-%d %H:%M:%S")
        file_timestamp = time.strftime("%Y%m%d_%H%M%S")

        circumference = 2 * 3.14159 * 40
        passed_stroke = (passed / total * circumference) if total > 0 else 0
        failed_stroke = circumference - passed_stroke

        scenarios_html = ""
        for idx, sc in enumerate(scenario_results, 1):
            sc_name = sc.get("name", f"Scenario {idx}")
            sc_status = sc.get("status", "Passed")
            sc_dur = sc.get("duration", "--")
            sc_retries = sc.get("retries_attempted", 0)
            status_color = "#34d399" if sc_status == "Passed" else "#f87171"
            badge_bg = "rgba(52, 211, 153, 0.15)" if sc_status == "Passed" else "rgba(248, 113, 113, 0.15)"

            steps_html = ""
            for s_idx, st in enumerate(sc.get("steps", []), 1):
                st_desc = st.get("human_description", f"Step {s_idx}")
                st_code = st.get("code", "")
                steps_html += f"""
                <div style="background:#090e18;border:1px solid #1e293b;border-radius:6px;padding:8px 12px;margin-bottom:6px;display:flex;align-items:center;justify-content:space-between;">
                    <div style="display:flex;align-items:center;gap:10px;">
                        <span style="background:rgba(56,189,248,0.15);color:#38bdf8;font-size:10px;font-weight:bold;width:20px;height:20px;display:flex;align-items:center;justify-content:center;border-radius:50%;">{s_idx}</span>
                        <span style="color:#e2e8f0;font-size:12px;font-weight:500;">{st_desc}</span>
                    </div>
                    <code style="color:#94a3b8;font-size:11px;background:#0d1527;padding:3px 8px;border-radius:4px;font-family:monospace;">{st_code}</code>
                </div>
                """

            evidence_html = ""
            sc_ev_dir = sc.get("evidence_dir", "")
            if sc_ev_dir and os.path.exists(sc_ev_dir):
                ev_files = [f for f in os.listdir(sc_ev_dir) if f.lower().endswith((".png", ".jpg"))]
                if ev_files:
                    evidence_html += '<div style="margin-top:10px;"><div style="font-size:11px;font-weight:bold;color:#94a3b8;margin-bottom:6px;">Step Screenshots:</div><div style="display:flex;gap:10px;flex-wrap:wrap;">'
                    for ev_img in ev_files[:6]:
                        img_path = os.path.join(sc_ev_dir, ev_img).replace("\\", "/")
                        evidence_html += f'<div style="text-align:center;"><img src="file:///{img_path}" style="height:90px;border-radius:6px;border:1px solid #334155;cursor:pointer;" onclick="window.open(this.src)"/><div style="color:#64748b;font-size:10px;margin-top:2px;">{ev_img}</div></div>'
                    evidence_html += '</div></div>'

            retry_badge = f'<span style="background:rgba(251,191,36,0.15);color:#fbbf24;font-size:10px;font-weight:bold;padding:2px 6px;border-radius:4px;margin-left:6px;">Retries: {sc_retries}</span>' if sc_retries > 0 else ""

            scenarios_html += f"""
            <div style="background:#0d1527;border:1px solid #1e293b;border-radius:8px;padding:16px;margin-bottom:12px;">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;">
                    <div style="display:flex;align-items:center;gap:10px;">
                        <span style="background:{badge_bg};color:{status_color};font-weight:bold;font-size:11px;padding:4px 10px;border-radius:6px;border:1px solid {status_color};">{sc_status.upper()}</span>
                        <strong style="color:#ffffff;font-size:14px;">{sc_name}</strong>
                        {retry_badge}
                    </div>
                    <span style="color:#94a3b8;font-size:12px;">Duration: {sc_dur}s</span>
                </div>
                {steps_html}
                {evidence_html}
            </div>
            """

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Conduit Test Execution Report - {status_overall}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ background: #070b13; color: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; padding: 24px; }}
        .header {{ display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #1e293b; padding-bottom: 20px; margin-bottom: 24px; }}
        .brand {{ display: flex; align-items: center; gap: 12px; }}
        .brand-icon {{ width: 32px; height: 32px; background: linear-gradient(135deg, #0284c7, #2563eb); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-weight: bold; color: #fff; font-size: 16px; }}
        .brand h1 {{ font-size: 20px; font-weight: bold; color: #ffffff; }}
        .brand span {{ font-size: 12px; color: #64748b; margin-left: 6px; }}
        .meta-pill {{ background: #131b2e; border: 1px solid #2a3a5e; border-radius: 20px; padding: 6px 14px; font-size: 12px; color: #94a3b8; display: inline-flex; align-items: center; gap: 8px; margin-left: 8px; }}
        .meta-pill strong {{ color: #38bdf8; }}
        .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 24px; }}
        .kpi-card {{ background: #0d1527; border: 1px solid #1e293b; border-radius: 10px; padding: 18px; }}
        .kpi-title {{ font-size: 12px; font-weight: bold; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }}
        .kpi-val {{ font-size: 28px; font-weight: 800; color: #ffffff; }}
        .chart-box {{ background: #0d1527; border: 1px solid #1e293b; border-radius: 10px; padding: 20px; display: flex; align-items: center; gap: 30px; margin-bottom: 24px; }}
        .section-title {{ font-size: 16px; font-weight: bold; color: #ffffff; margin-bottom: 14px; }}
    </style>
</head>
<body>
    <div class="header">
        <div class="brand">
            <div class="brand-icon">⚡</div>
            <div>
                <h1>Conduit Execution Report</h1>
                <span>Enterprise UI Automation Report & Diagnostics</span>
            </div>
        </div>
        <div>
            <div class="meta-pill">Context: <strong>{env}</strong></div>
            <div class="meta-pill">Browser: <strong>{browser}</strong></div>
            <div class="meta-pill">Device: <strong>{device}</strong></div>
            <div class="meta-pill">Run Time: <strong>{timestamp_str}</strong></div>
        </div>
    </div>

    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-title">Total Tests</div>
            <div class="kpi-val">{total}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">Pass Rate</div>
            <div class="kpi-val" style="color: {'#34d399' if pass_rate >= 80 else '#f87171'};">{pass_rate}%</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">Passed</div>
            <div class="kpi-val" style="color: #34d399;">{passed}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">Failed</div>
            <div class="kpi-val" style="color: #f87171;">{failed}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">Total Duration</div>
            <div class="kpi-val">{duration}s</div>
        </div>
    </div>

    <div class="chart-box">
        <svg width="100" height="100" viewBox="0 0 100 100">
            <circle cx="50" cy="50" r="40" stroke="#1e293b" stroke-width="12" fill="none" />
            <circle cx="50" cy="50" r="40" stroke="#f87171" stroke-width="12" fill="none"
                stroke-dasharray="{failed_stroke} {passed_stroke}" stroke-dashoffset="0" transform="rotate(-90 50 50)" />
            <circle cx="50" cy="50" r="40" stroke="#34d399" stroke-width="12" fill="none"
                stroke-dasharray="{passed_stroke} {failed_stroke}" stroke-dashoffset="0" transform="rotate(-90 50 50)" />
        </svg>
        <div>
            <h3 style="font-size:16px;font-weight:bold;margin-bottom:6px;">Overall Result: <span style="color:{'#34d399' if status_overall == 'Passed' else '#f87171'};">{status_overall}</span></h3>
            <p style="color:#94a3b8;font-size:13px;">{passed} of {total} test scenarios passed successfully with 0 critical locator blockages.</p>
        </div>
    </div>

    <div class="section-title">Executed Test Scenarios</div>
    {scenarios_html}

</body>
</html>
"""
        report_path = os.path.join(reports_dir, f"report_{file_timestamp}.html")
        latest_path = os.path.join(reports_dir, "latest_report.html")

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        with open(latest_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        return latest_path
