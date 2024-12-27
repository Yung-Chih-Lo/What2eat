# app.py
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta

from flask import Flask, jsonify, request
from flask_cors import CORS
from google.cloud import firestore
from google.oauth2 import service_account
from openai import OpenAI
from peft import PeftConfig, PeftModel
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from transformers import AutoModelForQuestionAnswering, AutoTokenizer, pipeline
from webdriver_manager.chrome import ChromeDriverManager

# 設定logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)

app = Flask(__name__)
CORS(app)

credentials = service_account.Credentials.from_service_account_file(
    os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "YOUR_GOOGLE_APPLICATION_CREDENTIALS")
)
# 初始化 Firestore 客戶端
db = firestore.Client(
    project="dm-project-445608", credentials=credentials, database="dm-firestore"
)

# 用於儲存爬蟲狀態
scraping_status = {}
# 用於儲存正在執行的線程
active_threads = {}

# 設定 OpenAI API Key
openai_api_key = os.getenv("OPENAI_API_KEY", "your-openai-api-key")
client = OpenAI(api_key=openai_api_key)

# 設定QA模型路徑（請確認模型文件在此路徑下）
model_path = r"lora_qa_model_new/lora_qa_model_new"


def upload_reviews_to_firestore(collection_name, reviews):
    """
    將評論數據上傳到 Firestore 的指定集合。
    每條評論作為一個文檔存儲。
    """
    try:
        batch = db.batch()
        for review in reviews:
            doc_ref = db.collection(collection_name).document()
            batch.set(doc_ref, review)
        batch.commit()
        logging.info(
            f"成功上傳 {len(reviews)} 條評論到 Firestore 集合: {collection_name}"
        )
    except Exception as e:
        logging.error(f"上傳評論到 Firestore 時發生錯誤: {e}")
        raise


def upload_analysis_to_firestore(collection_name, keyword, analysis):
    """
    將分析結果上傳到 Firestore 的指定集合中的一個文檔。
    """
    try:
        # 創建或更新一個文檔用於存儲分析結果，文檔 ID 為關鍵字
        doc_ref = db.collection(collection_name).document(keyword)
        doc_ref.set(
            {
                "keyword": keyword,
                "分析結果": analysis,
                "分析時間": firestore.SERVER_TIMESTAMP,
                "last_scraped": firestore.SERVER_TIMESTAMP,  # 記錄最後爬取時間
            },
            merge=True,
        )
        logging.info(
            f"成功上傳分析結果到 Firestore 集合: {collection_name}, 文檔 ID: {keyword}"
        )
    except Exception as e:
        logging.error(f"上傳分析結果到 Firestore 時發生錯誤: {e}")
        raise


def should_scrape(keyword, frequency_days=7):
    """
    判斷是否需要爬取該餐廳的評論。
    :param keyword: 餐廳名稱
    :param frequency_days: 爬取頻率（天）
    :return: True 如果需要爬取，否則 False
    """
    doc_ref = db.collection("reviews").document(keyword)
    doc = doc_ref.get()
    if doc.exists:
        last_scraped = doc.to_dict().get("last_scraped")
        if last_scraped:
            last_scraped_time = last_scraped.to_pydatetime()
            current_time = datetime.utcnow()
            elapsed_days = (current_time - last_scraped_time).days
            return elapsed_days >= frequency_days
    # 如果文檔不存在或沒有記錄，則需要爬取
    return True


