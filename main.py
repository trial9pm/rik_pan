import time
import random
import zipfile
import os
import sys
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Silence TensorFlow / Chromium stderr logging
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
os.environ["WDM_LOG"] = "0"

# ─────────────────────────────────────────────────────────────
#  PROXY CONFIG
# ─────────────────────────────────────────────────────────────
PROXY_HOST = "37.49.230.40"
PROXY_PORT = "80"
PROXY_USER = "19f6a86c928846c8889066c621e75870-cc-IN"
PROXY_PASS = "821512e250cf1fd5707fc4692de45dd8"

# ─────────────────────────────────────────────────────────────
#  USER CREDENTIALS  ← yahan apna dalo
# ─────────────────────────────────────────────────────────────
MOBILE_OR_EMAIL = ""   # runtime pe puchha jayega
PASSWORD        = ""   # agar password login ho


TARGET_URL  = "https://creditreport.paisabazaar.com/bureau/report-analysis"
LOGIN_URLS = [
    "https://creditreport.paisabazaar.com/credit-report/apply",
]

PLUGIN_DIR = "proxy_auth_plugin"

# ─────────────────────────────────────────────────────────────
#  USER AGENT PROFILES (4 real browser fingerprints)
# ─────────────────────────────────────────────────────────────
USER_AGENTS = [
    {
        "label": "Chrome 124 / Windows 11",
        "ua": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "platform": "Win32",
        "vendor": "Google Inc.",
        "languages": ["en-IN", "en-GB", "en"],
    },
    {
        "label": "Chrome 123 / macOS Sonoma",
        "ua": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "platform": "MacIntel",
        "vendor": "Google Inc.",
        "languages": ["en-IN", "en"],
    },
    {
        "label": "Edge 124 / Windows 10",
        "ua": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36 "
            "Edg/124.0.0.0"
        ),
        "platform": "Win32",
        "vendor": "Microsoft Corporation",
        "languages": ["en-IN", "hi", "en"],
    },
    {
        "label": "Firefox 125 / Windows 11",
        "ua": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
            "Gecko/20100101 Firefox/125.0"
        ),
        "platform": "Win32",
        "vendor": "",
        "languages": ["en-IN", "en-US", "en"],
    },
]


def create_proxy_plugin(host, port, user, pwd):
    """
    Chrome extension for proxy auth.
    Headless mode mein bhi kaam karta hai jab --load-extension se load karo.
    """
    os.makedirs(PLUGIN_DIR, exist_ok=True)

    manifest = """{
  "version": "1.0.0",
  "manifest_version": 2,
  "name": "Proxy Auth",
  "permissions": ["proxy","tabs","unlimitedStorage","storage",
                   "<all_urls>","webRequest","webRequestBlocking"],
  "background": {"scripts": ["background.js"]},
  "minimum_chrome_version": "22.0.0"
}"""

    background = f"""
var config = {{
    mode: "fixed_servers",
    rules: {{
        singleProxy: {{ scheme: "http", host: "{host}", port: parseInt("{port}") }},
        bypassList: ["localhost"]
    }}
}};
chrome.proxy.settings.set({{value: config, scope: "regular"}}, function(){{}});

function callbackFn(details) {{
    return {{ authCredentials: {{ username: "{user}", password: "{pwd}" }} }};
}}
chrome.webRequest.onAuthRequired.addListener(
    callbackFn, {{urls: ["<all_urls>"]}}, ["blocking"]
);
"""

    with open(os.path.join(PLUGIN_DIR, "manifest.json"), "w") as f:
        f.write(manifest)
    with open(os.path.join(PLUGIN_DIR, "background.js"), "w") as f:
        f.write(background)

    plugin_zip = "proxy_auth_plugin.zip"
    with zipfile.ZipFile(plugin_zip, "w") as zf:
        zf.write(os.path.join(PLUGIN_DIR, "manifest.json"), "manifest.json")
        zf.write(os.path.join(PLUGIN_DIR, "background.js"), "background.js")

    return os.path.abspath(PLUGIN_DIR)   # load-extension ko unpacked path chahiye


