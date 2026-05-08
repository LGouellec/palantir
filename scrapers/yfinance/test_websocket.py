"""
Quick test app for yfinance WebSocket real-time streaming.

Tests real-time price updates for a few tickers.
"""
import asyncio
import logging
import ssl
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# SSL context for WebSocket connections
# For testing purposes, we'll use certifi certificates or disable verification
try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except (ImportError, Exception):
    # If certifi not available, create context without verification (testing only)
    SSL_CONTEXT = ssl._create_unverified_context()
    logger.warning("⚠️  Using unverified SSL context (testing only)")


async def _run_polling_mode(tickers):
    """Fallback polling mode when WebSocket is not available."""
    logger.info("Press Ctrl+C to stop")
    logger.info("")

    for i in range(20):  # Run for ~100 seconds
        logger.info(f"--- Iteration {i + 1} ---")
        for ticker in tickers:
            try:
                import yfinance as yf
                stock = yf.Ticker(ticker)
                info = stock.info
                price = info.get('regularMarketPrice') or info.get('currentPrice', 0)
                change = info.get('regularMarketChangePercent', 0)

                if price:
                    change_str = f"{change:+.2f}%" if change else "N/A"
                    logger.info(f"  💹 {ticker}: ${price:.2f} ({change_str})")
            except Exception as e:
                logger.error(f"  ❌ {ticker}: Error - {str(e)[:50]}")

        logger.info("")
        await asyncio.sleep(5)


async def test_websocket():
    """Test yfinance WebSocket for real-time data."""
    try:
        import yfinance as yf

        logger.info("=" * 70)
        logger.info("YFinance WebSocket Real-Time Test")
        logger.info("=" * 70)
        logger.info("")

        # Test tickers
        tickers = ["AAPL", "GOOGL", "MSFT", "NVDA", "META"]
        # tickers = ["IBM"]
        logger.info(f"📡 Subscribing to real-time updates for: {', '.join(tickers)}")
        logger.info("")

        # Create ticker objects
        ticker_objects = [yf.Ticker(t) for t in tickers]

        # Check if WebSocket is available
        if not hasattr(yf, 'WebSocket'):
            logger.warning("⚠️  yfinance.WebSocket not found in this version")
            logger.info("📋 Available real-time options:")
            logger.info("   1. Use stock.history(period='1d', interval='1m') for 1-minute bars")
            logger.info("   2. Poll stock.info['regularMarketPrice'] regularly")
            logger.info("   3. Use websocket-client library with Yahoo Finance WebSocket directly")
            logger.info("")

            # Fallback: polling demo
            logger.info("🔄 Falling back to polling mode (fetching every 5 seconds)...")
            await _run_polling_mode(tickers)
            return

        # If WebSocket is available, try to use it
        logger.info("✅ WebSocket support detected!")
        logger.info("🔌 Connecting to Yahoo Finance WebSocket...")
        logger.info("")

        try:
            # Create WebSocket connection and subscribe
            # Note: SSL verification may fail on some systems
            import os
            os.environ['PYTHONHTTPSVERIFY'] = '0'  # Disable SSL verification for testing

            ws = yf.WebSocket()
            ws.subscribe(tickers)

            # Message counter
            message_count = 0
            max_messages = 50  # Stop after 50 messages

            logger.info("✅ WebSocket created and subscribed!")
            logger.info(f"📡 Listening for real-time updates on: {', '.join(tickers)}")
            logger.info("   (Receiving data for ~30 seconds)")
            logger.info("")

            # Listen for messages
            start_time = datetime.now()
            timeout = 30  # seconds

            try:
                for message in ws.listen():
                    message_count += 1

                    try:
                        # Parse message based on yfinance WebSocket format
                        ticker = message.get('id', message.get('symbol', 'UNKNOWN'))
                        price = message.get('price', message.get('regularMarketPrice', 0))
                        change_pct = message.get('changePercent', message.get('regularMarketChangePercent', 0))
                        volume = message.get('dayVolume', message.get('regularMarketVolume', 0))

                        # Get timestamp
                        msg_time = message.get('time', message.get('regularMarketTime'))
                        if msg_time:
                            if isinstance(msg_time, (int, float)):
                                timestamp = datetime.fromtimestamp(msg_time)
                            else:
                                timestamp = datetime.now()
                        else:
                            timestamp = datetime.now()

                        logger.info(
                            f"📊 {ticker}: ${price:.2f} "
                            f"({change_pct:+.2f}%) "
                            f"Vol: {volume:,} "
                            f"@ {timestamp.strftime('%H:%M:%S')}"
                        )

                        # Stop after max_messages or timeout
                        if message_count >= max_messages:
                            logger.info("")
                            logger.info(f"✅ Received {max_messages} messages. Stopping test.")
                            break

                        elapsed = (datetime.now() - start_time).total_seconds()
                        if elapsed >= timeout:
                            logger.info("")
                            logger.info(f"⏱️  Timeout reached ({timeout}s). Stopping test.")
                            logger.info(f"   Total messages received: {message_count}")
                            break

                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
                        logger.debug(f"Message content: {message}")

            finally:
                ws.close()

            logger.info("")
            logger.info("🔌 WebSocket test complete")
            logger.info(f"   Total messages received: {message_count}")

        except ssl.SSLError as e:
            # SSL certificate error - fall back to polling
            logger.warning(f"⚠️  WebSocket SSL error: {e}")
            logger.info("")
            logger.info("💡 To fix SSL errors on macOS:")
            logger.info("   1. Run: /Applications/Python\\ 3.12/Install\\ Certificates.command")
            logger.info("   2. Or install certifi: pip install certifi")
            logger.info("")
            logger.info("🔄 Falling back to polling mode...")
            logger.info("")

            # Fall through to polling mode below
            await _run_polling_mode(tickers)
            return

        except Exception as e:
            # Other WebSocket errors - fall back to polling
            logger.warning(f"⚠️  WebSocket connection failed: {e}")
            logger.info("🔄 Falling back to polling mode...")
            logger.info("")

            # Fall through to polling mode below
            await _run_polling_mode(tickers)
            return

    except ImportError:
        logger.error("❌ yfinance not installed. Install with: pip install yfinance")
    except KeyboardInterrupt:
        logger.info("\n\n🛑 Stopped by user")
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


