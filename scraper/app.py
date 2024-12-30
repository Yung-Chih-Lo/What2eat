# app.py
import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from math import radians, sin, cos, sqrt, atan2
from flask import Flask, jsonify, request
from flask_cors import CORS
from google.cloud import aiplatform, firestore
from google.oauth2 import service_account
from peft import PeftConfig, PeftModel
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from transformers import AutoModelForQuestionAnswering, AutoTokenizer, pipeline
from vertexai.preview.generative_models import GenerativeModel
from webdriver_manager.chrome import ChromeDriverManager
import requests

# 設定logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("app.log"), logging.StreamHandler()],
)

PROJECT_ID = "data-model-lecture"
GOOGLE_MAPS_API_KEY = os.getenv('VITE_GOOGLE_MAPS_API_KEY', 'YOUR_GOOGLE_MAPS_API_KEY')
GOOGLE_APPLICATION_CREDENTIALS = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'YOUR_GOOGLE_APPLICATION_CREDENTIALS')

app = Flask(__name__)
CORS(app)

# export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/service-account-file.json" -> 環境變數 mac
# set GOOGLE_APPLICATION_CREDENTIALS=C:\Users\username\Downloads\your-service-account-file.json -> 環境變數 windows
credentials = service_account.Credentials.from_service_account_file(
    GOOGLE_APPLICATION_CREDENTIALS
)

# 初始化 AI Platform，傳遞憑證
aiplatform.init(project=PROJECT_ID, credentials=credentials, location="us-central1")

# 初始化 Firestore 客戶端
db = firestore.Client(
    project=PROJECT_ID, credentials=credentials, database="dm-firestore"
)

# 用於儲存爬蟲狀態
scraping_status = {}
# 用於儲存正在執行的線程
active_threads = {}


def save2json(dir_name: str, file_name: str, reviews: list | dict):
    """將數據保存到本地 JSON 文件"""
    if not os.path.exists(dir_name):
        os.makedirs(dir_name)

    file_name = os.path.join(dir_name, file_name)
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(reviews, f, ensure_ascii=False, indent=4)
    logging.info(f"評論數據已保存到: {file_name}")


def build_prompt(context, question):
    """製作餵給 Gemini 的 Prompt"""
    prompt = f"""
    Instructions: Answer the question using the following Context.

    Context: {context}

    Question: {question}
    """
    return prompt


def answer_question_gemini(context, question):
    """使用 Gemini 模型回答問題"""
    prompt = build_prompt(context, question)

    model = GenerativeModel("gemini-1.5-pro-002")
    try:
        response = model.generate_content(
            prompt,
            generation_config={
                "max_output_tokens": 8192,
                "temperature": 0.2,
                "top_p": 0.5,
                "top_k": 10,
            },
            stream=False,
        )
        return response.text
    except Exception as e:
        logging.error(f"發生錯誤：{e}")


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
            last_scraped_time = last_scraped
            current_time = datetime.now(timezone.utc)
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

        driver.get("https://www.google.com.tw/maps/preview")
        search_box = wait.until(
            EC.presence_of_element_located((By.ID, "searchboxinput"))
        )
        search_box.send_keys(keyword)
        search_box.send_keys(Keys.ENTER)

        review_tab = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//button[.//div[text()='評論']]"))
        )
        review_tab.click()

        scrollable_div = wait.until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    '//*[@id="QA0Szd"]/div/div/div[1]/div[2]/div/div[1]/div/div/div[2]',
                )
            )
        )

        logging.info("Scrolling to load reviews...")
        for _ in range(10):
            previous_height = driver.execute_script(
                "return arguments[0].scrollHeight;", scrollable_div
            )
            driver.execute_script(
                "arguments[0].scrollTop = arguments[0].scrollHeight;", scrollable_div
            )

            # 等待 scrollHeight 增加，代表有載入新評論
            try:
                wait.until(
                    lambda d: driver.execute_script(
                        "return arguments[0].scrollHeight;", scrollable_div
                    )
                    > previous_height
                )
            except:
                # 若超過指定秒數沒變化，表示已無更多評論可以載入
                break

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
                last_scraped_time = last_scraped

        for idx, review in enumerate(reviews, 1):
            try:
                more_button = review.find_elements(
                    By.CSS_SELECTOR, "button.w8nwRe.kyuRq"
                )
                if more_button:
                    more_button[0].click()
                    time.sleep(0.1) # NOTE 修改成0.1秒

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
        analysis_result = analyze_reviews_with_qa_lora(all_reviews)
        # API會使用太多資源，所以使用 local LLM 配合 lora 進行分析
        # analysis_result = analyze_reviews_with_qa_gemeni(all_reviews)

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