def scrape_google_reviews(
    keyword, driver_path, collection_name="reviews", frequency_days=7
):
    logging.info(f"Start scraping for keyword: {keyword}")
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # service = Service(driver_path)
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    wait = WebDriverWait(driver, 15)

    all_reviews = []

    try:
        if keyword in scraping_status:
            scraping_status[keyword]["status"] = "processing"
            scraping_status[keyword]["message"] = "連接到 Google Maps"

        logging.info("Connecting to Google Maps preview page...")
        driver.get("https://www.google.com.tw/maps/preview")
        time.sleep(3)

        logging.info("Searching for the place...")
        search_box = wait.until(
            EC.presence_of_element_located((By.ID, "searchboxinput"))
        )
        search_box.send_keys(keyword)
        search_box.send_keys(Keys.ENTER)
        time.sleep(2)

        logging.info("Clicking on review tab...")
        review_tab = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//button[.//div[text()='評論']]"))
        )
        review_tab.click()
        time.sleep(2)

        scrollable_div = wait.until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    '//*[@id="QA0Szd"]/div/div/div[1]/div[2]/div/div[1]/div/div/div[2]',
                )
            )
        )

        logging.info("Scrolling to load reviews...")
        for i in range(10):
            driver.execute_script(
                "arguments[0].scrollTop = arguments[0].scrollHeight;", scrollable_div
            )
            if keyword in scraping_status:
                scraping_status[keyword]["message"] = f"載入更多評論 ({i+1}/10)"
            time.sleep(0.5)

        logging.info("Extracting reviews...")
        reviews = driver.find_elements(By.CSS_SELECTOR, "div.jftiEf.fontBodyMedium")
        total_reviews = len(reviews)
        logging.info(f"Total extracted reviews: {total_reviews}")

        if keyword in scraping_status:
            scraping_status[keyword]["total_reviews"] = total_reviews

        # 獲取上次爬取的最新評論時間
        doc_ref = db.collection("reviews").document(keyword)
        doc = doc_ref.get()
        last_scraped_time = None
        if doc.exists:
            last_scraped = doc.to_dict().get("last_scraped")
            if last_scraped:
                last_scraped_time = last_scraped.to_pydatetime()

        for idx, review in enumerate(reviews, 1):
            try:
                more_button = review.find_elements(
                    By.CSS_SELECTOR, "button.w8nwRe.kyuRq"
                )
                if more_button:
                    more_button[0].click()
                    time.sleep(1)

                reviewer = review.find_element(By.CSS_SELECTOR, "div.d4r55").text
                rating_element = review.find_element(By.CSS_SELECTOR, "span.kvMYJc")
                rating = (
                    rating_element.get_attribute("aria-label")
                    if rating_element
                    else "無評分"
                )
                comment = review.find_element(By.CSS_SELECTOR, "span.wiI7pd").text

                # 嘗試獲取評論時間
                try:
                    review_time_str = review.find_element(
                        By.CSS_SELECTOR, "span.rsqaWe"
                    ).text
                    # 解析評論時間（根據實際格式調整）
                    review_time = datetime.strptime(
                        review_time_str, "%Y-%m-%d"
                    )  # 示例格式
                except Exception:
                    review_time = None

                # 如果評論時間早於上次爬取時間，則跳過
                if (
                    last_scraped_time
                    and review_time
                    and review_time < last_scraped_time
                ):
                    logging.info(f"跳過早於上次爬取的評論: {review_time}")
                    continue

                review_data = {
                    "評論編號": idx,
                    "用戶": reviewer,
                    "評分": rating,
                    "評論": comment,
                    "關鍵字": keyword,
                    "抓取時間": firestore.SERVER_TIMESTAMP,
                    "評論時間": review_time_str if review_time else None,
                }
                all_reviews.append(review_data)

                if keyword in scraping_status:
                    scraping_status[keyword]["processed_reviews"] = idx

            except Exception as e:
                logging.error(f"處理第 {idx} 則評論時發生錯誤: {e}")
                continue

        logging.info("Reviews extracted, uploading to Firestore...")
        # 上傳評論到 Firestore
        upload_reviews_to_firestore(collection_name, all_reviews)

        logging.info("Reviews uploaded, starting QA analysis...")
        # 爬完之後進行 QA 分析和總結
        analysis_result = analyze_reviews_with_qa(all_reviews)

        logging.info("QA analysis completed, uploading analysis to Firestore...")
        # 上傳分析結果到 Firestore
        upload_analysis_to_firestore(collection_name, keyword, analysis_result)

        if keyword in scraping_status:
            scraping_status[keyword]["status"] = "completed"
            scraping_status[keyword][
                "message"
            ] = f"完成，共收集 {len(all_reviews)} 則評論，並產生QA分析結果"

        logging.info("Scraping and analysis completed.")
    except Exception as e:
        logging.error(f"Error during scraping: {e}")
        if keyword in scraping_status:
            scraping_status[keyword]["status"] = "error"
            scraping_status[keyword]["error"] = str(e)
        raise
    finally:
        driver.quit()


