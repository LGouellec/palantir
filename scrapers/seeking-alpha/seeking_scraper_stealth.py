#!/usr/bin/env python3
"""
Seeking Alpha News Scraper - Stealth Mode
Uses Scrapling's StealthyFetcher for enhanced anti-bot avoidance
"""

# https://github.com/Pr0t0ns/perimeterx-solution
# https://github.com/ph00lt0/blocklist

import json
import time
import os
import sys
import random
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

# Add parent directory to path for common module imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scrapling.fetchers import StealthyFetcher
from playwright.sync_api import Page
from common.mouvement.human import HumanMouseSimulator
from seeking_scraper_base import SeekingScraperBase


class SeekingScraperStealth(SeekingScraperBase):
    """
    Seeking Alpha Scraper using Scrapling's StealthyFetcher for anti-bot avoidance

    Features:
    - Automatic browser context cleanup after consecutive 403 errors
    - Graceful Playwright process shutdown (SIGTERM → SIGKILL fallback)
    - Persistent browser session management via user_data_dir
    - Login and captcha handling with human-like interactions

    Note: StealthyFetcher manages Playwright instances internally, so cleanup is
    done at the process level. For more granular control, consider using
    playwright.sync_api directly with proper context managers.
    """

    def __init__(
        self,
        output_dir: str = "news",
        headless: bool = True,
        verbose: bool = False,
        api_base_url: str = "https://seekingalpha.com/api/v3/news",
        article_base_url: str = "https://seekingalpha.com/news",
        category: str = "market-news::all",
        history_file: str = "scraped_history.json",
        kafka_enabled: bool = False,
        kafka_bootstrap_servers: str = "localhost:9092",
        kafka_topic: str = "seeking-news",
        kafka_config_file: Optional[str] = None,
        login_email: Optional[str] = None,
        login_password: Optional[str] = None,
        history_ttl_days: Optional[int] = None
    ):
        # Call parent constructor
        super().__init__(
            output_dir=output_dir,
            verbose=verbose,
            api_base_url=api_base_url,
            article_base_url=article_base_url,
            category=category,
            history_file=history_file,
            kafka_enabled=kafka_enabled,
            kafka_bootstrap_servers=kafka_bootstrap_servers,
            kafka_topic=kafka_topic,
            kafka_config_file=kafka_config_file,
            history_ttl_days=history_ttl_days
        )

        # Stealth-specific attributes
        self.headless = headless
        self.login_email = login_email
        self.login_password = login_password
        self.user_data_dir = "./chrome_seeking"  # Persistent browser context

        # Track consecutive 403 errors for browser context reset
        self.consecutive_403_count = 0
        self.max_consecutive_403 = 3

        # Enable Scrapling's adaptive mode for future-proofing
        StealthyFetcher.adaptive = True

    def _cleanup_browser_context(self) -> None:
        """
        Clean up persistent browser context and cookies after consecutive 403 errors.

        Uses process-level cleanup (SIGTERM → SIGKILL) to terminate Playwright instances
        managed internally by StealthyFetcher, then deletes the browser context directory
        and session cookies to force a fresh start.
        """
        self.logger.warning(f"🧹 Cleaning up browser context after {self.consecutive_403_count} consecutive 403 errors")
        print(f"⚠️  Detected {self.consecutive_403_count} consecutive 403 errors - resetting browser context...")

        try:
            # StealthyFetcher manages Playwright instances internally, so we use
            # process-level cleanup since we don't have direct access to browser objects
            try:
                # Check if pgrep/pkill are available (may not be in Docker containers)
                pgrep_available = subprocess.run(
                    ['which', 'pgrep'],
                    capture_output=True,
                    timeout=2
                ).returncode == 0

                if pgrep_available:
                    self.logger.debug("Attempting graceful Playwright shutdown with SIGTERM...")
                    result = subprocess.run(
                        ['pgrep', '-f', 'playwright'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )

                    if result.returncode == 0 and result.stdout.strip():
                        # Playwright processes found
                        pids = result.stdout.strip().split('\n')
                        self.logger.debug(f"Found {len(pids)} Playwright process(es), sending SIGTERM...")

                        # Send SIGTERM for graceful shutdown
                        subprocess.run(['pkill', '-15', '-f', 'playwright'], stderr=subprocess.DEVNULL, timeout=5)

                        # Wait up to 5 seconds for graceful shutdown
                        for _ in range(10):
                            time.sleep(0.5)
                            check = subprocess.run(
                                ['pgrep', '-f', 'playwright'],
                                capture_output=True,
                                timeout=5
                            )
                            if check.returncode != 0:
                                self.logger.debug("Playwright processes shut down gracefully")
                                break
                        else:
                            # If still running after 5 seconds, force kill
                            self.logger.warning("Graceful shutdown timeout, forcing SIGKILL...")
                            subprocess.run(['pkill', '-9', '-f', 'playwright'], stderr=subprocess.DEVNULL, timeout=5)
                            time.sleep(1)
                            self.logger.debug("Forced Playwright process termination")
                    else:
                        self.logger.debug("No Playwright processes found")
                else:
                    self.logger.debug("pgrep/pkill not available (common in Docker), relying on context cleanup")
                    # In Docker without process tools, just wait a bit for processes to settle
                    time.sleep(2)

            except subprocess.TimeoutExpired:
                self.logger.warning("Process check timed out")
            except FileNotFoundError:
                self.logger.debug("Process management tools not found (Docker environment), skipping process cleanup")
                time.sleep(2)
            except Exception as e:
                self.logger.debug(f"Process cleanup note: {e}")
                time.sleep(2)

            # Additional wait for full cleanup
            time.sleep(1)

            # Delete persistent browser context directory
            user_data_path = Path(self.user_data_dir)
            if user_data_path.exists():
                self.logger.info(f"Deleting browser context directory: {user_data_path}")
                shutil.rmtree(user_data_path, ignore_errors=True)
                self.logger.info("✓ Browser context directory deleted")

            # Clear session cookies in memory
            self.session_cookies = []

            # Reset consecutive error counter
            self.consecutive_403_count = 0

            # Give the system time to fully clean up
            time.sleep(3)

            self.logger.info("✅ Browser context cleanup complete - starting fresh")
            print("✅ Browser context reset complete - will retry with fresh session")

        except Exception as e:
            self.logger.error(f"Error during browser context cleanup: {e}", exc_info=True)
            print(f"❌ Warning: Cleanup had issues but continuing: {e}")
            # Reset counter anyway to avoid infinite loop
            self.consecutive_403_count = 0

    def _bypass_perimeterx_captcha(self, page: Page) -> bool:
        """
        Bypass PerimeterX "Press & Hold" captcha using human-like mouse behavior.

        Monitors the progress bar width and holds until it matches the target width,
        rather than using a fixed duration.

        Args:
            page: Playwright Page object with captcha

        Returns:
            bool: True if captcha was bypassed successfully, False otherwise
        """
        self.logger.info("🤖 Attempting to bypass PerimeterX captcha...")

        try:
            # Initialize human mouse simulator
            simulator = HumanMouseSimulator(page, self.logger)
            simulator.enable_mouse_tracking()

            # Wait for captcha to be fully loaded
            page.wait_for_selector('#px-captcha', timeout=5000)
            time.sleep(random.uniform(0.5, 1.0))  # Human hesitation

            # The captcha button is inside an iframe with style="display: block"
            # Important: there may be hidden iframes to confuse crawlers, so we only check visible ones

            # Get the Frame object that corresponds to iframe with style*="display: block"
            captcha_frame = None

            # Get all iframe elements
            all_iframes = page.locator('iframe').all()

            for iframe_element in all_iframes:
                try:
                    # Check if this iframe has display: block in its style
                    style_attr = iframe_element.get_attribute('style')
                    if not style_attr or 'display: block' not in style_attr:
                        self.logger.debug(f"Skipping iframe with style: {style_attr}")
                        continue

                    # This iframe has display: block
                    self.logger.debug("Found iframe with display: block")

                    # Get the Frame directly from the iframe element using frame_element.content_frame()
                    # Note: need to use ElementHandle, not Locator
                    # Get ElementHandle from Locator
                    iframe_handle = iframe_element.element_handle()
                    if iframe_handle:
                        # Get the frame from the element handle
                        frame = iframe_handle.content_frame()
                        if frame:
                            # Verify this frame contains the captcha button
                            if frame.locator('p:has-text("Press & Hold")').count() > 0:
                                captcha_frame = frame
                                self.logger.debug(f"Found captcha frame with display:block via element_handle")
                                break
                            else:
                                self.logger.debug("Frame found but doesn't contain captcha button")
                        else:
                            self.logger.debug("Could not get content_frame from element_handle")
                    else:
                        self.logger.debug("Could not get element_handle from iframe locator")

                except Exception as e:
                    self.logger.debug(f"Error checking iframe: {e}")
                    continue

            if not captcha_frame:
                self.logger.warning("Could not find captcha iframe with display:block")
                return False

            self.logger.debug("Successfully identified captcha iframe")

            if captcha_frame.locator('p:has-text("Press & Hold")').count() > 0:
                time.sleep(random.uniform(0.5, 1.0))
                self.logger.debug("Moving mouse to captcha button in iframe...")

                # Get the button in the frame to move mouse there
                framelocator = page.locator('iframe[style*="display: block"]').content_frame
                button_locator = framelocator.locator('p:has-text("Press & Hold")')

                # Get the button's bounding box to calculate center coordinates
                button_box = button_locator.bounding_box()
                if not button_box:
                    self.logger.error("Could not get button bounding box")
                    return False

                # Calculate center of the button
                button_x = button_box['x'] + button_box['width'] / 2
                button_y = button_box['y'] + button_box['height'] / 2

                self.logger.debug(f"Button center: ({button_x:.1f}, {button_y:.1f})")
                
                # Move mouse to the button using human-like movement with jitter
                existing_pos = simulator.get_real_mouse_position()
                simulator.mouse_move(existing_pos['x'], existing_pos['y'], button_x, button_y, 28)

                time.sleep(random.uniform(0.2, 0.5))  # Human hesitation before clicking

                # Now manually press and hold the mouse button using raw Playwright API
                # This ensures we maintain control over when it's released
                page.mouse.down()
                self.logger.debug("Mouse button pressed and held down, monitoring progress...")

                # Monitor progress bar width until it matches target width
                # Use the actual Frame object to evaluate JavaScript
                max_wait_time = 15  # Maximum 15 seconds
                start_time = time.time()
                last_micro_move = time.time()
                micro_move_interval = random.uniform(0.4, 0.7)  # Add micro-movements every 0.4-0.7s
                current_x, current_y = button_x, button_y

                while time.time() - start_time < max_wait_time:
                    try:
                        # Add natural hand tremor/micro-movements while holding
                        # This is CRITICAL - real humans can't hold perfectly still
                        if time.time() - last_micro_move >= micro_move_interval:
                            # Small random movement (1-3 pixels in random direction)
                            jitter_x = random.uniform(-2.5, 2.5)
                            jitter_y = random.uniform(-2.5, 2.5)
                            current_x = button_x + jitter_x
                            current_y = button_y + jitter_y

                            # Move mouse slightly (while button is still down)
                            page.mouse.move(current_x, current_y)

                            last_micro_move = time.time()
                            micro_move_interval = random.uniform(0.4, 0.7)  # Randomize next interval
                            self.logger.debug(f"Micro-tremor: ({jitter_x:.1f}px, {jitter_y:.1f}px)")

                        # Small delay before checking width
                        time.sleep(0.05)

                        # Get widths using JavaScript evaluation in the frame
                        # Find the "Press & Hold" button, get its parent div (2nd child),
                        # then get grandparent (main container), then get 1st child (progress bar)
                        widths = captcha_frame.evaluate("""
                            () => {
                                // Find the "Press & Hold" text element
                                const button = Array.from(document.querySelectorAll('p')).find(
                                    p => p.textContent.includes('Press') && p.textContent.includes('Hold')
                                );
                                if (!button) return { progress: 0, target: 0 };

                                // Get the main container (button's grandparent or great-grandparent)
                                let container = button.parentElement;
                                while (container && container.parentElement) {
                                    // Check if this container has multiple div children
                                    const divChildren = Array.from(container.parentElement.children).filter(
                                        child => child.tagName === 'DIV'
                                    );
                                    if (divChildren.length >= 2) {
                                        container = container.parentElement;
                                        break;
                                    }
                                    container = container.parentElement;
                                }

                                if (!container) return { progress: 0, target: 0 };

                                // Get the first and second div children
                                const divChildren = Array.from(container.children).filter(
                                    child => child.tagName === 'DIV'
                                );

                                const progressBar = divChildren[0];
                                const targetContainer = divChildren[1];

                                const progressWidth = progressBar ? parseFloat(window.getComputedStyle(progressBar).width) : 0;
                                const targetWidth = targetContainer ? parseFloat(window.getComputedStyle(targetContainer).width) : 0;

                                return { progress: progressWidth, target: targetWidth };
                            }
                        """)

                        progress_width = widths.get('progress', 0)
                        target_width = widths.get('target', 0)

                        if target_width > 0:
                            progress_pct = (progress_width / target_width) * 100
                            self.logger.debug(f"Progress: {progress_width:.1f}px / {target_width:.1f}px ({progress_pct:.1f}%)")

                            # Check if progress bar has reached target width (with small tolerance)
                            if progress_width >= target_width * 0.98: # 98% threshold, no threshold
                                self.logger.debug(f"Progress complete! ({progress_width:.1f}px >= {target_width:.1f}px)")
                                time.sleep(0.34)
                                break
                        else:
                            self.logger.debug("Waiting for target width to be available...")

                        # Continue with micro-movements (already slept 0.05s above)

                    except Exception as e:
                        self.logger.debug(f"Width check error (continuing): {e}")
                        continue
                else:
                    # Timeout reached
                    elapsed = time.time() - start_time
                    self.logger.warning(f"Progress monitoring timed out after {elapsed:.1f}s")

                # Release mouse button
                page.mouse.up()
                elapsed = time.time() - start_time
                self.logger.debug(f"Released mouse button after {elapsed:.1f} seconds")

            # Wait for captcha to disappear
            time.sleep(random.uniform(1.0, 2.0))

            # Check if captcha is still present
            if page.locator('#px-captcha-wrapper').count() == 0:
                self.logger.info("✅ Captcha bypassed successfully!")
                print("✅ Captcha solved!")
                return True
            else:
                self.logger.warning("Captcha still present after bypass attempt")
                print("⚠️  Captcha bypass may have failed")
                # Give it one more second to disappear
                time.sleep(2.0)
                if page.locator('#px-captcha-wrapper').count() == 0:
                    self.logger.info("✅ Captcha bypassed successfully (delayed)!")
                    print("✅ Captcha solved!")
                    return True
                else:
                    return False

        except Exception as e:
            self.logger.error(f"Error during captcha bypass: {e}", exc_info=True)
            print(f"❌ Captcha bypass failed: {e}")
            return False

    def _perform_login(self, page: Page) -> None:
        """
        Perform login to Seeking Alpha and save session cookies
        """
        self.logger.info("Starting login process...")
        print("🔐 Logging in to Seeking Alpha...")

        # Initialize human mouse simulator
        simulator = HumanMouseSimulator(page, self.logger)
        simulator.enable_mouse_tracking()
        self.logger.debug("Mouse tracking enabled")

        try:
            
            # Wait for the page to load
            page.wait_for_load_state("networkidle", timeout=10000)
            self.logger.debug("Page loaded, looking for login button")

            # Click the sign-in button with human-like movement
            login_button_selector = 'button[data-test-id="header-button-sign-in"]'

            try:
                login_button = page.locator(login_button_selector)
                login_button.wait_for(state="visible", timeout=5000)

                # Use human-like click
                simulator.click(login_button)
                self.logger.debug("Clicked sign-in button with human movement")
                time.sleep(random.uniform(0.8, 1.5))
            except Exception as e:
                self.logger.warning(f"Could not find sign-in button: {e}")
                # Try alternative: look for "Sign In" text link
                try:
                    sign_in_link = page.locator('text="Sign In"')
                    simulator.click(sign_in_link)
                    self.logger.debug("Clicked 'Sign In' text link")
                    time.sleep(random.uniform(0.8, 1.5))
                except Exception as e2:
                    self.logger.error(f"Could not find any login button: {e2}")
                    return

            # Wait for login modal to fully load
            self.logger.debug("Waiting for login modal...")
            page.wait_for_selector('[data-test-id="header-title"]', timeout=10000)
            self.logger.debug("Login modal appeared")
            time.sleep(random.uniform(0.5, 1.0))  # Human hesitation

            # Fill email with human-like typing
            # Use more specific selector to target the modal input (there are 2 email inputs on page)
            email_input = page.locator('input[type="email"][name="email"][autocomplete="username"]')
            email_input.wait_for(state="visible", timeout=5000)

            # Random typing speed like a human (80-150ms per character)
            typing_delay = random.uniform(80, 150)
            simulator.move_and_type(email_input, self.login_email, delay=typing_delay)
            self.logger.debug(f"Typed email with human-like behavior: {self.login_email}")

            # Human pause between fields
            time.sleep(random.uniform(0.4, 0.9))

            # Fill password with human-like typing
            # More specific selector for password in modal
            password_input = page.locator('input[type="password"][name="password"][autocomplete="current-password"]')
            password_input.wait_for(state="visible", timeout=5000)

            # Slightly different typing speed for password
            typing_delay = random.uniform(90, 160)
            simulator.move_and_type(password_input, self.login_password, delay=typing_delay)
            self.logger.debug("Typed password with human-like behavior")

            # Human pause before clicking submit (thinking time)
            time.sleep(random.uniform(0.6, 1.2))

            # Click submit button with human-like movement
            submit_button = page.locator('button[data-test-id="sign-in-button"]')
            submit_button.wait_for(state="visible", timeout=5000)
            simulator.click(submit_button)
            self.logger.debug("Clicked sign-in button with human movement")
            
            # Wait for login to complete (either redirect or page change)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
                self.logger.info("Login completed, waiting for page to stabilize")

                # Wait for login modal to disappear
                try:
                    page.wait_for_selector('[data-test-id="header-title"]', state="hidden", timeout=5000)
                    self.logger.debug("Login modal closed")
                except:
                    pass  # Modal might already be gone

                time.sleep(2)
            except Exception as e:
                self.logger.warning(f"Login wait warning: {e}")

            # Save cookies from the browser context (keep in Playwright format)
            # They will be converted to CookieJar when needed by curl_cffi
            self.session_cookies = page.context.cookies()
            # page.pause()

            self.logger.info(f"✅ Login successful! Saved {len(self.session_cookies)} cookies")
            print(f"✅ Login successful! Session cookies saved ({len(self.session_cookies)} cookies).")

            # Check for captcha after login
            if page.locator('#px-captcha-wrapper:not(.overflow-hidden)').count() > 0 or page.locator('#px-captcha:not(.overflow-hidden)').count() > 0:
                self.logger.debug("Captcha appeared after login")
                self._bypass_perimeterx_captcha(page)

        except Exception as e:
            self.logger.error(f"Error during login: {e}", exc_info=True)
            print(f"❌ Login failed: {e}")
            raise

    def before_scraping(self):
        # Just make sure we login before before fetching data
        self.scrape_article("https://seekingalpha.com/", None, True)
        
    def get_articles_with_metadata(self, limit: int = 20, filter_scraped: bool = True) -> List[Dict]:
        """
        Get articles with metadata from SeekingAlpha API using StealthyFetcher
        Automatically paginates through API pages until limit is reached

        Args:
            limit: Maximum number of articles to collect (across all pages)
            filter_scraped: If True, filter out already-scraped articles

        Returns:
            List of article dictionaries with metadata (not already scraped)

        Note:
            Pagination stops at page 15 to avoid excessive scraping,
            even if the limit hasn't been reached.
        """
        all_articles = []
        page_number = 1
        page_size = 50  # API max per page
        max_pages = 15  # Maximum pages to scrape to avoid excessive pagination
        skipped_count = 0

        self.logger.info(f"Fetching articles from SeekingAlpha API (category: {self.category})")
        print(f"📄 Fetching articles from SeekingAlpha API (category: {self.category})...")

        while len(all_articles) < limit and page_number <= max_pages:
            try:
                # Fetch page from API
                articles = self._base_fetch_articles_from_api(page_number, page_size)

                if not articles:
                    self.logger.info(f"No more articles found at page {page_number}, stopping pagination")
                    print(f"📄 Page {page_number}: No articles found, stopping")
                    break

                # Filter out already scraped articles
                if filter_scraped:
                    before_filter = len(articles)
                    articles = [a for a in articles if not self._is_already_scraped(a['url'])]
                    filtered = before_filter - len(articles)
                    if filtered > 0:
                        skipped_count += filtered
                        self.logger.debug(f"Filtered {filtered} already-scraped articles from page {page_number}")

                # Add to collection
                all_articles.extend(articles)
                new_count = len(articles)

                self.logger.info(f"Page {page_number}: Found {new_count} new articles (total: {len(all_articles)}, skipped: {skipped_count})")
                print(f"📄 Page {page_number}: +{new_count} new articles (total: {len(all_articles)})")

                # Check if we've reached limit
                if len(all_articles) >= limit:
                    self.logger.info(f"Reached limit of {limit} articles")
                    print(f"✓ Reached limit of {limit} articles")
                    break

                # Move to next page
                page_number += 1

                # Check if we've hit the page limit
                if page_number > max_pages:
                    self.logger.info(f"Reached maximum page limit ({max_pages}), stopping pagination")
                    print(f"⚠️  Reached maximum page limit ({max_pages})")
                    break

                # Small delay between pages
                time.sleep(1.0)

            except Exception as e:
                self.logger.error(f"Error fetching page {page_number}: {e}", exc_info=self.verbose)
                print(f"❌ Error on page {page_number}: {e}")
                break

        # Limit to requested number
        result = all_articles[:limit]

        if skipped_count > 0:
            print(f"⏭️  Skipped {skipped_count} already scraped article(s)")

        self.logger.info(f"Fetched {len(result)} new articles with metadata")
        print(f"✓ Found {len(result)} new articles total")

        return result

    def _fetch_articles_from_api(self, page_number: int, page_size: int) -> List[Dict]:
        """
        Fetch articles from SeekingAlpha API using StealthyFetcher

        Args:
            page_number: Page number to fetch (1-indexed)
            page_size: Number of articles per page

        Returns:
            List of article dictionaries with metadata
        """
        from urllib.parse import urlencode

        # Build API URL with pagination params
        params = {
            'filter[category]': self.category,
            'filter[since]': '0',
            'filter[until]': str(int(time.time())),
            'page[size]': str(page_size),
            'page[number]': str(page_number),
            'include': 'primaryTickers,secondaryTickers',
            'isMounting': 'false',
            'fields[news]': 'title,date,comment_count,content,disclosure,primaryTickers,secondaryTickers,tag,gettyImageUrl,publishOn',
            'fields[tag]': 'slug,name'
        }

        url = f"{self.api_base_url}?{urlencode(params)}"

        try:
            self.logger.debug(f"Fetching API: {url}")

            # Use StealthyFetcher for API requests
            response = StealthyFetcher.fetch(
                url,
                headless=self.headless,
                network_idle=True,
                google_search=True,
                timeout=10000,
                useragent='User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
                disable_resources=True
            )

            self.logger.debug(f"Response status: {response.status}")

            # Check for 403 Forbidden errors
            if response.status == 403:
                self.consecutive_403_count += 1
                self.logger.warning(f"API returned 403 Forbidden (consecutive: {self.consecutive_403_count}/{self.max_consecutive_403})")

                if self.consecutive_403_count >= self.max_consecutive_403:
                    self._cleanup_browser_context()

                return []
            elif response.status != 200:
                self.logger.error(f"API returned status {response.status}")
                # Reset counter on other errors
                self.consecutive_403_count = 0
                return []

            # Success - reset consecutive 403 counter
            self.consecutive_403_count = 0

            # Parse JSON from response body
            data = json.loads(response.body)
            articles = []

            # Parse JSON response
            if 'data' in data:
                for item in data['data']:
                    attributes = item.get('attributes', {})
                    article_id = item.get('id', '')

                    # Build article URL
                    article_url = f"{self.article_base_url}/{article_id}"

                    articles.append({
                        'id': article_id,
                        'url': article_url,
                        'title': attributes.get('title', ''),
                        'date': attributes.get('publishOn', ''),
                        'content': attributes.get('content', ''),
                        'raw_data': item  # Store full data for later use
                    })

                self.logger.debug(f"Parsed {len(articles)} articles from API response")

            return articles

        except Exception as e:
            self.logger.error(f"Error fetching from API: {e}", exc_info=self.verbose)
            raise

    def scrape_article(self, url: str, article_metadata: Optional[Dict] = None, login: bool = False) -> Optional[Dict]:
        """
        Scrape a single SeekingAlpha article using StealthyFetcher

        Args:
            url: Article URL
            article_metadata: Optional pre-fetched metadata from API

        Returns:
            Article data dictionary
        """
        self.logger.info(f"Scraping article: {url}")

        article_data = {
            'url': url,
            'scraped_at': datetime.now().isoformat(),
        }

        try:
            
            retry = True
            page = None

            # Fetch the article page with StealthyFetcher for full content
            self.logger.debug(f"Fetching article page with stealth mode: {url}")

            proxy = os.getenv('HTTP_PROXY', None)
            if proxy:
                self.logger.info(f"Using HTTP Proxy: {proxy}")

            while retry:
                def ensure_content_loaded(page: Page):
                    """
                    Page action to ensure all content is loaded including paywall content
                    Scrolls down and waits for dynamic content to render
                    """
                    try:
                        import time
                        self.logger.debug("Page action: Ensuring content is loaded")

                        if page.locator('#px-captcha-wrapper:not(.overflow-hidden)').count() > 0:
                            self.logger.debug("Captcha detected, trying to solve it ...")
                            self._bypass_perimeterx_captcha(page)

                        # Wait for content container to be present
                        page.wait_for_selector('div[data-test-id="content-container"]', timeout=10000)
                        self.logger.debug("Content container found")

                        # Scroll down to trigger lazy loading of paywall content
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        time.sleep(0.5)

                        # Scroll back up
                        page.evaluate("window.scrollTo(0, 0)")
                        time.sleep(0.5)

                        # Wait a bit more for any lazy-loaded content
                        page.wait_for_load_state("networkidle", timeout=5000)

                        if page.locator('button[data-test-id="header-button-sign-in"]').count() > 0 and self.login_email:
                            # Must log in
                            self.logger.debug("Login required, performing login...")
                            self._perform_login(page)

                            # Post-login stabilization: wait for session to fully establish
                            # The persistent browser context will retain cookies for next articles
                            self.logger.debug("Login complete, waiting for content to refresh with authenticated session...")

                            # Wait for the page to refresh content with authenticated access
                            # The content should auto-update after successful login
                            time.sleep(5)  # Give time for the page to update with auth content

                            # Wait for authenticated content to be visible
                            page.wait_for_selector('div[data-test-id="content-container"]', timeout=10000)
                            self.logger.debug("Authenticated content container found")

                        self.logger.debug("Content loading complete")

                        time.sleep(2)
                        page.wait_for_selector('section[data-test-id="card-container"]', timeout=5000)
                    except Exception as e:
                        self.logger.warning(f"Page action warning (non-critical): {e}")

                # Prepare fetch options
                fetch_options = {
                    'headless': self.headless,
                    'network_idle': True,
                    'user_data_dir': self.user_data_dir,  # Use persistent browser context
                    'allow_webgl': True,
                    'hide_canvas': False,
                    'google_search': False,
                    'retries': 5,
                    'timeout': 60000,
                    'disable_resources': False,
                    'solve_cloudflare': False,
                    'proxy': proxy,
                    'page_action': ensure_content_loaded,
                    'blocked_domains': ['collector-pxxgcxm9by.cl6.px-cloud.net', 'collector-pxxgcxm9by.px-cloud.net']
                }

                # 
                page = StealthyFetcher.fetch(url, cookies=self.session_cookies, **fetch_options)

                # Check for 403 Forbidden errors
                if page.status == 403:
                    retry = True
                    self.consecutive_403_count += 1
                    self.logger.warning(f"Article fetch returned 403 Forbidden (consecutive: {self.consecutive_403_count}/{self.max_consecutive_403})")
                    print(f"  ⚠️  403 Forbidden error (consecutive: {self.consecutive_403_count}/{self.max_consecutive_403})")

                    if self.consecutive_403_count >= self.max_consecutive_403:
                        self._cleanup_browser_context()
                elif page.status != 200:
                    self.logger.error(f"Failed to fetch article: HTTP {page.status}")
                    # Reset counter on other errors
                    self.consecutive_403_count = 0
                    retry = False
                else:
                    retry = False
                    # Success - reset consecutive 403 counter
                    self.consecutive_403_count = 0

            if not page:
                return None
            
            if login:
                return None
            
            # Extract title
            title = self._extract_title(page)
            article_data['title'] = title or article_metadata.get('title', 'No Title') if article_metadata else 'No Title'
            self.logger.info(f"Title: {article_data['title']}")

            # Extract author
            author = self._extract_author(page)
            article_data['author'] = author or 'Seeking Alpha'
            self.logger.debug(f"Author: {article_data['author']}")

            # Extract publish date
            published_date = self._extract_date(page)
            article_data['published_date'] = published_date or article_metadata.get('date', 'Unknown') if article_metadata else 'Unknown'
            self.logger.debug(f"Published: {article_data['published_date']}")

            # Extract excerpt from meta tags (og:description)
            excerpt = self._extract_excerpt(page)
            if excerpt:
                self.logger.debug(f"Excerpt extracted from meta tags ({len(excerpt)} chars)")

            # Extract article content using CSS selectors
            content_text = self._extract_content(page)

            if not content_text or len(content_text.split()) < 50:
                self.logger.warning("Stealth mode: Content seems short, might be paywalled or blocked")

            article_data['content'] = content_text
            # Use meta tag excerpt if available, otherwise fallback to first 200 chars of content
            article_data['excerpt'] = excerpt if excerpt else (content_text[:200] if content_text else '')
            article_data['word_count'] = len(content_text.split())

            self.logger.info(f"Word count: {article_data['word_count']}")

            return article_data

        except Exception as e:
            self.logger.error(f"Error scraping article {url}: {e}", exc_info=self.verbose)
            print(f"  ❌ Error: {e}")
            return None

    def _extract_title(self, page) -> Optional[str]:
        """Extract article title using multiple selectors"""
        selectors = [
            'h1[data-test-id="post-title"]',
            'h1',
            'meta[property="og:title"]::attr(content)',
            'meta[name="title"]::attr(content)',
        ]

        for selector in selectors:
            self.logger.debug(f"Trying title selector: {selector}")
            try:
                if '::attr' in selector:
                    title = page.css(selector).get()
                else:
                    title = page.css(f'{selector}::text').get()

                if title and title.strip():
                    self.logger.debug(f"Title found with selector: {selector}")
                    return title.strip()
            except Exception as e:
                self.logger.debug(f"Selector {selector} failed: {e}")
                continue

        return None

    def _extract_author(self, page) -> Optional[str]:
        """Extract article author"""
        selectors = [
            'a[data-test-id="author-name"]::text',
            '[class*="author"]::text',
            'span[data-test-id="post-author-nick"] > a::text',
            'meta[name="author"]::attr(content)',
        ]

        for selector in selectors:
            self.logger.debug(f"Trying author selector: {selector}")
            try:
                author = page.css(selector).get()
                if author and author.strip():
                    self.logger.debug(f"Author found with selector: {selector}")
                    return author.strip()
            except:
                continue

        return None

    def _extract_date(self, page) -> Optional[str]:
        """Extract publish date"""
        selectors = [
            'time::attr(datetime)',
            'time::text',
            'meta[property="article:published_time"]::attr(content)',
        ]

        for selector in selectors:
            self.logger.debug(f"Trying date selector: {selector}")
            try:
                date = page.css(selector).get()
                if date and date.strip():
                    self.logger.debug(f"Date found with selector: {selector}")
                    return date.strip()
            except:
                continue

        return None

    def _extract_excerpt(self, page) -> Optional[str]:
        """Extract article excerpt/description from meta tags"""
        selectors = [
            'meta[property="og:description"]::attr(content)',
            'meta[name="description"]::attr(content)',
            'meta[property="description"]::attr(content)',
        ]

        for selector in selectors:
            self.logger.debug(f"Trying excerpt selector: {selector}")
            try:
                excerpt = page.css(selector).get()
                if excerpt and excerpt.strip():
                    self.logger.debug(f"Excerpt found with selector: {selector}")
                    return excerpt.strip()
            except:
                continue

        return None

    def _extract_content(self, page) -> str:
        """
        Extract article content using CSS selectors
        Captures both visible and paywall-hidden content including nested elements
        Extracts headings, paragraphs, and all text content

        Args:
            page: Scrapling Response object

        Returns:
            Clean text content
        """
        content_blocks = []

        # Primary strategy: Get the entire content container and extract ALL text elements
        # This includes <p>, <h1-h6>, <div>, etc. with all nested content
        # Updated selector based on new HTML structure with class "T2G6W JYDbo"
        content_container_selector = 'div[data-test-id="content-container"].T2G6W'

        try:
            self.logger.debug(f"Extracting content from {content_container_selector}")

            # Get the entire content container HTML
            container_html = page.css(content_container_selector).get()

            if container_html:
                from bs4 import BeautifulSoup

                soup = BeautifulSoup(container_html, 'html.parser')

                # Remove figure/image elements to avoid extracting captions as content
                for figure in soup.find_all('figure'):
                    figure.decompose()

                # Remove script and style elements
                for script in soup(['script', 'style']):
                    script.decompose()

                # Extract text from all content elements (p, h1-h6, div, etc.)
                # Process them in document order to maintain structure
                for element in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'strong']):
                    text = element.get_text(separator=' ', strip=True)

                    # Filter out promotional/boilerplate content
                    if text == 'Join the community built by investors, for investors. Create your free account >>':
                        continue
                    elif text == 'New! Get unlimited breaking news with a free Seeking Alpha account »':
                        continue
                    elif text.startswith('Dear readers:'):
                        continue

                    if text and len(text) > 10:  # Keep even short elements like headings
                        # Clean up excessive whitespace
                        text = ' '.join(text.split())

                        # Avoid duplicates
                        if text not in content_blocks:
                            # Format headings with markdown-style headers
                            if element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                                # Add extra newline before headings for better formatting
                                content_blocks.append(f"\n## {text}")
                                self.logger.debug(f"Added heading ({len(text)} chars): {text[:80]}...")
                            else:
                                content_blocks.append(text)
                                self.logger.debug(f"Added content ({len(text)} chars): {text[:80]}...")

                self.logger.info(f"Successfully extracted {len(content_blocks)} content blocks from container")
            else:
                self.logger.warning("Content container not found, trying alternative approach")

                # Fallback: Extract elements individually
                elements_to_extract = [
                    f'{content_container_selector} p',
                    f'{content_container_selector} h3',
                    f'{content_container_selector} h2',
                    f'{content_container_selector} h1',
                ]

                for selector in elements_to_extract:
                    elements = page.css(selector).getall()
                    self.logger.debug(f"Found {len(elements)} elements with selector: {selector}")

                    for elem_html in elements:
                        soup = BeautifulSoup(elem_html, 'html.parser')
                        text = soup.get_text(separator=' ', strip=True)

                        if text and len(text) > 10:
                            text = ' '.join(text.split())
                            if text not in content_blocks:
                                content_blocks.append(text)

        except Exception as e:
            self.logger.error(f"Error extracting from content container: {e}", exc_info=True)

        # Final fallback: get all text elements from entire page
        if not content_blocks:
            self.logger.warning("No article content found in container, using page-wide fallback")
            try:
                from bs4 import BeautifulSoup

                # Try to get article or main content
                article_html = page.css('article').get() or page.body

                if article_html:
                    soup = BeautifulSoup(article_html, 'html.parser')

                    # Remove unwanted elements
                    for element in soup(['script', 'style', 'nav', 'header', 'footer', 'figure']):
                        element.decompose()

                    for element in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                        text = element.get_text(separator=' ', strip=True)
                        if text and len(text) > 20:
                            text = ' '.join(text.split())
                            content_blocks.append(text)

            except Exception as e:
                self.logger.error(f"Fallback extraction failed: {e}", exc_info=True)

        clean_text = '\n\n'.join(content_blocks)
        self.logger.info(f"Extracted {len(content_blocks)} content blocks total, {len(clean_text)} characters")

        return self.remove_copyright(clean_text)
