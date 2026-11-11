"""Market & Financial Statement Ingestor backed by yfinance and KDB-X (.kdb) cache."""

from __future__ import annotations

import datetime as dt
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import yfinance as yf

from kdb_engine import KDBXEngine

# Curated multi-sector starter universes for fast Stage 0 scanning
PRESET_UNIVERSES: Dict[str, Dict[str, List[str]]] = {
    "IN": {
        "Defense & Infra": ["HAL.NS", "BEL.NS", "MAZDOCK.NS", "LT.NS", "CGPOWER.NS"],
        "IT & Digital": ["TCS.NS", "PERSISTENT.NS", "COFORGE.NS", "KPITTECH.NS", "TATAELXSI.NS"],
        "Pharma & Chemicals": ["SUNPHARMA.NS", "DIVISLAB.NS", "PIIND.NS", "DEEPAKNTR.NS", "CIPLA.NS"],
        "Consumer & Retail": ["TITAN.NS", "TRENT.NS", "PIDILITIND.NS", "ITC.NS", "DMART.NS"],
        "Banking & Financials": ["HDFCBANK.NS", "ICICIBANK.NS", "BAJFINANCE.NS", "BSE.NS", "CDSL.NS"],
        "Energy & Manufacturing": ["RELIANCE.NS", "NTPC.NS", "SOLARINDS.NS", "CUMMINSIND.NS", "ABB.NS"],
    },
    "CA": {
        "IT & Digital": ["CSU.TO", "SHOP.TO", "OTEX.TO", "DSG.TO", "GIB-A.TO"],
        "Consumer & Retail": ["DOL.TO", "ATD.TO", "L.TO", "CTC-A.TO", "MRU.TO"],
        "Banking & Financials": ["RY.TO", "TD.TO", "BN.TO", "BAM.TO", "FFH.TO"],
        "Energy & Industrials": ["CNQ.TO", "SU.TO", "WCN.TO", "CNR.TO", "CP.TO"],
    },
    "US": {
        "IT & AI": ["MSFT", "NVDA", "AAPL", "ANET", "FICO"],
        "Consumer & Retail": ["COST", "AMZN", "MELI", "ORLY", "TJX"],
        "Healthcare": ["LLY", "ISRG", "VEEV", "UNH", "TMO"],
        "Financials & Industrials": ["BRK-B", "V", "MA", "URI", "HEI"],
    },
}


# Emerging small/mid-cap multibagger discovery universes
MULTIBAGGER_UNIVERSES: Dict[str, Dict[str, List[str]]] = {
    "IN": {
        "Defense & Infra": ["DATAPATTNS.NS", "PARAS.NS", "ZENTEC.NS", "KAYNES.NS", "KPIL.NS"],
        "IT & Digital": ["NEWGEN.NS", "ECLERX.NS", "INTELLECT.NS", "RATEGAIN.NS", "TANLA.NS"],
        "Pharma & Chemicals": ["NEULANDLAB.NS", "FINEORG.NS", "NAVINFLUOR.NS", "GLAND.NS", "ALKYLAMINE.NS"],
        "Consumer & Retail": ["SAFARI.NS", "ETHOSLTD.NS", "PGEL.NS", "SENCO.NS", "WESTLIFE.NS"],
        "Banking & Financials": ["KFINTECH.NS", "ANGELONE.NS", "MCX.NS", "AAVAS.NS", "HOMEFIRST.NS"],
        "Energy & Manufacturing": ["PRAJIND.NS", "TRITURBINE.NS", "THERMAX.NS", "ELECON.NS", "APARINDS.NS"],
    },
    "CA": {
        "IT & Digital": ["DSG.TO", "KXS.TO", "CLS.TO", "ENGH.TO", "SYZ.TO"],
        "Consumer & Retail": ["DOL.TO", "ATZ.TO", "PBH.TO", "MTY.TO", "PET.TO"],
        "Banking & Financials": ["EQB.TO", "GSY.TO", "ECN.TO", "EFN.TO", "CF.TO"],
        "Energy & Industrials": ["BDT.TO", "TFII.TO", "STN.TO", "AIF.TO", "WSP.TO"],
    },
    "US": {
        "IT & AI": ["DUOL", "TOST", "IOT", "GWRE", "VERX"],
        "Consumer & Retail": ["CELH", "WING", "ELF", "BOOT", "ONON"],
        "Healthcare": ["MEDP", "HIMS", "TMDX", "NARI", "HALO"],
        "Financials & Industrials": ["AXON", "FIX", "MOD", "IESC", "EME"],
    },
}


