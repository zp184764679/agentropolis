"""Import-level checks for the target unmounted route surface."""

from importlib import import_module


def test_target_route_modules_import_cleanly() -> None:
    modules = [
        "agentropolis.api.agent",
        "agentropolis.api.world",
        "agentropolis.api.skills",
        "agentropolis.api.guild",
        "agentropolis.api.diplomacy",
        "agentropolis.api.transport",
        "agentropolis.api.strategy",
        "agentropolis.api.autonomy",
        "agentropolis.api.digest",
        "agentropolis.api.dashboard",
        "agentropolis.api.market_analysis",
        "agentropolis.api.decisions",
        "agentropolis.api.warfare",
        "agentropolis.services.autopilot",
        "agentropolis.services.goal_svc",
        "agentropolis.services.digest_svc",
        "agentropolis.services.market_analysis_svc",
        "agentropolis.mcp.server",
        "agentropolis.services.guild_svc",
        "agentropolis.services.regional_project_svc",
    ]

    for module in modules:
        import_module(module)
