import re
import json
import time
import random
import requests # <-- Import requests for Telegram
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException, WebDriverException
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager
from selenium_stealth import stealth
import gspread
from google.oauth2.service_account import Credentials
# --- Google Sheets Integration ---
import gspread
from google.oauth2.service_account import Credentials
# --- End Google Sheets Integration ---

# Only import 2Captcha if needed
try:
    from twocaptcha import TwoCaptcha
except ImportError:
    TwoCaptcha = None # Define it as None if library not installed


# --- Configuration ---
# --- TOGGLE FEATURES HERE ---
USE_PROXY = False  # Set to True to enable proxy usage
SOLVE_CAPTCHA = False # Set to True to enable automatic CAPTCHA solving
SEND_TO_GOOGLE_SHEETS = True # Set to True to send data to Google Sheets
SEND_TELEGRAM_ALERTS = True # Set to True to send alerts via Telegram

MAX_PAGES = 2 # Set a limit for the number of pages to scrape
MIN_ALERT_DISCOUNT = 40 # Example: Only alert for 40% off or more

# --- Google Sheets Config ---
# Make sure credentials.json is in the same directory as the script
GOOGLE_CREDENTIALS_FILE = 'credentials.json'
# Enter the name of the Google Sheet you created and shared (used for messages)
GOOGLE_SHEET_NAME = '6pm Scraped Deals'
# *** PASTE YOUR GOOGLE SHEET ID HERE *** (from the sheet's URL)
GOOGLE_SHEET_ID = 'YOUR_ID'
# --- End Google Sheets Config ---

# --- Telegram Config ---
# Get these from Telegram's BotFather and userinfobot
TELEGRAM_BOT_TOKEN = "YOUR_ID" # Paste your token from BotFather
YOUR_CHAT_ID = "YOUR_ID"         # Paste your ID from userinfobot
# --- End Telegram Config ---

# Replace with your actual 2Captcha API Key (needed if SOLVE_CAPTCHA is True)
TWO_CAPTCHA_API_KEY = 'YOUR_2CAPTCHA_API_KEY'

# Replace with your actual residential proxy details (needed if USE_PROXY is True)
PROXY_HOST = "proxy.example.com" # Your proxy host
PROXY_PORT = 8080 # Your proxy port
PROXY_USER = "username" # Your proxy username, or None
PROXY_PASS = "password" # Your proxy password, or None
# --- END TOGGLE FEATURES ---

# Configure the proxy string only if USE_PROXY is True
proxy_full_address = None
if USE_PROXY:
    proxy_auth = f"{PROXY_USER}:{PROXY_PASS}@" if PROXY_USER and PROXY_PASS else ""
    proxy_full_address = f"http://{proxy_auth}{PROXY_HOST}:{PROXY_PORT}"

# 2Captcha solver setup only if SOLVE_CAPTCHA is True
captcha_solver = None
if SOLVE_CAPTCHA:
    if TwoCaptcha is None:
        print("[ERROR] '2captcha-python' library is not installed. CAPTCHA solving disabled.")
        print("Please install it: pip install 2captcha-python")
        SOLVE_CAPTCHA = False # Force disable if library missing
    elif 'YOUR_2CAPTCHA_API_KEY' in TWO_CAPTCHA_API_KEY:
         print("\n[WARNING] 2Captcha API Key is still the placeholder. CAPTCHA solving will fail.")
         print("Please edit the script and add your API key.\n")
         # Consider setting SOLVE_CAPTCHA = False here too, or let it fail later
    else:
        captcha_solver = TwoCaptcha(TWO_CAPTCHA_API_KEY)
# --- End Configuration ---


