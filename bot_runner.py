"""
bot_runner.py — Master Orchestrator
Runs the daily trading loop, calls each subsystem in order.
The runner orchestrates; it does NOT make trading decisions.
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime, time as dt_time
from pathlib import Path

from config.settings_loader import load_settings
from data.market_data_fetcher import MarketDataFetcher
from data.session_context import SessionContext
from scanner.stock_scanner import StockScanner
from scanner.news_catalyst_checker import NewsCatalystChecker
from analysis.market_influence_filter import MarketInfluenceFilter
from decision.trade_quality_gate import TradeQualityGate
from risk.account_risk_guard import AccountRiskGuard
from risk.position_tracker import PositionTracker
from execution.order_executor import OrderExecutor
from execution.trade_logger import TradeLogger
from exit.exit_manager import ExitManager
from learning.performance_tracker import PerformanceTracker
from frontend.api_server import APIServer

# ── Logging setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/bot_runner.log"),
    ],
)
log = logging.getLogger("BotRunner")


class BotRunner:
    """
    Top-level orchestrator. Initialises all subsystems and runs the main loop.
    Never makes buy/sell decisions itself — it delegates every decision to the
    appropriate engine and only acts on their verdicts.
    """

    def __init__(self):
        self.settings = load_settings()
        self.running = False
        self.paused_new_entries = False

        # Subsystems
        self.session_ctx = SessionContext(self.settings)
        self.data_fetcher = MarketDataFetcher(self.settings)
        self.scanner = StockScanner(self.settings, self.data_fetcher)
        self.news_checker = NewsCatalystChecker(self.settings)
        self.market_filter = MarketInfluenceFilter(self.settings, self.data_fetcher)
        self.position_tracker = PositionTracker(self.settings)
        self.account_guard = AccountRiskGuard(self.settings, self.position_tracker)
        self.quality_gate = TradeQualityGate(self.settings)
        self.order_executor = OrderExecutor(self.settings)
        self.trade_logger = TradeLogger(self.settings)
        self.exit_manager = ExitManager(self.settings, self.position_tracker, self.order_executor, self.trade_logger)
        self.perf_tracker = PerformanceTracker(self.settings)
        self.api_server = APIServer(self.settings, self)

        # Register shutdown signals
        signal.signal(signal.SIGINT, self._shutdown_signal)
        signal.signal(signal.SIGTERM, self._shutdown_signal)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self):
        log.info("=" * 60)
        log.info("Algo Trading Bot starting up")
        log.info(f"  Mode      : {'DRY RUN' if self.settings['mode']['dry_run'] else 'PAPER' if self.settings['mode']['paper_trading'] else 'LIVE'}")
        log.info(f"  Risk/trade: {self.settings['risk']['risk_per_trade_pct']}%")
        log.info("=" * 60)

        self.running = True

        # Start API server in background
        asyncio.create_task(self.api_server.serve())

        await self._main_loop()

    async def _main_loop(self):
        scan_interval = self.settings["scanner"]["scan_interval_seconds"]

        while self.running:
            try:
                await self._run_cycle()
            except Exception as exc:
                log.exception(f"Unhandled error in main loop: {exc}")

            await asyncio.sleep(scan_interval)

    async def _run_cycle(self):
        """One full scan-analyse-decide-manage cycle."""
        now = datetime.now()
        session = self.session_ctx.get_session(now)
        log.debug(f"Cycle start | session={session} | {now.strftime('%H:%M:%S')}")

        # 1. Update session / market data
        market_state = await self.market_filter.get_market_state()

        # 2. Manage open positions first (exits take priority over new entries)
        if self.position_tracker.has_open_positions():
            await self._manage_open_positions(market_state)

        # 3. End-of-day exit
        if session == "EOD":
            await self._end_of_day_routine()
            return

        # 4. New entries only during active trading hours and if not paused
        if session == "ACTIVE" and not self.paused_new_entries:
            await self._scan_and_evaluate(market_state)

    # ── Scanning & Entry ──────────────────────────────────────────────────────

    async def _scan_and_evaluate(self, market_state):
        if not self.account_guard.can_open_new_position():
            log.info("Account guard blocked new entries (daily limit or max positions reached)")
            return

        candidates = await self.scanner.get_candidates()
        log.info(f"Scanner returned {len(candidates)} candidate(s)")

        for ticker in candidates:
            try:
                await self._evaluate_ticker(ticker, market_state)
            except Exception as exc:
                log.exception(f"Error evaluating {ticker}: {exc}")

    async def _evaluate_ticker(self, ticker: str, market_state: dict):
        """Run the full analysis pipeline for one ticker."""
        log.debug(f"Evaluating {ticker}")

        # Fetch data
        ohlcv = await self.data_fetcher.get_ohlcv(ticker)
        level2 = await self.data_fetcher.get_level2(ticker)
        news = await self.news_checker.get_catalyst(ticker)

        if ohlcv is None:
            log.warning(f"{ticker}: No OHLCV data, skipping")
            return

        # Build context package for quality gate
        context = {
            "ticker": ticker,
            "ohlcv": ohlcv,
            "level2": level2,
            "news": news,
            "market_state": market_state,
            "account_state": self.account_guard.get_state(),
            "timestamp": datetime.now(),
        }

        # Quality gate makes the buy/no-buy decision
        verdict = self.quality_gate.evaluate(context)

        if verdict.approved:
            await self._execute_entry(ticker, verdict, context)
        else:
            self.trade_logger.log_rejection(ticker, verdict)
            log.info(f"{ticker} REJECTED — {verdict.primary_rejection_reason}")

    async def _execute_entry(self, ticker: str, verdict, context: dict):
        """Place the paper/live order after quality gate approval."""
        log.info(f"{ticker} APPROVED — score={verdict.setup_score} prob={verdict.probability:.0%} R:R={verdict.risk_reward:.1f}")

        order = await self.order_executor.place_entry(
            ticker=ticker,
            shares=verdict.position_size,
            entry_price=verdict.entry_price,
            stop_price=verdict.stop_price,
            targets=verdict.targets,
        )

        if order:
            self.position_tracker.add_position(ticker, order, verdict)
            self.trade_logger.log_entry(ticker, order, verdict, context)

    # ── Exit Management ───────────────────────────────────────────────────────

    async def _manage_open_positions(self, market_state: dict):
        for position in self.position_tracker.get_open_positions():
            try:
                ohlcv = await self.data_fetcher.get_ohlcv(position.ticker)
                if ohlcv:
                    await self.exit_manager.check_position(position, ohlcv, market_state)
            except Exception as exc:
                log.exception(f"Error managing position {position.ticker}: {exc}")

    # ── End of Day ────────────────────────────────────────────────────────────

    async def _end_of_day_routine(self):
        log.info("EOD routine starting — closing all positions")
        for position in self.position_tracker.get_open_positions():
            await self.order_executor.close_position(position.ticker, reason="EOD")
            self.trade_logger.log_exit(position, reason="EOD")

        # Update performance stats
        closed_today = self.trade_logger.get_todays_closed_trades()
        self.perf_tracker.record_day(closed_today)
        log.info(f"EOD complete — {len(closed_today)} trade(s) logged")

    # ── Controls (called by API server) ───────────────────────────────────────

    def pause_new_entries(self):
        self.paused_new_entries = True
        log.info("New entries PAUSED")

    def resume_new_entries(self):
        self.paused_new_entries = False
        log.info("New entries RESUMED")

    async def emergency_close_all(self):
        log.warning("EMERGENCY CLOSE ALL triggered")
        for position in self.position_tracker.get_open_positions():
            await self.order_executor.close_position(position.ticker, reason="EMERGENCY")
            self.trade_logger.log_exit(position, reason="EMERGENCY")

    def get_status(self) -> dict:
        return {
            "running": self.running,
            "paused": self.paused_new_entries,
            "mode": self.settings["mode"],
            "session": self.session_ctx.get_session(datetime.now()),
            "open_positions": len(self.position_tracker.get_open_positions()),
            "account": self.account_guard.get_state(),
            "daily_pnl": self.position_tracker.get_daily_pnl(),
        }

    def _shutdown_signal(self, *_):
        log.info("Shutdown signal received")
        self.running = False


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    bot = BotRunner()
    asyncio.run(bot.start())