def get_universe_tickers(
    market: str = "IN",
    sectors: Optional[List[str]] = None,
    custom_tickers: Optional[List[str]] = None,
    cap_focus: str = "all",
) -> List[str]:
    """Resolve final deduplicated ticker list from investor market, cap focus, sectors, and custom symbols."""
    tickers: List[str] = []
    if custom_tickers:
        for t in custom_tickers:
            cleaned = t.strip().upper()
            if cleaned and cleaned not in tickers:
                tickers.append(cleaned)

    source_pool = (
        MULTIBAGGER_UNIVERSES
        if cap_focus.lower() == "small_mid"
        else PRESET_UNIVERSES
    )
    mkt_map = source_pool.get(market.upper(), {})
    if not mkt_map and market.upper() == "GLOBAL":
        for sub in source_pool.values():
            for syms in sub.values():
                for s in syms:
                    if s not in tickers:
                        tickers.append(s)
        return tickers

    selected_sectors = sectors or ["ALL"]
    if "ALL" in [s.upper() for s in selected_sectors]:
        for syms in mkt_map.values():
            for s in syms:
                if s not in tickers:
                    tickers.append(s)
    else:
        for sec_name, syms in mkt_map.items():
            if any(req.lower() in sec_name.lower() for req in selected_sectors):
                for s in syms:
                    if s not in tickers:
                        tickers.append(s)
    return tickers


def search_yahoo_tickers(query: str, max_results: int = 8) -> List[Dict[str, Any]]:
    """Search Yahoo Finance symbols (supports global & ca.finance.yahoo tickers)."""
    if not query.strip():
        return []
    try:
        res = yf.Search(query.strip(), max_results=max_results)
        quotes = getattr(res, "quotes", []) or []
        return [
            {
                "symbol": q.get("symbol", ""),
                "shortname": q.get("shortname") or q.get("longname") or "",
                "exchange": q.get("exchDisp") or q.get("exchange") or "",
                "type": q.get("quoteType") or "",
            }
            for q in quotes
            if q.get("symbol")
        ]
    except Exception:
        return []


def _safe_key(symbol: str) -> str:
    return symbol.replace(".", "_").replace("-", "_").replace("^", "_")


def _stmt_to_df(stmt: pd.DataFrame) -> pd.DataFrame:
    """Convert yfinance statement (rows=metrics, cols=timestamps) into KDB-friendly DF."""
    if stmt is None or stmt.empty:
        return pd.DataFrame()
    out = stmt.copy()
    out.columns = [str(c)[:10] for c in out.columns]
    out.index.name = "metric"
    return out.reset_index()


def _df_to_stmt(df: Optional[pd.DataFrame]) -> pd.DataFrame:
    if df is None or df.empty or "metric" not in df.columns:
        return pd.DataFrame()
    return df.set_index("metric")


def _actual_data_checks(
    info: Dict[str, Any],
    inc: Optional[pd.DataFrame],
    bal: Optional[pd.DataFrame],
    cf: Optional[pd.DataFrame],
    hist: Optional[pd.DataFrame],
) -> Dict[str, Any]:
    """Verify actual market quote and financial statement availability (strict actual-data policy)."""
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    mcap = info.get("marketCap")
    has_inc = inc is not None and not inc.empty
    has_bal = bal is not None and not bal.empty
    has_cf = cf is not None and not cf.empty
    has_hist = hist is not None and not hist.empty
    return {
        "strict_actual_only": True,
        "has_price": bool(price is not None and float(price) > 0),
        "has_market_cap": bool(mcap is not None and float(mcap) > 0),
        "has_income_stmt": has_inc,
        "has_balance_sheet": has_bal,
        "has_cashflow": has_cf,
        "has_price_history": has_hist,
    }