# --- Google Sheets Functions ---
def authenticate_google_sheets():
    """Authenticates with Google Sheets API using service account credentials."""
    if not SEND_TO_GOOGLE_SHEETS:
        print("Google Sheets integration disabled.")
        return None, None
    if 'YOUR_GOOGLE_SHEET_ID_HERE' in GOOGLE_SHEET_ID:
         print("[ERROR] GOOGLE_SHEET_ID is not set in the script.")
         print("Please paste the Sheet ID from its URL into the GOOGLE_SHEET_ID variable.")
         return None, None

    try:
        # Define the scopes needed: Sheets (Drive scope not strictly needed for open_by_key)
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            # 'https://www.googleapis.com/auth/drive.file' # Keep if needed for other Drive ops
        ]
        creds = Credentials.from_service_account_file(GOOGLE_CREDENTIALS_FILE, scopes=scopes)
        client = gspread.authorize(creds)

        # --- Attempt to open the sheet BY ID ---
        sheet = client.open_by_key(GOOGLE_SHEET_ID).sheet1 # Open by ID, access the first tab
        # ---

        print(f"Successfully connected to Google Sheet: '{GOOGLE_SHEET_NAME}' (using ID)")
        return client, sheet
    except FileNotFoundError:
        print(f"[ERROR] Google credentials file '{GOOGLE_CREDENTIALS_FILE}' not found.")
        print("Make sure the JSON key file is in the same directory as the script.")
        return None, None
    except gspread.exceptions.APIError as e:
         # More specific error handling for API issues like permissions or ID not found
         if e.response.status_code == 403:
              print(f"[ERROR] Permission Denied (403): Failed to open Google Sheet by ID.")
              print(f"Make sure the sheet (ID: {GOOGLE_SHEET_ID}) is shared with the service account email: {creds.service_account_email} granting 'Editor' access.")
         elif e.response.status_code == 404:
              print(f"[ERROR] Google Sheet Not Found (404): No sheet found with ID: {GOOGLE_SHEET_ID}")
              print("Please double-check the GOOGLE_SHEET_ID in your script.")
         elif "Request had insufficient authentication scopes" in str(e):
             print(f"[ERROR] Google API Scope Error: {e}")
             print("Please ensure 'Google Sheets API' is enabled in your Google Cloud project.")
         else:
            print(f"[ERROR] Google API Error ({e.response.status_code}) opening sheet by ID: {e}")
            return None, None
    except Exception as e:
        print(f"[ERROR] Failed to authenticate/open Google Sheet by ID: {e}")
        return None, None

def send_data_to_google_sheet(sheet, data):
    """Appends scraped product data to the Google Sheet."""
    if not sheet or not data:
        print("No sheet object or data provided, skipping Google Sheets update.")
        return

    try:
        print(f"Attempting to send {len(data)} items to Google Sheets...")
        # Prepare header row if sheet is empty
        try:
             # Check first cell, faster than getting all values if sheet is large
             first_cell = sheet.cell(1, 1).value
             is_empty = not first_cell
        except gspread.exceptions.APIError as api_error:
             # Handle potential permission issues if the sheet was just created/shared
             print(f"[WARN] API error checking sheet emptiness: {api_error}. Assuming header might be needed.")
             is_empty = True # Assume empty on error
        except Exception as check_error:
             print(f"[WARN] Error checking sheet emptiness: {check_error}. Assuming header might be needed.")
             is_empty = True


        if is_empty:
            # Use specific keys relevant to the scraped data
            header = ["brand", "title", "current_price", "original_price", "discount_percent", "product_url", "image_url", "site_url"]
            # Ensure the header only includes keys present in the first data item if data exists
            if data:
                header = [h for h in header if h in data[0]]
            else: # If no data, just use the default header
                 pass

            if not header:
                 print("[WARN] Could not determine header row, data might be empty or malformed.")
                 return # Don't proceed without a header

            try:
                sheet.append_row(header, value_input_option='USER_ENTERED')
                print("Added header row to Google Sheet.")
                time.sleep(1) # Small delay after adding header
            except Exception as header_e:
                 print(f"[ERROR] Failed to add header row: {header_e}")
                 return # Stop if header fails
        else:
             # If not empty, try to get header to ensure order (optional but good practice)
             try:
                 header = sheet.row_values(1)
                 print("Found existing header in sheet.")
             except Exception as get_header_e:
                  print(f"[WARN] Could not read existing header: {get_header_e}. Using default order.")
                  # Fallback to default order if header read fails
                  header = ["brand", "title", "current_price", "original_price", "discount_percent", "product_url", "image_url", "site_url"]
                  if data: header = [h for h in header if h in data[0]] # Filter again


        # Prepare data rows using the determined header order
        rows_to_append = []
        ordered_keys = header # Use the header (either new or existing) for order
        for item in data:
            # Convert values to strings to prevent potential type issues with gspread
            row = [str(item.get(key, '')) for key in ordered_keys] # Get values in header order
            rows_to_append.append(row)

        # Append all rows at once for efficiency
        sheet.append_rows(rows_to_append, value_input_option='USER_ENTERED')
        print(f"Successfully appended {len(rows_to_append)} rows to Google Sheet.")

    except gspread.exceptions.APIError as e:
         print(f"[ERROR] Google Sheets API Error while sending data: {e}")
         print("Check sheet permissions and API quotas in Google Cloud Console.")
    except Exception as e:
        print(f"[ERROR] Failed to send data to Google Sheet: {e}")
