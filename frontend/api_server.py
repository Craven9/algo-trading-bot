"""
frontend/api_server.py — FastAPI server for the React dashboard
Serves live bot status, trades, scanner data, and performance stats.
Exposes control endpoints (pause, stop, emergency close).
"""

import logging
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

log = logging.getLogger(__name__)


def create_app(settings: dict, bot) -> FastAPI:
    app = FastAPI(title="Algo Trading Bot API", version="1.0.0")

    origins = settings["frontend"].get("cors_origins", ["http://localhost:3000"])
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Status endpoints ──────────────────────────────────────────────────────

    @app.get("/api/status")
    async def get_status():
        return bot.get_status()

    @app.get("/api/positions")
    async def get_positions():
        return [p.to_dict() for p in bot.position_tracker.get_open_positions()]

    @app.get("/api/account")
    async def get_account():
        return bot.account_guard.get_state()

    @app.get("/api/performance")
    async def get_performance():
        return {
            "setup_stats": bot.perf_tracker.get_all_stats(),
            "equity_curve": bot.perf_tracker.get_equity_curve(),
            "today_trades": bot.trade_logger.get_todays_closed_trades(),
        }

    @app.get("/api/rejections")
    async def get_rejections():
        """Return today's rejection log."""
        import json
        from pathlib import Path
        from datetime import date
        rejection_file = Path(settings["logging"]["rejection_log_dir"]) / f"rejections_{date.today().isoformat()}.jsonl"
        if not rejection_file.exists():
            return []
        records = []
        with open(rejection_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        pass
        return records[-100:]  # last 100 rejections

    @app.get("/api/scanner")
    async def get_scanner_state():
        return {
            "running": bot.running,
            "paused_new_entries": bot.paused_new_entries,
            "last_scan": datetime.now().isoformat(),
        }

    # ── Control endpoints ─────────────────────────────────────────────────────

    @app.post("/api/control/pause")
    async def pause_entries():
        bot.pause_new_entries()
        return {"status": "paused"}

    @app.post("/api/control/resume")
    async def resume_entries():
        bot.resume_new_entries()
        return {"status": "resumed"}

    @app.post("/api/control/stop")
    async def stop_bot():
        bot.running = False
        return {"status": "stopping"}

    @app.post("/api/control/emergency-close")
    async def emergency_close():
        await bot.emergency_close_all()
        return {"status": "all positions closed"}

    @app.post("/api/control/close/{ticker}")
    async def close_position(ticker: str):
        position = bot.position_tracker.get_position(ticker.upper())
        if not position:
            raise HTTPException(status_code=404, detail=f"No open position for {ticker}")
        await bot.order_executor.close_position(ticker.upper(), reason="Manual close via dashboard")
        bot.trade_logger.log_exit(position, reason="Manual close")
        bot.position_tracker.remove_position(ticker.upper())
        return {"status": "closed", "ticker": ticker.upper()}

    @app.post("/api/control/risk/{pct}")
    async def set_risk_pct(pct: float):
        if not 0.1 <= pct <= 5.0:
            raise HTTPException(status_code=400, detail="Risk must be between 0.1% and 5.0%")
        bot.settings["risk"]["risk_per_trade_pct"] = pct
        return {"risk_per_trade_pct": pct}

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "timestamp": datetime.now().isoformat()}

    return app


class APIServer:
    def __init__(self, settings: dict, bot):
        self.settings = settings
        self.bot = bot
        self.port = settings["frontend"].get("api_port", 8080)

    async def serve(self):
        app = create_app(self.settings, self.bot)
        config = uvicorn.Config(app, host="0.0.0.0", port=self.port, log_level="warning")
        server = uvicorn.Server(config)
        log.info(f"API server starting on port {self.port}")
        await server.serve()