def analyze_reviews_with_qa_lora(reviews):
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

    results = {
        "positives": positives,
        "negatives": negatives,
        "recommendations": recommendations,
    }

    save2json(dir_name="results", file_name="first_result.json", reviews=results)

    filtered_results = filter_with_gemini(positives, negatives, recommendations)

    save2json(dir_name="results", file_name="filtered_result.json", reviews=results)

    logging.info("GPT filtering completed, starting final summary...")
    summary_result = summarize_with_gemini(
        filtered_results["positives"],
        filtered_results["negatives"],
        filtered_results["recommendations"],
    )

    final_result = {"individual_analysis": filtered_results, "summary": summary_result}

    save2json(dir_name="results", file_name="final_result.json", reviews=final_result)

    return final_result


def analyze_reviews_with_qa_gemeni(reviews):
    logging.info("Analyzing reviews with QA pipeline...")

    # 讓問題本身更明確,引導模型給出更準確的答案
    context1 = """
        你是評論大師，擁有數十年的餐廳評論經驗。請你根據這段使用者給的評價，回答這家餐廳實際表現好的地方有什麼？
    
        以下是你必須遵守的：
        1. 回答必須是有意義的，不能是無意義的文字。
        2. 只需要一個，且控制在20個字以內。
        3. 具體的描述，不要含糊不清、太攏統。
        4. 若無則回答「無優點」
        
        給你一個例子：
        "義大利麵🍝和披薩🍕等主餐價位都落在350左右
        排餐像是牛排、龍蝦🦞價位才比較高
        披薩是10吋的用料實在cp值很高
        披薩上的起司、明太子都很濃郁 唐揚雞是雞腿肉也很夠味 可以2～3人一起分😋
        主餐可以+200元就有前菜、飲料、沙拉、甜點可以選👍🏻"
        
        你需要回答：
        "披薩用料實在cp值很高"
    """
    context2 = """
        你是評論大師，擁有數十年的餐廳評論經驗。請你根據這段使用者給的評價，回答這家餐廳實際表現「不好」的地方有什麼？
        
        以下是你必須遵守的：
        1. 回答必須是有意義的，不能是無意義的文字。
        2. 只需要一個，且控制在20個字以內。
        3. 具體的描述，不要含糊不清、太攏統。
        4. 若無則回答「無缺點」
        
        給你一個例子：
        "義大利麵🍝和披薩🍕等主餐價位都落在350左右
        排餐像是牛排、龍蝦🦞價位才比較高
        披薩是10吋的用料實在cp值很高
        披薩上的起司、明太子都很濃郁 唐揚雞是雞腿肉也很夠味 可以2～3人一起分😋
        主餐可以+200元就有前菜、飲料、沙拉、甜點可以選👍🏻"
        
        你需要回答：
        "排餐價位高"
    """
    context3 = """
        你是評論大師，擁有數十年的餐廳評論經驗。請你根據這段使用者給的評價，有哪些值得一試的餐點或特色菜？
        
        以下是你必須遵守的：
        1. 回答必須是有意義的，不能是無意義的文字。
        2. 只需要一個，且控制在20個字以內。
        3. 列出具體菜名，不要含糊不清、太攏統。
        4. 若無則回答「無推薦」。
        
        給你一個例子：
        "義大利麵🍝和披薩🍕等主餐價位都落在350左右
        排餐像是牛排、龍蝦🦞價位才比較高
        披薩是10吋的用料實在cp值很高
        披薩上的起司、明太子都很濃郁 唐揚雞是雞腿肉也很夠味 可以2～3人一起分😋
        主餐可以+200元就有前菜、飲料、沙拉、甜點可以選👍🏻"
        
        你需要回答：
        "義大利麵和披薩"
    """

    positives = []  # 優點
    negatives = []  # 缺點
    recommendations = []  # 推薦

    seen_positives = set()  # 用於過濾重複內容
    seen_negatives = set()  # 用於過濾重複內容
    seen_recommendations = set()  # 用於過濾重複內容

    for idx, r in enumerate(reviews, start=1):
        question = r.get("評論", "")
        if not question:
            continue

        try:
            ans1 = answer_question_gemini(context=context1, question=question)

            ans2 = answer_question_gemini(context=context2, question=question)

            ans3 = answer_question_gemini(context=context3, question=question)

            # 只過濾重複內容和無效答案
            if ans1 and ans1 != "無優點":
                if ans1 not in seen_positives:
                    positives.append(ans1)
                    seen_positives.add(ans1)

            if ans2 and ans2 != "無缺點":
                if ans2 not in seen_negatives:
                    negatives.append(ans2)
                    seen_negatives.add(ans2)

            if ans3 and ans3 != "無推薦":
                if ans3 not in seen_recommendations:
                    recommendations.append(ans3)
                    seen_recommendations.add(ans3)

            if idx % 10 == 0:
                logging.info(f"QA processed {idx}/{len(reviews)} reviews...")

        except Exception as e:
            logging.error(f"QA處理第 {idx} 則評論時出現問題: {e}")
            continue

    # 在進行 gemini 總結前，先進行一次 gemini 篩選
    logging.info("Starting gemini filtering...")

    # data ={
    #     "positives": positives,
    #     "negatives": negatives,
    #     "recommendations": recommendations
    # }
    # print(data)

    # with open("first.json", "w", encoding='utf-8') as f:
    #     json.dump(data, f, ensure_ascii=False, indent=4)

    filtered_results = filter_with_gemini(positives, negatives, recommendations)  # json

    logging.info("gemini filtering completed, starting final summary...")
    summary_result = summarize_with_gemini(  # str
        filtered_results["positives"],
        filtered_results["negatives"],
        filtered_results["recommendations"],
    )

    return {"individual_analysis": filtered_results, "summary": summary_result}