class MarketDataIngestor:
    """Fetches fundamentals via yfinance and caches columnar snapshots in KDB-X (.kdb)."""

    def __init__(self, kdb: KDBXEngine, cache_ttl_seconds: int = 43200) -> None:
        self.kdb = kdb
        self.cache_ttl_seconds = cache_ttl_seconds
        self.meta_dir = self.kdb.cache_dir / "meta"
        self.meta_dir.mkdir(parents=True, exist_ok=True)

    def fetch_ticker_bundle(
        self, symbol: str, force_refresh: bool = False
    ) -> Dict[str, Any]:
        """Load ticker info, statements, and 1y price history (KDB-X cache first)."""
        key = _safe_key(symbol)
        meta_path = self.meta_dir / f"{key}.json"
        ttl = None if not force_refresh else 0

        if not force_refresh and meta_path.exists():
            age = time.time() - meta_path.stat().st_mtime
            if age <= self.cache_ttl_seconds:
                inc_df = self.kdb.load_table(f"inc_{key}")
                bal_df = self.kdb.load_table(f"bal_{key}")
                cf_df = self.kdb.load_table(f"cf_{key}")
                hist_df = self.kdb.load_table(f"hist_{key}")
                if inc_df is not None and bal_df is not None and cf_df is not None:
                    info = json.loads(meta_path.read_text(encoding="utf-8"))
                    inc_s = _df_to_stmt(inc_df)
                    bal_s = _df_to_stmt(bal_df)
                    cf_s = _df_to_stmt(cf_df)
                    hist_s = hist_df if hist_df is not None else pd.DataFrame()
                    checks = _actual_data_checks(info, inc_s, bal_s, cf_s, hist_s)
                    if checks["has_market_cap"] or checks["has_income_stmt"]:
                        return {
                            "symbol": symbol,
                            "source": "KDB-X Binary Cache (.kdb)",
                            "ingested_at": dt.datetime.fromtimestamp(meta_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                            "data_checks": checks,
                            "info": info,
                            "income_stmt": inc_s,
                            "balance_sheet": bal_s,
                            "cashflow": cf_s,
                            "history": hist_s,
                            "error": None,
                        }

        # Live fetch from Yahoo Finance
        try:
            tkr = yf.Ticker(symbol)
            info = tkr.info or {}
            inc = tkr.income_stmt
            bal = tkr.balance_sheet
            cf = tkr.cashflow
            hist = tkr.history(period="1y", auto_adjust=True)

            # Persist to KDB-X columnar binary cache
            meta_path.write_text(json.dumps(info, default=str), encoding="utf-8")
            inc_clean = _stmt_to_df(inc)
            bal_clean = _stmt_to_df(bal)
            cf_clean = _stmt_to_df(cf)
            if not inc_clean.empty:
                self.kdb.save_table(f"inc_{key}", inc_clean)
            if not bal_clean.empty:
                self.kdb.save_table(f"bal_{key}", bal_clean)
            if not cf_clean.empty:
                self.kdb.save_table(f"cf_{key}", cf_clean)
            if hist is not None and not hist.empty:
                h_save = hist.reset_index()
                self.kdb.save_table(f"hist_{key}", h_save)

            checks = _actual_data_checks(info, inc, bal, cf, hist)
            if not (checks["has_price"] or checks["has_market_cap"] or checks["has_income_stmt"]):
                return {
                    "symbol": symbol,
                    "source": "Yahoo Finance (No Data)",
                    "ingested_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "data_checks": checks,
                    "info": {},
                    "income_stmt": pd.DataFrame(),
                    "balance_sheet": pd.DataFrame(),
                    "cashflow": pd.DataFrame(),
                    "history": pd.DataFrame(),
                    "error": f"Strict actual-data guard: no verified quote or financial statements found for {symbol}.",
                }

            return {
                "symbol": symbol,
                "source": "Yahoo Finance -> KDB-X (.kdb)",
                "ingested_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "data_checks": checks,
                "info": info,
                "income_stmt": inc if inc is not None else pd.DataFrame(),
                "balance_sheet": bal if bal is not None else pd.DataFrame(),
                "cashflow": cf if cf is not None else pd.DataFrame(),
                "history": hist if hist is not None else pd.DataFrame(),
                "error": None,
            }
        except Exception as exc:
            return {
                "symbol": symbol,
                "source": "Error",
                "info": {},
                "income_stmt": pd.DataFrame(),
                "balance_sheet": pd.DataFrame(),
                "cashflow": pd.DataFrame(),
                "history": pd.DataFrame(),
                "error": str(exc),
            }

    def fetch_universe(
        self,
        symbols: List[str],
        force_refresh: bool = False,
        max_workers: int = 4,
    ) -> List[Dict[str, Any]]:
        """Fetch a list of symbols concurrently with bounded worker pool."""
        results: Dict[str, Dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(self.fetch_ticker_bundle, sym, force_refresh): sym
                for sym in symbols
            }
            for fut in as_completed(futures):
                sym = futures[fut]
                results[sym] = fut.result()
        return [results[s] for s in symbols if s in results]