# --- End Google Sheets Functions ---

# --- Telegram Function ---
def send_telegram_alert(deal_data):
    """Sends a formatted deal alert to your Telegram chat."""
    if not SEND_TELEGRAM_ALERTS:
         # print("Telegram alerts disabled.") # Keep console cleaner
         return
    if 'YOUR_BOT_TOKEN_HERE' in TELEGRAM_BOT_TOKEN or 'YOUR_CHAT_ID_HERE' in YOUR_CHAT_ID:
        print("[WARN] Telegram token or chat ID not configured. Skipping alert.")
        return

    # Helper function to escape MarkdownV2 characters
    def escape_markdown(text):
        if not isinstance(text, str):
             text = str(text) # Ensure it's a string
        # Added more characters that often cause issues in MarkdownV2
        escape_chars = r'_*[]()~`>#+-=|{}.!'
        # Escape the escape character '\' itself first
        text = text.replace('\\', '\\\\')
        # Then escape the other characters
        return ''.join(f'\\{char}' if char in escape_chars else char for char in text)

    try:
        title = escape_markdown(deal_data.get("title", "N/A"))
        brand = escape_markdown(deal_data.get("brand", "N/A"))
        current_price_val = deal_data.get("current_price", 0.0)
        original_price_val = deal_data.get("original_price", 0.0)
        # Format prices after escaping other text
        current_price_str = escape_markdown(f"{current_price_val:.2f}")
        original_price_str = escape_markdown(f"{original_price_val:.2f}")

        discount = int(deal_data.get("discount_percent", 0)) # Use int for cleaner look
        product_url = deal_data.get("product_url", "#") # Don't escape URLs, but ensure they don't contain unbalanced parentheses

        # Check for unbalanced parentheses in URL, which breaks MarkdownV2 links
        if product_url.count('(') != product_url.count(')'):
             print(f"  [WARN] URL has unbalanced parentheses, might break Telegram link: {product_url}")
             # Optionally, skip the link part or the whole message
             # product_url = "#" # Fallback to a safe link

        message = (
            f"*{discount}% OFF* 🔥 Deal Found on 6pm\\!\n\n"
            f"*Brand:* {brand}\n"
            f"*Product:* {title}\n"
            f"*Price:* *${current_price_str}* \\(was ${original_price_str}\\)\n\n"
            f"[View Product]({product_url})"
        )

    except Exception as e:
        print(f"  [ERROR] Error formatting Telegram message: {e}")
        # Try sending simpler text on formatting error
        message = f"Deal Found: {deal_data.get('brand')} - {deal_data.get('title')} - ${deal_data.get('current_price')} ({deal_data.get('discount_percent')}% off) {deal_data.get('product_url')}"
        # Set parse_mode to None for plain text if formatting fails
        payload = {
            'chat_id': YOUR_CHAT_ID,
            'text': message,
            'parse_mode': None, # Send as plain text
             'disable_web_page_preview': False
        }
        try:
            response = requests.post(api_url, json=payload, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as fallback_e:
            print(f"  [ERROR] Also failed sending plain text Telegram alert: {fallback_e}")
        return # Exit after sending fallback

    # --- Send the message via Telegram API ---
    api_url = f"https://api.telegram.org/bot8454465574:AAG9MLFtIwbpPfvFRs06A-GbMsTOLkRDilE/sendMessage"
    payload = {
        'chat_id': YOUR_CHAT_ID,
        'text': message,
        'parse_mode': 'MarkdownV2', # Use MarkdownV2 for formatting
        'disable_web_page_preview': False # Allow link previews (shows image)
    }

    # --- DEBUG: Print the message before sending ---
    print(f"  [DEBUG] Sending Telegram message:\n{message}\n")
    # --- END DEBUG ---

    response = None # Define response outside try block
    try:
        response = requests.post(api_url, json=payload, timeout=10)
        response.raise_for_status() # Raise exception for bad status codes
        # Success message moved outside this function for cleaner scraping loop output
    except requests.exceptions.RequestException as e:
        print(f"  [ERROR] Error sending Telegram alert: {e}")
        # --- DEBUG: Print response body on error ---
        if response is not None:
             try:
                 error_details = response.json() # Try parsing JSON error
                 print(f"  [DEBUG] Telegram API Response (JSON): {error_details}")
             except json.JSONDecodeError:
                 print(f"  [DEBUG] Telegram API Response (Text): {response.text}") # Print raw text if not JSON
        # --- END DEBUG ---

def calculate_discount(original_price, current_price):
    """Calculates discount percentage."""
    if original_price > 0 and current_price < original_price:
        discount = ((original_price - current_price) / original_price) * 100
        return round(discount, 2)
    return 0.0

def parse_price(price_text):
    """Extracts float value from price string (removes $, commas)."""
    if not price_text:
        return 0.0
    cleaned_price = re.sub(r"[^0-9.]", "", price_text)
    try:
        return float(cleaned_price)
    except ValueError:
        print(f"  [WARN] Could not parse price from text: {price_text}")
        return 0.0

def solve_captcha_if_present(driver):
    """Checks for and attempts to solve CAPTCHA using 2Captcha if enabled."""
    if not SOLVE_CAPTCHA or not captcha_solver:
        # print("CAPTCHA solving is disabled or not configured.") # Keep console cleaner
        return False

    print("Checking for CAPTCHA...")
    try:
        # --- Adjust this section for 6pm's CAPTCHA ---
        # Look for common indicators like Cloudflare, Akamai, hCaptcha, reCAPTCHA iframes
        # Example: Check for Cloudflare challenge title
        if "checking your browser" in driver.title.lower() or "just a moment" in driver.title.lower():
             print("Cloudflare challenge detected. Waiting...")
             # Simple wait, might need more advanced handling or CAPTCHA solving service for interactive challenges
             time.sleep(15) # Wait for potential automatic bypass
             # Re-check title after waiting
             if "checking your browser" in driver.title.lower() or "just a moment" in driver.title.lower():
                  print("[WARN] Cloudflare challenge persisted.")
                  # Here you might try a CAPTCHA solve if it presents one (e.g., hCaptcha)
             else:
                  print("Cloudflare challenge seems to have passed.")
             return True # Indicate some handling was attempted

        # Example: Looking for hCaptcha or reCAPTCHA iframe (adjust selectors)
        captcha_iframe = driver.find_element(By.CSS_SELECTOR, 'iframe[src*="captcha"]')
        # ---

        # --- Extract sitekey (Highly dependent on CAPTCHA type) ---
        src_attribute = captcha_iframe.get_attribute('src')
        if not src_attribute: return False # Skip if no src

        sitekey = None
        captcha_type = None
        if 'hcaptcha.com' in src_attribute:
            sitekey_match = re.search(r'sitekey=([\w-]+)', src_attribute)
            if sitekey_match:
                sitekey = sitekey_match.group(1)
                captcha_type = 'hcaptcha'
        elif 'google.com/recaptcha' in src_attribute:
            sitekey_match = re.search(r'[?&]k=([\w-]+)', src_attribute)
            if sitekey_match:
                sitekey = sitekey_match.group(1)
                captcha_type = 'recaptcha'
        # Add other CAPTCHA types if needed

        if not sitekey or not captcha_type:
            print("[WARN] CAPTCHA iframe found, but failed to identify type or extract sitekey from 'src':", src_attribute)
            return False
        # ---

        page_url = driver.current_url
        print(f"CAPTCHA detected ({captcha_type}). Sitekey: {sitekey}")
        print("Sending to 2Captcha for solving...")

        # --- Use correct 2Captcha method ---
        if captcha_type == 'hcaptcha':
             result = captcha_solver.hcaptcha(sitekey=sitekey, url=page_url)
        elif captcha_type == 'recaptcha':
             result = captcha_solver.recaptcha(sitekey=sitekey, url=page_url, version='v2') # Assuming v2
        else:
             print(f"[WARN] Unsupported CAPTCHA type for solving: {captcha_type}")
             return False
        # ---

        captcha_code = result.get('code')
        if not captcha_code:
             print("[ERROR] 2Captcha did not return a solution code.")
             return False

        print("CAPTCHA solved by 2Captcha. Submitting solution...")

        # --- Inject the solution code ---
        driver.execute_script(f"""
            var el_h = document.getElementsByName('h-captcha-response')[0];
            var el_g = document.getElementById('g-recaptcha-response');
            if (el_h) {{ el_h.innerHTML = '{captcha_code}'; }}
            if (el_g) {{ el_g.innerHTML = '{captcha_code}'; }}
            // Add callback execution if needed (common for hCaptcha/reCAPTCHA)
            // Example: find the callback function name from the iframe or data attributes
            // if (typeof yourCaptchaCallbackFunction === 'function') {{ yourCaptchaCallbackFunction('{captcha_code}'); }}
        """)
        # Try finding a submit button near the CAPTCHA
        try:
             submit_button = captcha_iframe.find_element(By.XPATH, "./ancestor::form//button[@type='submit']")
             submit_button.click()
             print("Clicked a potential form submit button.")
        except NoSuchElementException:
             print("[INFO] No obvious CAPTCHA form submit button found.")
        # ---

        print("CAPTCHA solution submitted. Waiting briefly...")
        time.sleep(12)
        return True

    except NoSuchElementException:
        # print("No CAPTCHA detected.") # Keep console cleaner
        return False
    except Exception as e:
        print(f"[ERROR] Failed during CAPTCHA check/solve process: {e}")
        return False



def scrape_6pm(url, sheet): # Added sheet parameter
    """
    Scrapes product data from multiple pages of a 6pm.com search results.
    Sends data to Google Sheets and Telegram if configured.
    """
    # ... (Setup code remains the same) ...
    options = Options()
    # options.add_argument("--headless") # Keep headless commented out for debugging
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("start-maximized")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
    )
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    # --- Conditionally Add Proxy ---
    if USE_PROXY and proxy_full_address:
        print(f"Using Proxy: {PROXY_HOST}:{PROXY_PORT}")
        options.add_argument(f'--proxy-server={proxy_full_address}')
    elif USE_PROXY:
        print("[WARN] USE_PROXY is True, but proxy details missing. No proxy used.")
    else:
        print("Proxy usage is disabled.")
    # ---

    driver = None
    all_products_data = [] # List to hold data from all pages
    current_page = 1
    alerts_sent_this_run = 0

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        # --- Apply selenium-stealth ---
        stealth(driver, languages=["en-US", "en"], vendor="Google Inc.", platform="Linux x86_64", webgl_vendor="Intel Inc.", renderer="Intel Iris OpenGL Engine", fix_hairline=True)
        # ---

        driver.get(url)

        dwell_time = random.uniform(3.5, 6.5)
        print(f"Initial page loaded. Pausing for {dwell_time:.2f} seconds...")
        time.sleep(dwell_time)

        # --- Initial CAPTCHA check ---
        solve_captcha_if_present(driver)
        # ---

        while current_page <= MAX_PAGES:
            print(f"\n--- Scraping Page {current_page} ---")

            # Wait for the product grid marker (using the article element)
            wait_time = 60 if SOLVE_CAPTCHA else 30 # Wait longer if we might need to solve CAPTCHA
            print(f"Waiting for product grid to load (max {wait_time} seconds)...")
            try:
                WebDriverWait(driver, wait_time).until(
                    # Wait for first product OR the "no results" message to be sure page loaded
                    EC.presence_of_element_located((By.CSS_SELECTOR, "article[data-style-id], div._-z")) # Added selector for no results div
                )
                print("Product grid or 'no results' found.")
            except TimeoutException:
                print("Timeout waiting for product grid. Checking for CAPTCHA again...")
                if solve_captcha_if_present(driver):
                    print("CAPTCHA possibly handled. Retrying wait...")
                    try:
                        WebDriverWait(driver, 20).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "article[data-style-id], div._-z"))
                        )
                        print("Product grid or 'no results' found after CAPTCHA solve.")
                    except TimeoutException:
                        print("\n--- SCRAPE FAILED (Page {current_page}) ---")
                        print("Still timed out after attempting CAPTCHA solve.")
                        driver.save_screenshot(f"debug_6pm_timeout_p{current_page}.png")
                        print("Saved screenshot.")
                        break # Stop scraping on persistent timeout
                else:
                    print("\n--- SCRAPE FAILED (Page {current_page}) ---")
                    print("Page timed out, no CAPTCHA found or solved. Site might be blocking or layout changed.")
                    driver.save_screenshot(f"debug_6pm_timeout_p{current_page}.png")
                    print("Saved screenshot.")
                    break # Stop scraping on timeout
            # --- Selenium session error often occurs around here due to bot detection ---
            except WebDriverException as e:
                 if "invalid session id" in str(e) or "disconnected" in str(e):
                      print(f"\n--- BROWSER CRASHED (Page {current_page}) ---")
                      print("Error: ", str(e))
                      print("This often indicates aggressive bot detection closing the browser.")
                      print("Consider using a residential proxy (USE_PROXY=True) or enabling CAPTCHA solving.")
                 else:
                      print(f"An unexpected WebDriverException occurred: {e}") # Handle other WebDriver errors
                 break # Stop scraping if browser connection is lost


            # Check if the "no results" message is present
            try:
                no_results = driver.find_element(By.CSS_SELECTOR, "div._-z") # Specific selector for "no results found" container
                if "no results found" in no_results.text.lower():
                     print("'No results found' message detected. Stopping pagination.")
                     break
            except NoSuchElementException:
                 pass # No "no results" message, proceed

            # --- Scrolling (Optional, might not be needed if products load instantly) ---
            print("Scrolling page (optional)...")
            body = driver.find_element(By.TAG_NAME, 'body')
            scrolls_done = 0
            while scrolls_done < 3: # Fewer scrolls per page might be enough
                body.send_keys(Keys.PAGE_DOWN)
                time.sleep(random.uniform(0.8, 1.5))
                scrolls_done += 1
            print("Scrolling finished.")
            # --- End Scrolling ---

            # --- Find Products ---
            product_containers = driver.find_elements(By.CSS_SELECTOR, "article[data-style-id]")
            print(f"Found {len(product_containers)} product containers on page {current_page}.")

            if not product_containers:
                # If grid was found but no containers, something is odd
                print(f"[WARN] No product containers found on page {current_page}, but grid seemed present.")

            # --- Loop through products ---
            scraped_this_page = 0
            for item in product_containers:
                time.sleep(random.uniform(0.1, 0.4)) # Small delay between scraping items

                product_info = {
                    "brand": "N/A", # Moved brand first to match Sheets order likely
                    "title": "N/A",
                    "current_price": 0.0,
                    "original_price": 0.0,
                    "discount_percent": 0.0,
                    "product_url": "N/A",
                    "image_url": "N/A",
                    "site_url": "www.6pm.com",
                }


                try:
                    # --- Get URL ---
                    link_element = item.find_element(By.CSS_SELECTOR, "a.NR-z") # Use the link inside the details div
                    href = link_element.get_attribute('href')
                    if href:
                         product_info["product_url"] = href if href.startswith("http") else f"https://www.6pm.com{href}"

                    # --- Get Brand ---
                    try:
                        brand_element = item.find_element(By.CSS_SELECTOR, "dd.OR-z span")
                        product_info["brand"] = brand_element.text.strip()
                    except NoSuchElementException:
                        print(f"  [WARN] Brand element not found.")

                    # --- Get Title ---
                    try:
                        title_element = item.find_element(By.CSS_SELECTOR, "dd.PR-z")
                        product_info["title"] = title_element.text.strip()
                    except NoSuchElementException:
                         print(f"  [WARN] Title element not found.")

                    # --- Get Image URL ---
                    try:
                        # Prefer the first image in the figure
                        img_element = item.find_element(By.CSS_SELECTOR, "figure img.Jn-z")
                        product_info["image_url"] = img_element.get_attribute('src')
                    except NoSuchElementException:
                        print(f"  [WARN] Image not found.")

                    # --- Get Prices ---
                    try:
                        # Current (sale) price
                        current_price_element = item.find_element(By.CSS_SELECTOR, "span.c--z")
                        product_info["current_price"] = parse_price(current_price_element.text)
                    except NoSuchElementException:
                         print(f"  [WARN] Current price not found.")

                    try:
                        # Original (standard/MSRP) price
                        original_price_element = item.find_element(By.CSS_SELECTOR, "span.g--z")
                        product_info["original_price"] = parse_price(original_price_element.text)
                    except NoSuchElementException:
                        # If no original price, assume it's the same as current
                        product_info["original_price"] = product_info["current_price"]
                        # print(f"  [INFO] Original price span not found, using current price.") # Less verbose

                    # --- Calculate Discount ---
                    product_info["discount_percent"] = calculate_discount(
                        product_info["original_price"],
                        product_info["current_price"]
                    )

                    all_products_data.append(product_info)
                    scraped_this_page += 1

                    # --- Check and Send Telegram Alert ---
                    if SEND_TELEGRAM_ALERTS and product_info["discount_percent"] >= MIN_ALERT_DISCOUNT:
                         print(f"  >>> Deal Alert! ({product_info['discount_percent']}% off) Sending Telegram message for '{product_info['title']}'...")
                         send_telegram_alert(product_info)
                         # Note: Success/Error message is now inside send_telegram_alert for debugging
                         alerts_sent_this_run += 1
                         time.sleep(1) # Small pause after sending alert
                    # --- End Telegram Alert Check ---

                    # Less verbose success message
                    if scraped_this_page % 20 == 0 or scraped_this_page == len(product_containers):
                        print(f"  Scraped {scraped_this_page}/{len(product_containers)} items on page {current_page}...")

                except StaleElementReferenceException:
                    print("  [WARN] Stale element detected, likely due to page update. Skipping item.")
                    continue # Skip this item and continue loop
                except Exception as e:
                    print(f"  [ERROR] Failed to scrape details for one item on page {current_page}. Error: {e}")

            # --- End product loop for current page ---
            print(f"Finished scraping page {current_page}. Total items so far: {len(all_products_data)}")

            # --- Find and click next page ---
            if current_page >= MAX_PAGES:
                print(f"Reached MAX_PAGES limit ({MAX_PAGES}). Stopping.")
                break

            next_page_index = current_page # Because page 2 link has p=1, page 3 has p=2, etc.
            next_page_selector = f"a[href*='&p={next_page_index}']"
            pagination_selector = "span.ro-z" # Container for pagination links

            try:
                print(f"Looking for next page link ({next_page_selector})...")
                # Wait briefly for pagination to be potentially updated by JS
                WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, pagination_selector)))
                pagination_container = driver.find_element(By.CSS_SELECTOR, pagination_selector)
                next_page_link = pagination_container.find_element(By.CSS_SELECTOR, next_page_selector)

                print(f"Next page link found. Clicking page {current_page + 1}...")
                next_page_link.click()
                current_page += 1
                time.sleep(random.uniform(3.0, 5.0)) # Wait for navigation and initial load

                # --- CAPTCHA check after navigation ---
                solve_captcha_if_present(driver)
                # ---

            except NoSuchElementException:
                print("No 'next page' link found. Reached the last page or layout changed.")
                break # Exit the loop if no next page link
            except Exception as e:
                 print(f"Error clicking next page: {e}")
                 driver.save_screenshot(f"debug_6pm_next_page_error_p{current_page}.png")
                 print("Saved screenshot.")
                 break # Exit loop on navigation error

        # --- End page loop ---

        # --- Save to JSON (optional) ---
        if all_products_data:
            output_file = "6pm_products.json"
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(all_products_data, f, indent=4, ensure_ascii=False)
                # Use current_page - 1 because current_page increments *before* the check/break
                page_count_str = f"{current_page - 1 if current_page > 1 else 1}"
                print(f"\nSuccessfully scraped {len(all_products_data)} products across {page_count_str} page(s).")
                print(f"Data saved to {output_file}")
                print(f"Sent {alerts_sent_this_run} Telegram alerts for deals >= {MIN_ALERT_DISCOUNT}% off.")
            except Exception as e:
                print(f"[ERROR] Failed to save data to JSON file '{output_file}': {e}")
        else:
            print("\nScraping finished, but no product data was collected.")
            if driver:
                try:
                    driver.save_screenshot("debug_6pm_no_data_final.png")
                    print("Saved screenshot.")
                except: pass
        # --- End Save to JSON ---

        # --- Send to Google Sheets (if enabled and data exists) ---
        if SEND_TO_GOOGLE_SHEETS and all_products_data and sheet:
            send_data_to_google_sheet(sheet, all_products_data)
        elif SEND_TO_GOOGLE_SHEETS and not all_products_data:
             print("No data scraped, skipping Google Sheets update.")
        elif SEND_TO_GOOGLE_SHEETS and not sheet:
             print("Google Sheet connection failed earlier, skipping update.")
        # --- End Send to Google Sheets ---


    except WebDriverException as e: # Catch WebDriverException specifically
         if "invalid session id" in str(e) or "disconnected" in str(e) or "connection closed" in str(e):
              print(f"\n--- BROWSER CRASHED or DISCONNECTED (Early in Page {current_page}) ---")
              print("Error Details: ", str(e))
              print("This often indicates aggressive bot detection closing the browser connection.")
              print("Try enabling USE_PROXY=True with a residential proxy, or enable SOLVE_CAPTCHA=True.")
              print("If the problem persists, the site's protection might be too strong for this method.")
              # No driver object to take screenshot here
         else:
              print(f"\nAn unexpected WebDriver error occurred: {e}")
              if driver:
                  try:
                      driver.save_screenshot(f"debug_6pm_webdriver_error_p{current_page}.png")
                      print("Saved error screenshot.")
                  except: pass
    except Exception as e:
        print(f"\nAn unexpected error occurred during the process: {e}")
        if driver:
             try:
                driver.save_screenshot(f"debug_6pm_general_error_p{current_page}.png")
                print("Saved error screenshot.")
             except: pass # Ignore screenshot error if browser already crashed

    finally:
        if driver:
            try:
                driver.quit()
            except Exception as quit_e:
                 print(f"Error while quitting driver: {quit_e}") # Catch errors during quit too
        print("Scraping complete. Browser closed.")