def analyze_reviews_with_qa(reviews):
    logging.info("Analyzing reviews with QA pipeline...")

    # 讓問題本身更明確,引導模型給出更準確的答案
    question1 = "根據這段評論,這家餐廳實際表現好的地方有哪些?請列出具體的優點。若無則回答「無優點」"
    question2 = "根據這段評論,這家餐廳實際表現不好的地方有哪些?請列出具體的缺點。若無則回答「無缺點」"
    question3 = (
        "根據這段評論,有哪些值得一試的餐點或特色菜?請列出具體菜名。若無則回答「無推薦」"
    )

    positives = []
    negatives = []
    recommendations = []

    seen_positives = set()
    seen_negatives = set()
    seen_recommendations = set()

    for idx, r in enumerate(reviews, start=1):
        context = r.get("評論", "")
        if not context:
            continue

        try:
            ans1 = qa_pipeline(question=question1, context=context)
            ans2 = qa_pipeline(question=question2, context=context)
            ans3 = qa_pipeline(question=question3, context=context)

            # 只過濾重複內容和無效答案
            if ans1 and ans1["answer"] and ans1["answer"] != "無優點":
                if ans1["answer"] not in seen_positives:
                    positives.append(ans1["answer"])
                    seen_positives.add(ans1["answer"])

            if ans2 and ans2["answer"] and ans2["answer"] != "無缺點":
                if ans2["answer"] not in seen_negatives:
                    negatives.append(ans2["answer"])
                    seen_negatives.add(ans2["answer"])

            if ans3 and ans3["answer"] and ans3["answer"] != "無推薦":
                if ans3["answer"] not in seen_recommendations:
                    recommendations.append(ans3["answer"])
                    seen_recommendations.add(ans3["answer"])

            if idx % 10 == 0:
                logging.info(f"QA processed {idx}/{len(reviews)} reviews...")

        except Exception as e:
            logging.error(f"QA處理第 {idx} 則評論時出現問題: {e}")
            continue

    # 在進行 GPT 總結前，先進行一次 GPT 篩選
    logging.info("Starting GPT filtering...")
    filtered_results = filter_with_gpt(positives, negatives, recommendations)

    logging.info("GPT filtering completed, starting final summary...")
    summary_result = summarize_with_gpt(
        filtered_results["positives"],
        filtered_results["negatives"],
        filtered_results["recommendations"],
    )

    return {"individual_analysis": filtered_results, "summary": summary_result}


def filter_with_gpt(positives, negatives, recommendations):
    prompt = f"""
請以 JSON 格式回答。請仔細分析以下餐廳評論中提取出的內容，並進行二次篩選，確保內容的準確性和相關性。

原始優點列表:
{json.dumps(positives, ensure_ascii=False)}

原始缺點列表:
{json.dumps(negatives, ensure_ascii=False)}

原始推薦列表:
{json.dumps(recommendations, ensure_ascii=False)}

請執行以下任務：
1. 移除不相關或重複的內容
2. 確保每個類別的內容確實屬於該類別
3. 整合相似的描述
4. 移除模糊不清的評價

請以 JSON 格式返回結果，格式如下：
{{
   "positives": ["優點1", "優點2", ...],
   "negatives": ["缺點1", "缺點2", ...],
   "recommendations": ["推薦1", "推薦2", ...]
}}
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "你是一個專業的餐廳評論分析專家。請以 JSON 格式回傳分析結果。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            # response_format={"type": "json_object"}  # 這行無效，需要解析文本
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logging.error(f"GPT 篩選時發生錯誤: {e}")
        return {
            "positives": positives,
            "negatives": negatives,
            "recommendations": recommendations,
        }


def summarize_with_gpt(positives, negatives, recommendations):
    prompt = f"""
分析以下餐廳評論的優點、缺點和推薦項目清單，並提供一個簡潔的總結。請直接給出分析結果，不要使用「從評論中可以看出」之類的引導語。評分請先單獨列出，並同時整合在內容中。

