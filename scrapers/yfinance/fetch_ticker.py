from data.fetcher.yfinance import YFinanceFetcher
from news.fetcher.yfinance import YFinanceNewsFetcher

fetcher = YFinanceFetcher()
newsFetcher = YFinanceNewsFetcher()

# msft = fetcher.fetch_quote("MSFT")
# print(msft)

print(fetcher.fetch_fundamentals("MSFT"))

#newsMsft = newsFetcher.fetch_all("MSFT", include_guidance=True)
#print(newsMsft)