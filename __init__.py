"""Equity Research AI Agent — Autonomous Institutional Fundamental Research Engine."""

from __future__ import annotations

__version__ = "1.0.0"

from agent import AgentRunResult, AgentStep, FundamentalAnalystAgent
from agent_tools import AgentWorkspace
from dashboard_builder import save_web_dashboard
from kdb_engine import KDBXEngine
from scoring_engine import InvestorProfile
from standardized_report import build_standardized_report, render_standardized_markdown

__all__ = [
    "__version__",
    "AgentRunResult",
    "AgentStep",
    "AgentWorkspace",
    "FundamentalAnalystAgent",
    "InvestorProfile",
    "KDBXEngine",
    "build_standardized_report",
    "render_standardized_markdown",
    "save_web_dashboard",
]
