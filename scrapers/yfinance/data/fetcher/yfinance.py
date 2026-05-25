import math
import warnings
from datetime import datetime
from typing import Any, Dict, Optional

from .base import BaseFetcher, FetchResult, HistoryResult


class YFinanceFetcher(BaseFetcher):

    def __init__(self, proxy: Optional[str] = None) -> None:
        """
        Initialize YFinance fetcher.

        Args:
            proxy: Optional proxy URL (http://host:port or http://user:pass@host:port)
        """
        self._ticker: Optional[str] = None
        self._info: Optional[Dict[str, Any]] = None
        self._proxy = proxy

    @property
    def source_name(self) -> str:
        return "yfinance"

    def _get_ticker_obj(self, ticker: str) -> Any:
        try:
            import yfinance as yf

            # yfinance 1.3.0+ requires curl_cffi session for proxy support
            # Supports both HTTP and SOCKS5 proxies (SOCKS5 recommended for Yahoo Finance)
            # Format: socks5://host:port or http://host:port
            session = None
            if self._proxy:
                from curl_cffi import requests as curl_requests
                # impersonate="chrome" helps avoid bot detection
                session = curl_requests.Session(proxy=self._proxy, impersonate="chrome")

            return yf.Ticker(ticker, session=session)
        except ImportError as e:
            raise ImportError(
                "yfinance is required for US stock data. "
                "Install with: pip install valueinvest[us] or pip install yfinance"
            ) from e

    def fetch_quote(self, ticker: str) -> FetchResult:
        try:
            stock = self._get_ticker_obj(ticker)
            info = stock.info

            if not info:
                return FetchResult(
                    success=False,
                    data={},
                    source=self.source_name,
                    errors=[f"No data found for ticker: {ticker}"],
                    missing_fields=[],
                )

            # Start with ALL info fields from Yahoo Finance JSON
            # This preserves the complete Yahoo Finance API response including:
            # - companyOfficers (list of executives with compensation)
            # - address, city, state, zip, country, phone, website
            # - industry, sector, longBusinessSummary
            # - all price, volume, and ratio fields
            # - governance and risk metrics
            data = dict(info)

            # Ensure ticker is included
            data["ticker"] = ticker

            # Add normalized fields for backward compatibility
            shares = info.get("sharesOutstanding", 0) or info.get(
                "impliedSharesOutstanding", 0
            )

            # Override/add standardized field names for key fields
            # These provide consistent field names while preserving original Yahoo fields
            data.update({
                "name": info.get("longName", info.get("shortName", "")),
                "current_price": info.get("currentPrice", info.get("regularMarketPrice", 0)),
                "shares_outstanding": float(shares) if shares else 0.0,
                # Add market cap from Yahoo Finance
                "market_cap": info.get("marketCap", 0),
                # Add ratios from Yahoo Finance
                "pe_ratio": info.get("trailingPE", 0),
                "forward_pe": info.get("forwardPE", 0),
                "pb_ratio": info.get("priceToBook", 0),
                "ps_ratio": info.get("priceToSalesTrailing12Months", 0),
                "peg_ratio": info.get("pegRatio", 0),
                "dividend_yield": info.get("dividendYield", 0),
                # Add exchange and currency
                "currency": info.get("currency", "USD"),
                "exchange": info.get("exchange", ""),
                # Add sector and industry
                "sector": info.get("sector", ""),
                "industry": info.get("industry", ""),
            })

            # Track which standard fields are missing or zero
            standard_fields = [
                "ticker", "name", "current_price", "shares_outstanding", "market_cap",
                "pe_ratio", "pb_ratio", "dividend_yield", "currency", "exchange",
                "sector", "industry"
            ]
            missing = [k for k in standard_fields if k in data and (data[k] is None or data[k] == 0 or data[k] == "")]

            return FetchResult(
                success=True,
                data=data,
                source=self.source_name,
                errors=[],
                missing_fields=missing,
            )

        except Exception as e:
            return FetchResult(
                success=False,
                data={},
                source=self.source_name,
                errors=[str(e)],
                missing_fields=[],
            )

    def fetch_fundamentals(self, ticker: str) -> FetchResult:
        try:
            stock = self._get_ticker_obj(ticker)
            info = stock.info

            if not info:
                return FetchResult(
                    success=False,
                    data={},
                    source=self.source_name,
                    errors=[f"No fundamental data for ticker: {ticker}"],
                    missing_fields=[],
                )

            # Use new API names (income_stmt instead of deprecated financials)
            financials = stock.income_stmt
            balance_sheet = stock.balance_sheet
            cashflow = stock.cashflow

            # Start with ALL info fields from Yahoo Finance JSON
            # This preserves complete company data including:
            # - companyOfficers: List of executives with names, titles, ages, compensation
            # - Business description: longBusinessSummary, address, contact info
            # - Governance metrics: auditRisk, boardRisk, compensationRisk, etc.
            # - All financial ratios and metrics from Yahoo Finance
            data: Dict[str, Any] = dict(info)

            # Add raw financial statements as dictionaries
            if financials is not None and not financials.empty:
                data["financials_raw"] = financials.to_dict()
            if balance_sheet is not None and not balance_sheet.empty:
                data["balance_sheet_raw"] = balance_sheet.to_dict()
            if cashflow is not None and not cashflow.empty:
                data["cashflow_raw"] = cashflow.to_dict()

            # Add/override standardized fields for backward compatibility
            data.update({
                "eps": info.get("trailingEps", 0) or 0,
                "bvps": info.get("bookValue", 0) or 0,
                "revenue": info.get("totalRevenue", 0) or 0,
                "net_income": info.get("netIncomeToCommon", 0) or 0,
                "ebit": info.get("ebit", 0) or 0,
                "roe": (info.get("returnOnEquity", 0) or 0) * 100,
                "operating_margin": (info.get("operatingMargins", 0) or 0) * 100,
                "total_assets": info.get("totalAssets", 0) or 0,
                "current_assets": 0,
                "total_liabilities": info.get("totalDebt", 0) or 0,
                "net_debt": info.get("netDebt", 0) or 0,
                "net_working_capital": 0,
                "net_fixed_assets": 0,
                # TTM values from info (primary source, annual report is fallback)
                "fcf": float(info.get("freeCashflow", 0) or 0),
                "depreciation": 0,
                "capex": 0,
                "dividend_per_share": info.get("trailingAnnualDividendRate", 0) or 0,
                "dividend_growth_rate": 0,  # Will be calculated below
                "growth_rate": (info.get("revenueGrowth", 0) or 0) * 100,
                # TTM values from info (primary source)
                "ebitda": float(info.get("ebitda", 0) or 0),
                "earnings_growth": (info.get("earningsGrowth", 0) or 0) * 100,
                "revenue_growth": (info.get("revenueGrowth", 0) or 0) * 100,
                "operating_cash_flow": float(info.get("operatingCashflow", 0) or 0),
                "total_debt": float(info.get("totalDebt", 0) or 0),
                "cash_and_equivalents": float(info.get("totalCash", 0) or 0),
            })

            # Calculate dividend growth rate from dividend history
            try:
                dividends = stock.dividends
                if dividends is not None and len(dividends) >= 2:
                    # Get annual dividends by year
                    div_by_year = dividends.groupby(dividends.index.year).sum()
                    if len(div_by_year) >= 2:
                        # Use up to 10 years, excluding current (partial) year
                        current_year = datetime.now().year
                        full_years = div_by_year[div_by_year.index < current_year]
                        if len(full_years) >= 10:
                            full_years = full_years.iloc[-10:]
                        if len(full_years) >= 2:
                            years = len(full_years) - 1
                            older_div = float(full_years.iloc[0])
                            newer_div = float(full_years.iloc[-1])
                            if older_div > 0:
                                growth = ((newer_div / older_div) ** (1 / years) - 1) * 100
                                data["dividend_growth_rate"] = round(growth, 2)
            except Exception:
                pass

            # Income statement data (override info with financials where available)
            try:
                if financials is not None and not financials.empty:
                    if "Total Revenue" in financials.index:
                        data["revenue"] = float(financials.loc["Total Revenue"].iloc[0])
                    if "Net Income" in financials.index:
                        data["net_income"] = float(financials.loc["Net Income"].iloc[0])
                    if "EBIT" in financials.index:
                        data["ebit"] = float(financials.loc["EBIT"].iloc[0])
                    if "EBITDA" in financials.index:
                        data["ebitda"] = float(financials.loc["EBITDA"].iloc[0])
                    if "Depreciation" in financials.index:
                        data["depreciation"] = float(financials.loc["Depreciation"].iloc[0])
                    if "Gross Profit" in financials.index:
                        data["gross_profit"] = float(financials.loc["Gross Profit"].iloc[0])
                    # Interest expense (for WACC and interest coverage)
                    if "Interest Expense" in financials.index:
                        ie_series = financials.loc["Interest Expense"]
                        # Find first non-NaN value (latest year may be NaN)
                        for val in ie_series:
                            if val == val:  # NaN check (NaN != NaN)
                                data["interest_expense"] = abs(float(val))
                                break
                    if data.get("interest_expense", 0) == 0 and "Interest Income" in financials.index:
                        # Net interest: try to find both expense and income
                        ie_series = financials.loc.get("Interest Expense")
                        ii_series = financials.loc.get("Interest Income")
                        ie_val = 0.0
                        ii_val = 0.0
                        if ie_series is not None:
                            for val in ie_series:
                                if val == val:
                                    ie_val = float(val)
                                    break
                        if ii_series is not None:
                            for val in ii_series:
                                if val == val:
                                    ii_val = float(val)
                                    break
                        if ie_val != 0 or ii_val != 0:
                            data["interest_expense"] = abs(ie_val - ii_val)
                    # Compute tax rate from income statement
                    if "Tax Provision" in financials.index and "Pretax Income" in financials.index:
                        tax = abs(float(financials.loc["Tax Provision"].iloc[0]))
                        pretax = float(financials.loc["Pretax Income"].iloc[0])
                        if pretax > 0 and tax > 0:
                            data["tax_rate"] = round((tax / pretax) * 100, 2)
            except (KeyError, IndexError, TypeError):
                pass

            # Balance sheet data
            try:
                if balance_sheet is not None and not balance_sheet.empty:
                    if "Total Assets" in balance_sheet.index:
                        data["total_assets"] = float(balance_sheet.loc["Total Assets"].iloc[0])
                    if "Current Assets" in balance_sheet.index:
                        data["current_assets"] = float(
                            balance_sheet.loc["Current Assets"].iloc[0]
                        )
                    if "Total Liabilities Net Minority Interest" in balance_sheet.index:
                        data["total_liabilities"] = float(
                            balance_sheet.loc["Total Liabilities Net Minority Interest"].iloc[0]
                        )
                    if "Total Debt" in balance_sheet.index:
                        data["total_debt"] = float(balance_sheet.loc["Total Debt"].iloc[0])
                    if "Long Term Debt" in balance_sheet.index:
                        data["long_term_debt"] = float(balance_sheet.loc["Long Term Debt"].iloc[0])
                    if "Current Debt" in balance_sheet.index:
                        data["short_term_debt"] = float(balance_sheet.loc["Current Debt"].iloc[0])
                    if "Cash And Cash Equivalents" in balance_sheet.index:
                        data["cash_and_equivalents"] = float(
                            balance_sheet.loc["Cash And Cash Equivalents"].iloc[0]
                        )
                    if "Inventory" in balance_sheet.index:
                        data["inventory"] = float(balance_sheet.loc["Inventory"].iloc[0])
                    if "Accounts Receivable" in balance_sheet.index:
                        data["accounts_receivable"] = float(
                            balance_sheet.loc["Accounts Receivable"].iloc[0]
                        )
                    if "Accounts Payable" in balance_sheet.index:
                        data["accounts_payable"] = float(
                            balance_sheet.loc["Accounts Payable"].iloc[0]
                        )
                    if "Retained Earnings" in balance_sheet.index:
                        data["retained_earnings"] = float(
                            balance_sheet.loc["Retained Earnings"].iloc[0]
                        )
                    if "Current Liabilities" in balance_sheet.index:
                        data["current_liabilities"] = float(
                            balance_sheet.loc["Current Liabilities"].iloc[0]
                        )
                    # Populate net_working_capital and net_fixed_assets
                    if "Working Capital" in balance_sheet.index:
                        data["net_working_capital"] = float(
                            balance_sheet.loc["Working Capital"].iloc[0]
                        )
                    if "Net PPE" in balance_sheet.index:
                        data["net_fixed_assets"] = float(
                            balance_sheet.loc["Net PPE"].iloc[0]
                        )
            except (KeyError, IndexError, TypeError):
                pass

            # Cash flow data — prefer cashflow statement over info TTM values
            # because yfinance info['freeCashflow'] can be inaccurate
            # (e.g. META FY2025: info says $25B vs cashflow statement $46B)
            try:
                if cashflow is not None and not cashflow.empty:
                    if "Operating Cash Flow" in cashflow.index:
                        ocf_val = float(cashflow.loc["Operating Cash Flow"].iloc[0])
                        if data.get("operating_cash_flow", 0) == 0:
                            data["operating_cash_flow"] = ocf_val
                    if "Free Cash Flow" in cashflow.index:
                        fcf_val = float(cashflow.loc["Free Cash Flow"].iloc[0])
                        # Always prefer cashflow statement FCF over info TTM
                        data["fcf"] = fcf_val
                    elif "Operating Cash Flow" in cashflow.index and "Capital Expenditure" in cashflow.index:
                        # Calculate FCF = OCF + CapEx (CapEx is negative)
                        ocf = float(cashflow.loc["Operating Cash Flow"].iloc[0])
                        capex = float(cashflow.loc["Capital Expenditure"].iloc[0])
                        data["fcf"] = ocf + capex
                    if "Capital Expenditure" in cashflow.index:
                        # Store as positive value representing expenditure
                        raw_capex = float(cashflow.loc["Capital Expenditure"].iloc[0])
                        data["capex"] = abs(raw_capex)
                    if "Depreciation And Amortization" in cashflow.index:
                        data["depreciation"] = float(
                            cashflow.loc["Depreciation And Amortization"].iloc[0]
                        )
                    # SBC data
                    if "Stock Based Compensation" in cashflow.index:
                        data["sbc"] = float(cashflow.loc["Stock Based Compensation"].iloc[0])
                    # Share issuance/repurchase (financing activities)
                    if "Issuance Of Stock" in cashflow.index:
                        data["shares_issued"] = abs(float(cashflow.loc["Issuance Of Stock"].iloc[0]))
                    if "Repurchase Of Stock" in cashflow.index:
                        data["shares_repurchased"] = abs(float(cashflow.loc["Repurchase Of Stock"].iloc[0]))
            except (KeyError, IndexError, TypeError):
                pass

            # Compute net_debt from balance sheet if yfinance doesn't provide it
            if data.get("net_debt", 0) == 0 and data.get("total_debt", 0) > 0:
                cash = data.get("cash_and_equivalents", 0) or 0
                data["net_debt"] = data["total_debt"] - cash

            # Compute gross margin
            if "gross_profit" in data and data.get("revenue", 0) > 0:
                data["_gross_margin"] = (data["gross_profit"] / data["revenue"]) * 100

            # Compute current year ratios for prior_* comparison
            try:
                if data.get("total_assets", 0) > 0 and data.get("net_income", 0) > 0:
                    data["_roa"] = (data["net_income"] / data["total_assets"]) * 100
                if data.get("total_assets", 0) > 0 and data.get("total_liabilities", 0) > 0:
                    data["_debt_ratio"] = (data["total_liabilities"] / data["total_assets"]) * 100
                if data.get("current_liabilities", 0) > 0 and data.get("current_assets", 0) > 0:
                    data["_current_ratio"] = data["current_assets"] / data["current_liabilities"]
                if data.get("total_assets", 0) > 0 and data.get("revenue", 0) > 0:
                    data["_asset_turnover"] = data["revenue"] / data["total_assets"]
            except (TypeError, ZeroDivisionError):
                pass

            # Prior year data (second column, index 1) for F-Score and trend analysis
            try:
                if financials is not None and not financials.empty and len(financials.columns) >= 2:
                    prior_net_income = 0.0
                    prior_revenue = 0.0
                    prior_gross_profit = 0.0
                    prior_total_assets = 0.0
                    prior_total_liabilities = 0.0
                    prior_current_assets = 0.0
                    prior_current_liabilities = 0.0
                    prior_shares = 0.0

                    if "Net Income" in financials.index:
                        prior_net_income = float(financials.loc["Net Income"].iloc[1])
                    if "Total Revenue" in financials.index:
                        prior_revenue = float(financials.loc["Total Revenue"].iloc[1])
                    if "Gross Profit" in financials.index:
                        prior_gross_profit = float(financials.loc["Gross Profit"].iloc[1])
                    if "Diluted Average Shares" in financials.index:
                        prior_shares = float(financials.loc["Diluted Average Shares"].iloc[1])

                    # Prior balance sheet
                    if balance_sheet is not None and not balance_sheet.empty and len(balance_sheet.columns) >= 2:
                        if "Total Assets" in balance_sheet.index:
                            prior_total_assets = float(balance_sheet.loc["Total Assets"].iloc[1])
                        if "Total Liabilities Net Minority Interest" in balance_sheet.index:
                            prior_total_liabilities = float(
                                balance_sheet.loc["Total Liabilities Net Minority Interest"].iloc[1]
                            )
                        if "Current Assets" in balance_sheet.index:
                            prior_current_assets = float(
                                balance_sheet.loc["Current Assets"].iloc[1]
                            )
                        if "Current Liabilities" in balance_sheet.index:
                            prior_current_liabilities = float(
                                balance_sheet.loc["Current Liabilities"].iloc[1]
                            )

                    # Compute prior ROA
                    if prior_total_assets > 0 and prior_net_income != 0:
                        data["prior_roa"] = (prior_net_income / prior_total_assets) * 100

                    # Compute prior debt ratio
                    if prior_total_assets > 0 and prior_total_liabilities != 0:
                        data["prior_debt_ratio"] = (
                            prior_total_liabilities / prior_total_assets
                        ) * 100

                    # Compute prior current ratio
                    if prior_current_liabilities > 0 and prior_current_assets != 0:
                        data["prior_current_ratio"] = prior_current_assets / prior_current_liabilities

                    # Prior shares outstanding
                    if prior_shares > 0:
                        data["prior_shares_outstanding"] = prior_shares

                    # Prior gross margin
                    if prior_revenue > 0 and prior_gross_profit != 0:
                        data["prior_gross_margin"] = (prior_gross_profit / prior_revenue) * 100

                    # Prior asset turnover
                    if prior_total_assets > 0 and prior_revenue != 0:
                        data["prior_asset_turnover"] = prior_revenue / prior_total_assets
            except (KeyError, IndexError, TypeError):
                pass

            # 5-year CAGR calculations (use valid non-NaN values)
            try:
                if financials is not None and not financials.empty and len(financials.columns) >= 2:
                    revenues = financials.loc["Total Revenue"].values
                    net_incomes = financials.loc["Net Income"].values

                    # Drop NaN values, keep only valid positive numbers
                    valid_revenues = [v for v in revenues if not math.isnan(v) and v > 0]
                    valid_incomes = [v for v in net_incomes if not math.isnan(v) and v > 0]

                    # Revenue CAGR (use up to 5 years of data)
                    if len(valid_revenues) >= 2:
                        years = len(valid_revenues) - 1
                        r_cagr = (valid_revenues[0] / valid_revenues[-1]) ** (1 / years) - 1
                        data["revenue_cagr_5y"] = round(r_cagr * 100, 2)

                    # Earnings CAGR (use up to 5 years of data)
                    if len(valid_incomes) >= 2:
                        years = len(valid_incomes) - 1
                        e_cagr = (valid_incomes[0] / valid_incomes[-1]) ** (1 / years) - 1
                        data["earnings_cagr_5y"] = round(e_cagr * 100, 2)
            except (KeyError, IndexError, TypeError, ZeroDivisionError):
                pass

            # Historical PE/PB data for relative valuation (Task 1)
            try:
                shares = info.get("sharesOutstanding", 0) or info.get(
                    "impliedSharesOutstanding", 0
                )
                shares = float(shares) if shares else 0.0

                if shares > 0 and ((financials is not None and not financials.empty) or (balance_sheet is not None and not balance_sheet.empty)):
                    hist = stock.history(period="5y")
                    if hist is not None and not hist.empty:
                        # Resample to yearly average prices
                        yearly_avg = hist["Close"].resample("YE").mean()

                        historical_pe_data = []
                        historical_pb_data = []
                        historical_pe_list = []
                        historical_pb_list = []

                        # Build year -> avg_price mapping
                        price_by_year = {}
                        for date_idx, avg_price in yearly_avg.items():
                            yr = date_idx.year
                            price_by_year[yr] = float(avg_price)

                        # Get annual EPS from financials columns (each col = a fiscal year)
                        eps_by_year = {}
                        if financials is not None and not financials.empty and "Diluted EPS" in financials.index:
                            for col in financials.columns:
                                yr = col.year if hasattr(col, "year") else int(str(col)[:4])
                                eps_by_year[yr] = float(financials.loc["Diluted EPS"][col])
                        # Fallback: compute EPS from net income / shares per year
                        if not eps_by_year and financials is not None and not financials.empty and "Net Income" in financials.index and "Diluted Average Shares" in financials.index:
                            for col in financials.columns:
                                yr = col.year if hasattr(col, "year") else int(str(col)[:4])
                                ni = float(financials.loc["Net Income"][col])
                                sh = float(financials.loc["Diluted Average Shares"][col])
                                if sh > 0:
                                    eps_by_year[yr] = ni / sh

                        # Get annual BVPS from balance sheet
                        bvps_by_year = {}
                        if balance_sheet is not None and not balance_sheet.empty:
                            equity_row = None
                            for equity_name in ["Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity"]:
                                if equity_name in balance_sheet.index:
                                    equity_row = balance_sheet.loc[equity_name]
                                    break
                            if equity_row is not None:
                                for col in balance_sheet.columns:
                                    yr = col.year if hasattr(col, "year") else int(str(col)[:4])
                                    equity = float(equity_row[col])
                                    bvps_by_year[yr] = equity / shares if shares > 0 else 0

                        # Build historical PE data
                        for yr in sorted(price_by_year.keys()):
                            avg_price = price_by_year[yr]
                            eps = eps_by_year.get(yr)
                            if eps and eps > 0:
                                pe = avg_price / eps
                                historical_pe_data.append({
                                    "year": yr,
                                    "eps": round(eps, 4),
                                    "avg_price": round(avg_price, 2),
                                    "pe": round(pe, 2),
                                })
                                historical_pe_list.append(round(pe, 2))

                        # Build historical PB data
                        for yr in sorted(price_by_year.keys()):
                            avg_price = price_by_year[yr]
                            bvps = bvps_by_year.get(yr)
                            if bvps and bvps > 0:
                                pb = avg_price / bvps
                                historical_pb_data.append({
                                    "year": yr,
                                    "bvps": round(bvps, 4),
                                    "avg_price": round(avg_price, 2),
                                    "pb": round(pb, 2),
                                })
                                historical_pb_list.append(round(pb, 2))

                        data["historical_pe_data"] = historical_pe_data
                        data["historical_pb_data"] = historical_pb_data
                        data["historical_pe"] = historical_pe_list
                        data["historical_pb"] = historical_pb_list
            except Exception:
                pass

            missing = [k for k, v in data.items() if v is None or v == 0]

            return FetchResult(
                success=True,
                data=data,
                source=self.source_name,
                errors=[],
                missing_fields=missing,
            )

        except Exception as e:
            return FetchResult(
                success=False,
                data={},
                source=self.source_name,
                errors=[str(e)],
                missing_fields=[],
            )

    def fetch_all(self, ticker: str) -> FetchResult:
        quote = self.fetch_quote(ticker)
        fundamentals = self.fetch_fundamentals(ticker)

        combined = {**fundamentals.data, **quote.data}

        # Fetch additional yfinance data
        try:
            stock = self._get_ticker_obj(ticker)

            # Dividends history
            try:
                dividends = stock.dividends
                if dividends is not None and not dividends.empty:
                    combined["dividends_history"] = dividends.to_dict()
            except Exception:
                pass

            # Stock splits history
            try:
                splits = stock.splits
                if splits is not None and not splits.empty:
                    combined["splits_history"] = splits.to_dict()
            except Exception:
                pass

            # Actions (dividends + splits combined)
            try:
                actions = stock.actions
                if actions is not None and not actions.empty:
                    combined["actions_history"] = actions.to_dict()
            except Exception:
                pass

            # Analyst recommendations (suppress yfinance warnings)
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    recommendations = stock.recommendations
                    if recommendations is not None and not recommendations.empty:
                        combined["recommendations"] = recommendations.to_dict()
            except Exception:
                pass

            # Earnings dates (suppress yfinance warnings about delisted/missing data)
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    earnings_dates = stock.earnings_dates
                    if earnings_dates is not None and not earnings_dates.empty:
                        combined["earnings_dates"] = earnings_dates.to_dict()
            except Exception:
                pass

            # Quarterly earnings (using new API)
            try:
                # Use quarterly_income_stmt instead of deprecated quarterly_earnings
                quarterly_income = stock.quarterly_income_stmt
                if quarterly_income is not None and not quarterly_income.empty:
                    combined["quarterly_earnings"] = quarterly_income.to_dict()
            except Exception:
                pass

            # Quarterly financials (using new API)
            try:
                # Use quarterly_income_stmt instead of deprecated quarterly_financials
                quarterly_income_stmt = stock.quarterly_income_stmt
                if quarterly_income_stmt is not None and not quarterly_income_stmt.empty:
                    combined["quarterly_financials"] = quarterly_income_stmt.to_dict()
            except Exception:
                pass

            # Quarterly balance sheet
            try:
                quarterly_balance_sheet = stock.quarterly_balance_sheet
                if quarterly_balance_sheet is not None and not quarterly_balance_sheet.empty:
                    combined["quarterly_balance_sheet"] = quarterly_balance_sheet.to_dict()
            except Exception:
                pass

            # Quarterly cashflow
            try:
                quarterly_cashflow = stock.quarterly_cashflow
                if quarterly_cashflow is not None and not quarterly_cashflow.empty:
                    combined["quarterly_cashflow"] = quarterly_cashflow.to_dict()
            except Exception:
                pass

            # Major holders (suppress warnings)
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    major_holders = stock.major_holders
                    if major_holders is not None and not major_holders.empty:
                        combined["major_holders"] = major_holders.to_dict()
            except Exception:
                pass

            # Institutional holders (suppress warnings)
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    institutional_holders = stock.institutional_holders
                    if institutional_holders is not None and not institutional_holders.empty:
                        combined["institutional_holders"] = institutional_holders.to_dict()
            except Exception:
                pass

            # Mutualfund holders (suppress warnings)
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    mutualfund_holders = stock.mutualfund_holders
                    if mutualfund_holders is not None and not mutualfund_holders.empty:
                        combined["mutualfund_holders"] = mutualfund_holders.to_dict()
            except Exception:
                pass

            # Insider transactions (suppress warnings)
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    insider_transactions = stock.insider_transactions
                    if insider_transactions is not None and not insider_transactions.empty:
                        combined["insider_transactions"] = insider_transactions.to_dict()
            except Exception:
                pass

            # Insider purchases (suppress warnings)
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    insider_purchases = stock.insider_purchases
                    if insider_purchases is not None and not insider_purchases.empty:
                        combined["insider_purchases"] = insider_purchases.to_dict()
            except Exception:
                pass

            # Insider roster holders (suppress warnings)
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    insider_roster_holders = stock.insider_roster_holders
                    if insider_roster_holders is not None and not insider_roster_holders.empty:
                        combined["insider_roster_holders"] = insider_roster_holders.to_dict()
            except Exception:
                pass

            # Options expiration dates (suppress warnings)
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    options_dates = stock.options
                    if options_dates:
                        combined["options_expiration_dates"] = list(options_dates)
            except Exception:
                pass

        except Exception as e:
            combined["additional_data_errors"] = str(e)

        missing = [k for k, v in combined.items() if v is None or v == 0]

        return FetchResult(
            success=quote.success or fundamentals.success,
            data=combined,
            source=self.source_name,
            errors=quote.errors + fundamentals.errors,
            missing_fields=missing,
        )

    def fetch_history(
        self,
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: str = "5y",
        adjust: str = "qfq",
    ) -> HistoryResult:
        try:
            stock = self._get_ticker_obj(ticker)

            if start_date and end_date:
                df = stock.history(start=start_date, end=end_date)
            else:
                period_map = {
                    "1y": "1y",
                    "2y": "2y",
                    "3y": "3y",
                    "5y": "5y",
                    "10y": "10y",
                    "max": "max",
                }
                yf_period = period_map.get(period.lower(), "5y")
                df = stock.history(period=yf_period)

            if df is None or df.empty:
                return HistoryResult(
                    success=False,
                    ticker=ticker,
                    source=self.source_name,
                    errors=[f"No historical data for {ticker}"],
                )

            df = df.rename(columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            })
            df = df[["open", "high", "low", "close", "volume"]]
            df = df.sort_index()

            dates = df.index.tolist()
            start_dt = dates[0].date() if dates else None
            end_dt = dates[-1].date() if dates else None

            return HistoryResult(
                success=True,
                ticker=ticker,
                source=self.source_name,
                df=df,
                start_date=start_dt,
                end_date=end_dt,
            )

        except Exception as e:
            return HistoryResult(
                success=False,
                ticker=ticker,
                source=self.source_name,
                errors=[str(e)],
            )