if __name__ == "__main__":
    # Example search URL on 6pm.com for women's shoes
    SEARCH_URL = "https://www.6pm.com/womens/shoes/CK_XAcABAeICAgEY.zso?s=isNew%2Fdesc%2FgoLiveDate%2Fdesc%2FrecentSalesStyle%2Fdesc%2F"

    print("--- SCRAPER CONFIGURATION ---")
    print(f"[*] Target Site: 6pm.com")
    print(f"[*] Max Pages to Scrape: {MAX_PAGES}")
    print(f"[*] Use Proxy: {USE_PROXY}")
    if USE_PROXY and proxy_full_address: print(f"    - Address: {proxy_full_address}")
    elif USE_PROXY: print("    - [WARN] Proxy details missing!")
    print(f"[*] Solve CAPTCHA: {SOLVE_CAPTCHA}")
    if SOLVE_CAPTCHA and 'YOUR_2CAPTCHA_API_KEY' in TWO_CAPTCHA_API_KEY: print("    - [WARN] 2Captcha API Key missing!")
    elif SOLVE_CAPTCHA and not TwoCaptcha: print("    - [WARNING] 2Captcha library missing!")
    print(f"[*] Send to Google Sheets: {SEND_TO_GOOGLE_SHEETS}")
    if SEND_TO_GOOGLE_SHEETS:
        print(f"    - Sheet Name: '{GOOGLE_SHEET_NAME}'")
        if 'YOUR_GOOGLE_SHEET_ID_HERE' in GOOGLE_SHEET_ID:
            print(f"    - [ERROR] Sheet ID: NOT SET!")
        else:
            print(f"    - Sheet ID: '{GOOGLE_SHEET_ID[:5]}...{GOOGLE_SHEET_ID[-5:]}'") # Show partial ID
    print(f"[*] Send Telegram Alerts: {SEND_TELEGRAM_ALERTS}") # Added Telegram status
    if SEND_TELEGRAM_ALERTS:
        print(f"    - Min Discount % for Alert: {MIN_ALERT_DISCOUNT}%")
        if 'YOUR_BOT_TOKEN_HERE' in TELEGRAM_BOT_TOKEN or 'YOUR_CHAT_ID_HERE' in YOUR_CHAT_ID:
            print("    - [WARN] Telegram Bot Token or Chat ID is missing!")
    print("---")

    # --- Authenticate Google Sheets ---
    gs_client, gs_sheet = None, None
    if SEND_TO_GOOGLE_SHEETS:
        gs_client, gs_sheet = authenticate_google_sheets()
        if not gs_sheet:
            print("[INFO] Google Sheets authentication failed. Data will not be sent to Sheets.")
            # Decide if you want to stop the script entirely or just proceed without Sheets
            # exit() # Uncomment this line to stop if Sheets connection fails
    # --- End Authenticate ---

    scrape_6pm(SEARCH_URL, gs_sheet) # Pass the sheet object to the scrape function