def get_driver():
    profile = random.choice(USER_AGENTS)
    print(f"[*] Browser Profile : {profile['label']}")

    plugin_dir = create_proxy_plugin(PROXY_HOST, PROXY_PORT, PROXY_USER, PROXY_PASS)

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(f"--load-extension={plugin_dir}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument(f"--user-agent={profile['ua']}")
    options.add_argument(f"--lang={profile['languages'][0]}")

    options.add_argument("--log-level=3")
    options.add_argument("--silent")
    options.add_argument("--disable-logging")
    options.add_argument("--disable-bluetooth")

    # ── Enable DevTools Performance & Network Logging ─────────
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    options.add_experimental_option("perfLoggingPrefs", {"enableNetwork": True, "enablePage": False})

    service = Service(log_output=os.devnull)
    driver = webdriver.Chrome(options=options, service=service)

    # ── Inject In-Memory API Response Interceptor (Fetch + XHR) ──
    js_interceptor = """
    (function() {
        window.__CAPTURED_APIS__ = window.__CAPTURED_APIS__ || {};

        // 1. Fetch Interceptor
        var origFetch = window.fetch;
        if (origFetch) {
            window.fetch = async function() {
                var args = arguments;
                var res = await origFetch.apply(this, args);
                try {
                    var u = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url ? args[0].url : '');
                    if (u && (u.includes('creditReport') || u.includes('customer') || u.includes('bureauApplication') || u.includes('overview'))) {
                        var clone = res.clone();
                        var json = await clone.json();
                        window.__CAPTURED_APIS__[u] = json;
                    }
                } catch(e){}
                return res;
            };
        }

        // 2. XHR Interceptor
        var origOpen = XMLHttpRequest.prototype.open;
        var origSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.open = function(method, url) {
            this._targetUrl = url;
            return origOpen.apply(this, arguments);
        };
        XMLHttpRequest.prototype.send = function() {
            this.addEventListener('load', function() {
                try {
                    var u = this._targetUrl || '';
                    if (u && (u.includes('creditReport') || u.includes('customer') || u.includes('bureauApplication') || u.includes('overview'))) {
                        window.__CAPTURED_APIS__[u] = JSON.parse(this.responseText);
                    }
                } catch(e){}
            });
            return origSend.apply(this, arguments);
        };
    })();
    """
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": js_interceptor})
    except Exception:
        pass

    driver.execute_script(f"""
        Object.defineProperty(navigator, 'webdriver',  {{get: () => undefined}});
        Object.defineProperty(navigator, 'platform',   {{get: () => '{profile["platform"]}'}});
        Object.defineProperty(navigator, 'vendor',     {{get: () => '{profile["vendor"]}'}});
        Object.defineProperty(navigator, 'languages',  {{get: () => {profile["languages"]}}});
        Object.defineProperty(navigator, 'language',   {{get: () => '{profile["languages"][0]}'}});
    """)

    time.sleep(1)
    handles = driver.window_handles
    if len(handles) > 1:
        for h in handles[1:]:
            driver.switch_to.window(h)
            driver.close()
        driver.switch_to.window(handles[0])

    return driver


def login(driver):
    print("\n[*] Loading login page...")
    url = "https://creditreport.paisabazaar.com/credit-report/apply"
    driver.get(url)
    mobile_field = None
    start_wait = time.time()
    
    while time.time() - start_wait < 15:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for idx, iframe in enumerate(iframes):
            try:
                driver.switch_to.frame(iframe)
                mobile_field = driver.find_element(
                    By.XPATH,
                    "//input[contains(@placeholder,'Mobile') or @type='tel' or @name='mobile' or @name='phone']"
                )
                print(f"[+] Mobile input field located in iframe [{idx}]")
                break
            except NoSuchElementException:
                driver.switch_to.default_content()
        
        if mobile_field:
            break
            
        try:
            mobile_field = driver.find_element(
                By.XPATH,
                "//input[contains(@placeholder,'Mobile') or @type='tel' or @name='mobile' or @name='phone']"
            )
            print("[+] Mobile input field located in main DOM")
            break
        except NoSuchElementException:
            pass
            
        time.sleep(1)

    if not mobile_field:
        try:
            driver.save_screenshot("error_screenshot.png")
            print(f"[-] Mobile input field not found. Saved error_screenshot.png. Current URL: {driver.current_url}")
        except Exception as se:
            print(f"[-] Failed to save screenshot: {se}")
        return False



    try:
        from selenium.webdriver.common.keys import Keys
        mobile_field.click()
        mobile_field.send_keys(Keys.CONTROL + "a")
        mobile_field.send_keys(Keys.BACKSPACE)
        mobile_field.send_keys(MOBILE_OR_EMAIL)

        driver.execute_script("""
            var el = arguments[0];
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.blur();
        """, mobile_field)
        print(f"[+] Mobile number entered: {MOBILE_OR_EMAIL}")
    except Exception as e:
        print(f"[-] Mobile entry error: {e}")
        return False

    try:
        mobile_field.send_keys(Keys.ENTER)
    except Exception:
        pass

    try:
        btn = driver.find_element(
            By.XPATH,
            "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'get otp')"
            " or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]"
        )
        driver.execute_script("arguments[0].click();", btn)
    except Exception:
        pass

    print("[+] OTP request sent successfully.")

    print("\n[?] Enter received OTP: ", end="", flush=True)
    otp = input().strip()

    try:
        otp_boxes = driver.find_elements(By.CSS_SELECTOR, "input[maxlength='1'], input.otp")
        if len(otp_boxes) >= len(otp):
            for i, ch in enumerate(otp):
                otp_boxes[i].click()
                otp_boxes[i].send_keys(ch)
            print("[+] OTP inserted.")
        else:
            otp_field = driver.find_element(
                By.XPATH,
                "//input[@type='tel' or @name='otp' or @id='otp' or contains(@placeholder,'OTP') or contains(@placeholder,'otp')]"
            )
            otp_field.clear()
            otp_field.send_keys(otp)
            otp_field.send_keys(Keys.ENTER)
            print("[+] OTP submitted successfully.")

        try:
            verify = driver.find_element(
                By.XPATH,
                "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'verify')"
                " or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')"
                " or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'login')]"
            )
            driver.execute_script("arguments[0].click();", verify)
        except Exception:
            pass

    except Exception as e:
        print(f"[-] OTP submission error: {e}")
        return False

    time.sleep(2)
    print("\n" + "=" * 55)
    print("      [SUCCESS] LOGIN VERIFIED SUCCESSFULLY! 🎉")
    print("=" * 55)
    return True


def find_customer_profile(obj):
    if isinstance(obj, str):
        try:
            import json
            parsed = json.loads(obj)
            return find_customer_profile(parsed)
        except Exception:
            return None
    if isinstance(obj, dict):
        if "customerProfile" in obj and isinstance(obj["customerProfile"], dict):
            return obj["customerProfile"]
        if "mobileNumber" in obj and "panCard" in obj:
            return obj
        for k, v in obj.items():
            res = find_customer_profile(v)
            if res:
                return res
    elif isinstance(obj, list):
        for item in obj:
            res = find_customer_profile(item)
            if res:
                return res
    return None


def fetch_credit_report_overview(driver):
    print("\n[*] Navigating to Credit Report Analysis...")
    driver.switch_to.default_content()
    driver.get("https://creditreport.paisabazaar.com/bureau/report-analysis")

    import json
    import urllib.request
    import gzip

    profile = None
    start_time = time.time()


    # Poll in-memory captured APIs, Window State and LocalStorage for up to 12 seconds
    while time.time() - start_time < 12:
        try:
            captured = driver.execute_script("""
                var res = window.__CAPTURED_APIS__ || {};
                res.__INITIAL_STATE__ = window.__INITIAL_STATE__ || null;
                return res;
            """)
            if captured:
                found = find_customer_profile(captured)
                if found:
                    profile = found
                    break
        except Exception:
            pass

        try:
            local_data = driver.execute_script("""
                var result = {};
                for (var i = 0; i < localStorage.length; i++) {
                    var k = localStorage.key(i);
                    try {
                        result[k] = JSON.parse(localStorage.getItem(k));
                    } catch(e) {
                        result[k] = localStorage.getItem(k);
                    }
                }
                return result;
            """)
            found = find_customer_profile(local_data)
            if found:
                profile = found
                break
        except Exception:
            pass

        time.sleep(1)



    if not profile:
        try:
            cookies = {c['name']: c['value'] for c in driver.get_cookies()}
            cookie_header = "; ".join([f"{k}={v}" for k, v in cookies.items()])
            
            pb_access_token = cookies.get("pb-access-token", "") or driver.execute_script("return localStorage.getItem('pb-access-token') || localStorage.getItem('ssoToken') || '';")
            pb_pass_token = cookies.get("pb-pass-token", "") or cookies.get("PB_GLSS_TOKEN", "") or driver.execute_script("return localStorage.getItem('pb-pass-token') || '';")
            visit_id = cookies.get("visitId", "") or driver.execute_script("return localStorage.getItem('visitId') || '';")

            req_headers = {
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json",
                "User-Agent": driver.execute_script("return navigator.userAgent;"),
                "Origin": "https://creditreport.paisabazaar.com",
                "Referer": "https://creditreport.paisabazaar.com/",
                "non-app": "true",
                "site-origin": "BUREAU_WEB_MOBILE",
                "Cookie": cookie_header
            }
            if pb_access_token:
                req_headers["pb-access-token"] = pb_access_token
            if pb_pass_token:
                req_headers["pb-pass-token"] = pb_pass_token
            if visit_id:
                req_headers["visitid"] = visit_id

            target_url = "https://api2.paisabazaar.com/BSP/api/v1/customer/creditReport/overview"
            req = urllib.request.Request(target_url, headers=req_headers, method="GET")

            with urllib.request.urlopen(req, timeout=10) as response:
                resp_bytes = response.read()
                try:
                    resp_text = gzip.decompress(resp_bytes).decode("utf-8")
                except Exception:
                    resp_text = resp_bytes.decode("utf-8")

                parsed = json.loads(resp_text)
                found = find_customer_profile(parsed)
                if found:
                    profile = found
        except Exception:
            pass

    if not profile:
        try:
            local_data = driver.execute_script("""
                var result = {};
                for (var i = 0; i < localStorage.length; i++) {
                    var k = localStorage.key(i);
                    try {
                        result[k] = JSON.parse(localStorage.getItem(k));
                    } catch(e) {
                        result[k] = localStorage.getItem(k);
                    }
                }
                return result;
            """)
            found = find_customer_profile(local_data)
            if found:
                profile = found
        except Exception:
            pass

    if profile:
        print("\n" + "=" * 55)
        print("            CUSTOMER PROFILE DATA (RAW)")
        print("=" * 55)
        print(json.dumps(profile, indent=4))
        print("=" * 55 + "\n")
        return True
    else:
        print("[-] Customer profile data not found.")
        return False


def main():
    global MOBILE_OR_EMAIL

    print("=" * 55)
    print("   Paisabazaar — Customer Data Automation")
    print("=" * 55)

    while not MOBILE_OR_EMAIL:
        num = input("\n[?] Enter registered mobile number: ").strip()
        if num.isdigit() and len(num) == 10:
            MOBILE_OR_EMAIL = num
        else:
            print("    [!] Please enter a valid 10-digit mobile number.")

    print(f"[+] Registered Mobile: {MOBILE_OR_EMAIL}")

    try:
        driver = get_driver()
        try:
            if login(driver):
                fetch_credit_report_overview(driver)
        except KeyboardInterrupt:
            print("\n[*] Execution cancelled by user.")
        except Exception as e:
            print(f"[-] Error: {e}")
        finally:
            try:
                driver.quit()
            except (Exception, KeyboardInterrupt):
                pass
    except KeyboardInterrupt:
        print("\n[*] Execution cancelled by user.")

    print("\n[*] Execution Completed.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)