async def test_direct_websocket():
    """
    Test using websocket-client library directly with Yahoo Finance.

    This is an alternative if yfinance doesn't expose WebSocket API.
    """
    logger.info("=" * 70)
    logger.info("Direct Yahoo Finance WebSocket Test")
    logger.info("=" * 70)
    logger.info("")

    try:
        import websocket
        import json

        # Yahoo Finance WebSocket URL
        url = "wss://streamer.finance.yahoo.com/"

        tickers = ["AAPL", "GOOGL", "MSFT", "NVDA", "META"]

        def on_message(ws, message):
            try:
                data = json.loads(message)
                logger.info(f"📨 Message: {data}")
            except Exception as e:
                logger.error(f"Error parsing message: {e}")

        def on_error(ws, error):
            logger.error(f"❌ WebSocket Error: {error}")

        def on_close(ws, close_status_code, close_msg):
            logger.info("🔌 WebSocket connection closed")

        def on_open(ws):
            logger.info("✅ WebSocket connected!")
            logger.info(f"📡 Subscribing to: {', '.join(tickers)}")

            # Subscribe to tickers
            subscribe_message = {
                "subscribe": tickers
            }
            ws.send(json.dumps(subscribe_message))

        # Create WebSocket
        ws = websocket.WebSocketApp(
            url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )

        # Run
        ws.run_forever()

    except ImportError:
        logger.error("❌ websocket-client not installed. Install with: pip install websocket-client")
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Main entry point."""
    logger.info("\n")
    logger.info("╔══════════════════════════════════════════════════════════════════════╗")
    logger.info("║          YFinance Real-Time WebSocket Test                           ║")
    logger.info("╚══════════════════════════════════════════════════════════════════════╝")
    logger.info("\n")

    try:
        # Try yfinance WebSocket first
        await test_websocket()
    except KeyboardInterrupt:
        logger.info("\n🛑 Test stopped by user")
    except Exception as e:
        logger.error(f"Test failed: {e}")

        # Ask if user wants to try direct WebSocket
        logger.info("\nWould you like to try direct WebSocket connection?")
        logger.info("This requires: pip install websocket-client")
        # Uncomment to test direct WebSocket:
        # await test_direct_websocket()


if __name__ == "__main__":
    asyncio.run(main())