優點：
{json.dumps(positives, ensure_ascii=False)}

缺點：
{json.dumps(negatives, ensure_ascii=False)}

推薦必點：
{json.dumps(recommendations, ensure_ascii=False)}

要求：
1. 請直接陳述分析結果
2. 保持專業客觀的語氣
3. 重點摘要餐廳的特色和服務
4. 整體評分(滿分10分)請先列出，並再自然地融入描述中
5. 最後總結這家餐廳適合什麼樣的消費者，並用一段話總結一下整體感受
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "你是一位專業的餐廳評論家，請以簡潔直接的方式分析餐廳評論。避免使用「從評論可以看出」等引導語。",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=1024,
        )
        answer = response.choices[0].message.content.strip()
        logging.info("GPT summarization completed.")
    except Exception as e:
        logging.error(f"GPT 總結時發生錯誤: {e}")
        answer = f"GPT 總結時發生錯誤: {e}"

    return answer


@app.route("/api/scrape-reviews", methods=["POST"])
def start_scrape():
    try:
        data = request.json
        keyword = data.get("keyword")

        if not keyword:
            logging.warning("No keyword provided in request")
            return jsonify({"error": "No keyword provided"}), 400

        # 判斷是否需要爬取
        if not should_scrape(keyword):
            logging.info(f"不需要爬取 {keyword}，因為未達到爬取頻率")
            return (
                jsonify(
                    {
                        "message": "Scraping not needed at this time",
                        "status": "not_required",
                    }
                ),
                200,
            )

        # 初始化狀態
        scraping_status[keyword] = {
            "status": "initializing",
            "message": "初始化中",
            "total_reviews": 0,
            "processed_reviews": 0,
        }

        logging.info(f"Starting scrape thread for keyword: {keyword}")
        # 開始爬蟲線程
        thread = threading.Thread(
            target=scrape_google_reviews,
            args=(
                keyword,
                "scraper/chromedriver-win32/chromedriver-win64/chromedriver.exe",
                "reviews",
            ),  # 確保 chromedriver 路徑正確
        )
        active_threads[keyword] = thread
        thread.start()

        return jsonify({"message": "Scraping started", "status": "processing"})

    except Exception as e:
        logging.error(f"Error when starting scrape: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/reviews/<keyword>", methods=["GET"])
def get_reviews(keyword):
    try:
        reviews_ref = db.collection("reviews")
        print("keyword: " + keyword)
        query = reviews_ref.where("`關鍵字`", "==", keyword).stream()

        reviews = []
        for doc in query:
            review = doc.to_dict()
            # 移除 Firestore 內部的字段
            review.pop("關鍵字", None)
            review.pop("抓取時間", None)
            reviews.append(review)

        if reviews:
            return jsonify(reviews)
        return jsonify([]), 404
    except Exception as e:
        logging.error(f"Error getting reviews for {keyword}: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/reviews/<keyword>_analysis", methods=["GET"])
def get_analysis(keyword):
    try:
        doc_ref = db.collection("reviews").document(keyword)
        doc = doc_ref.get()
        if doc.exists:
            analysis = doc.to_dict().get("分析結果", {})
            return jsonify(analysis)
        return jsonify({"error": "Analysis not found"}), 404
    except Exception as e:
        logging.error(f"Error getting analysis for {keyword}: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # 使用PEFT從LoRA模型中取config
    logging.info("Loading PEFT config...")
    peft_config = PeftConfig.from_pretrained(model_path)

    logging.info("Loading base model and tokenizer...")
    base_tokenizer = AutoTokenizer.from_pretrained(peft_config.base_model_name_or_path)
    base_model = AutoModelForQuestionAnswering.from_pretrained(
        peft_config.base_model_name_or_path
    )

    logging.info("Loading LoRA weights...")
    model = PeftModel.from_pretrained(base_model, model_path)
    tokenizer = base_tokenizer

    logging.info("Initializing QA pipeline...")
    qa_pipeline = pipeline("question-answering", model=model, tokenizer=tokenizer)

    app.run(debug=True, port=5000)
