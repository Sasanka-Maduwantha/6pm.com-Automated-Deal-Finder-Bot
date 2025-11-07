
# 6pm.com Automated Deal Finder Bot

A Python automation bot that scrapes 6pm.com for high-discount products, saves them to Google Sheets, and sends instant Telegram alerts.

This project was built as a portfolio item to demonstrate a full-stack, data-driven automation pipeline.

---

## 🎥 Video Demonstration


> **[Click Here to Watch the Full Video Demo](https://youtu.be/A4aOutYn8Ac)**

---

## ✨ Core Features

* **Browser Automation:** Uses **Selenium** & **Selenium-Stealth** to mimic a real user, bypassing basic bot detection.
* **Data Extraction:** Scrapes product titles, brands, original prices, sale prices, product URLs, and image URLs.
* **Intelligent Filtering:** Automatically calculates the discount percentage and filters for deals above a set threshold (e.g., 40% off).
* **Google Sheets Integration:** Connects to the Google Sheets API (`gspread`) to automatically append all found deals to a spreadsheet in real-time.
* **Instant Alerts:** Uses the Telegram Bot API to send an immediate, formatted message for any "high-priority" deals that meet the alert criteria.
* **Highly Configurable:** Easy-to-use toggles in the script to enable/disable proxies, CAPTCHA solving, Sheets, and Telegram.

## 🛠️ Tech Stack

* **Language:** Python 3.10+
* **Web Automation:** Selenium & Selenium-Stealth
* **Google API:** `gspread` & `google-auth`
* **HTTP Requests:** `requests` (for Telegram API)
* **Driver Management:** `webdriver-manager`

## 🚀 How to Run

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/Kalana-Gayan/6pm.com-Automated-Deal-Finder-Bot.git
    cd 6pm_product_scrapper
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    (You will need to create a `requirements.txt` file. You can generate one by running: `pip freeze > requirements.txt`)

3.  **Complete the Configuration (See below).** This is the most important step.

4.  **Run the script:**
    ```bash
    python scrapperV3.py
    ```

## ⚙️ Configuration

You must set up your credentials in `scrapperV3.py` (or using environment variables) for the bot to work.

### 1. Script Toggles

Inside `scrapperV3.py`, set these to `True` or `False`:

```python
USE_PROXY = False
SOLVE_CAPTCHA = False
SEND_TO_GOOGLE_SHEETS = True
SEND_TELEGRAM_ALERTS = True
MIN_ALERT_DISCOUNT = 40 # Alert for deals >= 40%
```