def filter_with_gemini(positives, negatives, recommendations):
    context = (
        context
    ) = """
        你是一個專業的餐廳評論分析專家。
        
        請 step by step 仔細分析餐廳評論中提取出的內容，並進行二次篩選，確保內容的準確性和相關性。
        
        遵守以下規則：
        1. 移除不相關或重複的內容
        2. 整合相似的描述
        3. 移除模糊不清的評價，不要保留沒有意義的文字
        4. 請務必以 JSON 格式返回結果，格式如下：
        {
            "positives": list[str],
            "negatives": list[str],
            "recommendations": list[str]
        }
        5. json 回覆時，不要有多餘的字體，像是 "json"、換行符號等
    """

    question = f"""
    請參考以下優缺點和推薦的原始資料，並根據上述要求進行分析和整理。
        original positives:
        {json.dumps(positives, ensure_ascii=False)}

        original negatives:
        {json.dumps(negatives, ensure_ascii=False)}

        original recommendations:
        {json.dumps(recommendations, ensure_ascii=False)}
    """

    try:
        response = answer_question_gemini(context=context, question=question)
        response = response.strip()
        logging.info("gemini filtering completed.")
        return json.loads(response)
    except Exception as e:
        logging.error(f"gemini 篩選時發生錯誤: {e}")
        return {
            "positives": positives,
            "negatives": negatives,
            "recommendations": recommendations,
        }


def summarize_with_gemini(positives, negatives, recommendations):
    context = """
        你是一位專業的餐廳評論家，擁有豐富的經驗。用一段話總結一下整體感受，這家餐廳適合什麼樣的消費者，有哪些值得改進的地方。
        
        要求：
        1. 請直接陳述分析結果
        2. 保持專業客觀的語氣
        3. 重點摘要餐廳的特色和服務
        4. 整體評分(滿分5分)請先列出，並再自然地融入描述中
        5. 不要使用「從評論中可以看出」之類的引導語。評分請先單獨列出，並同時整合在內容中。
        
        我給你一個回答例如：
        "評分：4/5\n\n這家位於木新路的義大利料理餐廳擁有多樣化的菜單，包括套餐和早午餐選項，尤其推薦如牛排、義大利麵和烤飯等主菜。特色甜點如提拉米蘇和布朗尼蛋糕也深受好評。環境方面，裝潢古典且富有歐式風格，提供了一個氣氛佳且舒適的用餐環境，適合多人聚餐。\n\n儘管服務態度普遍親切，但存在服務生難以找到的問題，可能會影響顧客的用餐體驗。此外，部分餐點如豬肉串和沙拉的口味有待提升。餐廳位置對某些顧客來說可能不太方便。\n\n總體來說，這家餐廳因其美味的食物、多樣的選擇和優雅的環境受到推崇。對於尋求美味義大利料理和愉悅用餐環境的顧客來說，是一個不錯的選擇。然而，建議餐廳改進服務效率和部分菜品的品質，以提升顧客滿意度。总体而言，這家餐廳非常適合喜歡嘗試高品質義大利菜和享受美麗環境的顧客。"
    """
    questions = f"""
    現在你必須根據以下這些資訊，請為餐廳評論提供一個簡潔的總結。
    
        優點：
        {json.dumps(positives, ensure_ascii=False)}

        缺點：
        {json.dumps(negatives, ensure_ascii=False)}

        推薦必點：
        {json.dumps(recommendations, ensure_ascii=False)}
    """

    try:
        answer = answer_question_gemini(context=context, question=questions)
        logging.info("gemini summarization completed.")
    except Exception as e:
        logging.error(f"gemini 總結時發生錯誤: {e}")
        answer = f"gemini 總結時發生錯誤: {e}"

    return answer


