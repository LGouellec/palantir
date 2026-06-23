import yfinance as yf

ticker = 'AAPL' # Replace with your stock symbol
data = yf.download(ticker, start='2026-01-01', end='2026-06-22')

data.to_csv(f'{ticker}_historical_data.csv')

# Manually rename columns and remove date