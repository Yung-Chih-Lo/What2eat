from vertexai.preview.generative_models import GenerativeModel
from google.oauth2 import service_account
from google.cloud import aiplatform
import json
import os

# 取得專案 ID 和憑證路徑
PROJECT_ID = "data-model-lecture"
credentials = service_account.Credentials.from_service_account_file(
    os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "YOUR_GOOGLE_APPLICATION_CREDENTIALS")
)

# 初始化 AI Platform，傳遞憑證
aiplatform.init(project=PROJECT_ID, credentials=credentials, location="us-central1")

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
    
    model = GenerativeModel("gemini-1.5-flash-002")
    try:
        response = model.generate_content(
            prompt,
            generation_config={
                "max_output_tokens": 8192,
                "temperature": 0.3,
                "top_p": 0.5,
                "top_k": 10,
            },
            stream=False,
        )
        return response.text
    except Exception as e:
        print(f"發生錯誤：{e}")
        return "發生錯誤處理資料"

def t1():
    data = json.load(open("first_summary.json", "r", encoding="utf-8"))
    positives = data["positives"]
    negatives = data["negatives"]
    recommendations = data["recommendations"]
    
    context = """
        你是一位專業的餐廳評論家，擁有豐富的經驗。
        
        要求：
        1. 請直接陳述分析結果
        2. 保持專業客觀的語氣
        3. 重點摘要餐廳的特色和服務
        4. 整體評分(滿分5分)請先列出，並再自然地融入描述中
        5. 最後總結這家餐廳適合什麼樣的消費者，並用一段話總結一下整體感受
        6. 不要使用「從評論中可以看出」之類的引導語。評分請先單獨列出，並同時整合在內容中。
        
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
    # 取得答案
    answer = answer_question_gemini(context, questions)

    with open("data_analysis_summary.json", "w", encoding="utf-8") as f:
        f.write(answer)

def t2():
    data = json.load(open("first.json", "r", encoding="utf-8"))
    positives = data["positive"]
    negatives = data["negative"]
    recommendations = data["recommendation"]
    
    context = """
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
        6. 可以依照原文描述一下
    """
    questions = f"""
    請參考以下原始資料，根據上述要求進行分析和整理。
        原始優點列表:
        {json.dumps(positives, ensure_ascii=False)}

        原始缺點列表:
        {json.dumps(negatives, ensure_ascii=False)}

        原始推薦列表:
        {json.dumps(recommendations, ensure_ascii=False)}
    """
    
    # 取得答案
    answer = answer_question_gemini(context, questions)
    answer = answer.strip()
    answer_dict = json.loads(answer)
    
    with open("first_summary.json", "w", encoding="utf-8") as f:
        json.dump(answer_dict, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    
    t1()

    
   
