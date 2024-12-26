# scrape_google_reviews.py
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import json
import os
import logging
from selenium.common.exceptions import TimeoutException
import sys

logger = logging.getLogger(__name__)

def scrape_google_reviews(keyword, driver_path=None, output_file='reviews.json', status_dict=None):
    def update_status(new_status):
        if status_dict and keyword in status_dict:
            status_dict[keyword].update(new_status)
            logger.info(f"更新狀態: {new_status}")

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    try:
        # 根據操作系統選擇正確的 chromedriver 路徑
        if driver_path is None:
            if sys.platform == "win32":
                driver_path = "./chromedriver-win32/chromedriver.exe"
            elif sys.platform == "linux":
                driver_path = "./chromedriver-linux64/chromedriver"
            else:
                driver_path = "./chromedriver-mac-x64/chromedriver"

        service = Service(executable_path=driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        wait = WebDriverWait(driver, 15)
        
        all_reviews = []
        
        update_status({
            "status": "processing",
            "message": "連接到 Google Maps"
        })
        
        driver.get('https://www.google.com.tw/maps/preview')
        time.sleep(3)

        try:
            search_box = wait.until(EC.presence_of_element_located((By.ID, 'searchboxinput')))
            search_box.send_keys(keyword)
            search_box.send_keys(Keys.ENTER)
            time.sleep(2)

            # 等待並點擊評論按鈕
            review_tab = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//button[.//div[text()='評論']]")
            ))
            driver.execute_script("arguments[0].click();", review_tab)
            time.sleep(2)

            # 等待評論容器載入
            scrollable_div = wait.until(EC.presence_of_element_located(
                (By.XPATH, '//*[@id="QA0Szd"]/div/div/div[1]/div[2]/div/div[1]/div/div/div[2]')
            ))

            def scroll_reviews(scrollable_element, num_scrolls=10):
                last_height = driver.execute_script("return arguments[0].scrollHeight", scrollable_element)
                for i in range(num_scrolls):
                    driver.execute_script(
                        "arguments[0].scrollTop = arguments[0].scrollHeight;",
                        scrollable_element
                    )
                    update_status({
                        "status": "processing",
                        "message": f"載入更多評論 ({i+1}/{num_scrolls})"
                    })
                    time.sleep(1.5)
                    
                    new_height = driver.execute_script("return arguments[0].scrollHeight", scrollable_element)
                    if new_height == last_height:
                        break
                    last_height = new_height

            scroll_reviews(scrollable_div)

            reviews = driver.find_elements(By.CSS_SELECTOR, 'div.jftiEf.fontBodyMedium')
            total_reviews = len(reviews)

            update_status({
                "status": "processing",
                "message": f"開始解析 {total_reviews} 則評論",
                "total_reviews": total_reviews
            })

            for idx, review in enumerate(reviews, 1):
                try:
                    more_button = review.find_elements(By.CSS_SELECTOR, 'button.w8nwRe.kyuRq')
                    if more_button:
                        driver.execute_script("arguments[0].click();", more_button[0])
                        time.sleep(0.5)

                    reviewer = review.find_element(By.CSS_SELECTOR, 'div.d4r55').text
                    rating_element = review.find_element(By.CSS_SELECTOR, 'span.kvMYJc')
                    rating = rating_element.get_attribute("aria-label") if rating_element else "無評分"
                    comment = review.find_element(By.CSS_SELECTOR, 'span.wiI7pd').text
                    
                    # 嘗試獲取評論時間，如果找不到就設為空字串
                    try:
                        review_time = review.find_element(By.CSS_SELECTOR, 'span.rsqaWe').text
                    except:
                        review_time = ""

                    review_data = {
                        "評論編號": idx,
                        "用戶": reviewer,
                        "評分": rating,
                        "評論": comment,
                        "評論時間": review_time
                    }
                    all_reviews.append(review_data)

                    update_status({
                        "status": "processing",
                        "message": f"已處理 {idx}/{total_reviews} 則評論",
                        "processed_reviews": idx
                    })

                except Exception as e:
                    logger.error(f"處理第 {idx} 則評論時發生錯誤: {str(e)}")
                    continue

        except TimeoutException as e:
            error_msg = "等待頁面元素超時，請檢查網路連接"
            logger.error(error_msg)
            update_status({
                "status": "error",
                "message": error_msg,
                "error": str(e)
            })
            raise

        # 儲存評論
        os.makedirs(os.path.dirname(output_file) or '.', exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_reviews, f, ensure_ascii=False, indent=4)

        update_status({
            "status": "completed",
            "message": f"完成，共收集 {len(all_reviews)} 則評論",
            "total_reviews": len(all_reviews),
            "end_time": time.strftime("%Y-%m-%d %H:%M:%S")
        })

        return all_reviews

    except Exception as e:
        error_msg = f"爬蟲過程發生錯誤: {str(e)}"
        logger.error(error_msg, exc_info=True)
        update_status({
            "status": "error",
            "message": error_msg,
            "error": str(e)
        })
        raise

    finally:
        if 'driver' in locals():
            driver.quit()