@app.route("/api/reviews/<keyword>/status", methods=["GET"])
def get_status(keyword):
    try:
        doc_ref = db.collection("reviews").document(keyword)
        doc = doc_ref.get()
        if doc.exists:
            # analysis = doc.to_dict().get("分析結果", {})
            scraping_status[keyword]["status"] = "completed"
            return jsonify(scraping_status[keyword])
        return jsonify({"status": "not_found", "message": "No scraping job found"}), 404
    except Exception as e:
        logging.error(f"Error getting analysis for {keyword}: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if keyword in scraping_status:
            return jsonify(scraping_status[keyword])
        return jsonify({"status": "not_found", "message": "No scraping job found"}), 404


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
            # 如果沒有狀態，則會無法觸發前端抓取資訊
            scraping_status[keyword] = {
                "status": "completed",
                "message": "未達到爬取頻率",
                "total_reviews": 0,
                "processed_reviews": 0,
            }
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
                "scraper/chromedriver-win32/chromedriver-win64/chromedriver.exe",  # NOTE 確保 chromedriver 路徑正確
                "reviews",
            ),
        )
        active_threads[keyword] = thread
        thread.start()

        return jsonify({"message": "Scraping started", "status": "processing"})

    except Exception as e:
        logging.error(f"Error when starting scrape: {e}")
        return jsonify({"error": str(e)}), 500

def calculate_distance(loc1, loc2):
    """
    使用 Haversine 公式計算兩點之間的距離（米）
    """
    R = 6371e3  # 地球半徑（米）
    phi1 = radians(loc1['lat'])
    phi2 = radians(loc2['lat'])
    delta_phi = radians(loc2['lat'] - loc1['lat'])
    delta_lambda = radians(loc2['lng'] - loc1['lng'])

    a = sin(delta_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(delta_lambda / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    distance = R * c
    return round(distance)

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

@app.route('/api/nearby-restaurants', methods=['GET'])
def get_nearby_restaurants():
    lat = request.args.get('lat')
    lng = request.args.get('lng')
    radius = request.args.get('radius', 1500)

    if not lat or not lng:
        return jsonify({'error': 'Missing latitude or longitude'}), 400

    try:
        lat = float(lat)
        lng = float(lng)
        radius = int(radius)
    except ValueError:
        return jsonify({'error': 'Invalid latitude, longitude, or radius format'}), 400

    url = (
        f'https://maps.googleapis.com/maps/api/place/nearbysearch/json'
        f'?location={lat},{lng}&radius={radius}&type=restaurant&key={GOOGLE_MAPS_API_KEY}'
    )

    try:
        response = requests.get(url)
        data = response.json()

        if data.get('status') != 'OK':
            raise Exception(f"Google Places API error: {data.get('status')}")

        results = []
        for place in data.get('results', []):
            place_lat = place['geometry']['location']['lat']
            place_lng = place['geometry']['location']['lng']
            distance = calculate_distance(
                {'lat': lat, 'lng': lng},
                {'lat': place_lat, 'lng': place_lng}
            )
            results.append({
                'id': place['place_id'],
                'name': place['name'],
                'address': place.get('vicinity', ''),
                'lat': place_lat,
                'lng': place_lng,
                'distance': distance
            })

        return jsonify(results)
    except Exception as error:
        print(error)
        return jsonify({'error': 'Failed to fetch restaurants'}), 500

if __name__ == "__main__":
    # 設定QA模型路徑（請確認模型文件在此路徑下）
    model_path = r"scraper/lora_qa_model_new/lora_qa_model_new"

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
