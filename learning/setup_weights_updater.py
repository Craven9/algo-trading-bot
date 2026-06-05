"""
learning/setup_weights_updater.py — Adjusts scoring weights based on performance
Conservative, manual-approval step. Does NOT auto-update weights to prevent overfitting.
Run this manually after reviewing at least 20+ trades per setup type.
"""

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


class SetupWeightsUpdater:
    def __init__(self, settings: dict, performance_tracker=None, analyzer=None):
        self.settings = settings
        self.perf = performance_tracker
        self.analyzer = analyzer
        self.profiles_path = Path("config/strategy_profiles.json")

    def suggest_adjustments(self) -> dict:
        """
        Analyse recent performance and suggest weight adjustments.
        Returns suggestions — does NOT apply them automatically.
        """
        if not self.perf or not self.analyzer:
            return {"message": "Performance tracker or analyzer not connected"}

        analysis = self.analyzer.analyze()
        suggestions = {}

        for setup, data in analysis.get("by_setup", {}).items():
            if data["total"] < 10:
                continue
            wr = data["win_rate"]
            avg_r = data["avg_r"]
            note = []
            if wr < 0.45:
                note.append(f"Low win rate ({wr:.0%}) — consider raising min_score threshold")
            if avg_r < 0.5:
                note.append(f"Low avg R ({avg_r:.2f}) — review exit rules for this setup")
            if wr > 0.7 and avg_r > 1.5:
                note.append(f"Strong performance — consider relaxing min_score by 2-3 points")
            if note:
                suggestions[setup] = note

        return suggestions

    def apply_adjustment(self, setup: str, weight_key: str, new_value: int):
        """
        Manually apply a weight change to a strategy profile.
        Requires explicit call — never called automatically.
        """
        if not self.profiles_path.exists():
            log.error("strategy_profiles.json not found")
            return False

        with open(self.profiles_path) as f:
            profiles = json.load(f)

        if setup not in profiles:
            log.error(f"Setup '{setup}' not found in profiles")
            return False

        old = profiles[setup].get("score_weights", {}).get(weight_key, "?")
        profiles[setup].setdefault("score_weights", {})[weight_key] = new_value

        with open(self.profiles_path, "w") as f:
            json.dump(profiles, f, indent=2)

        log.info(f"Weight updated: {setup}.{weight_key}: {old} → {new_value}")
        return True
