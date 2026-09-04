import os
import json
import time
from playwright.sync_api import sync_playwright

def run():
    # Secretsから環境変数を取得
    school_id = os.environ.get("LOILO_SCHOOL_ID")
    user_id = os.environ.get("LOILO_USER_ID")
    password = os.environ.get("LOILO_PASSWORD")

    unsubmitted_items = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        # 1. ロイロノートWeb版へアクセス
        page.goto("https://loilonote.app")
        
        # 「ロイロノートでログイン」ボタンをクリック
        page.wait_for_selector("text=ロイロノートでログイン", timeout=15000)
        page.click("text=ロイロノートでログイン")

        # 2. 学校ID・ユーザーID・パスワードを入力してログイン
        page.wait_for_selector("input[placeholder*='学校ID']", timeout=15000)
        page.fill("input[placeholder*='学校ID']", school_id)
        page.fill("input[placeholder*='ユーザーID']", user_id)
        page.fill("input[placeholder*='パスワード']", password)
        page.click("button:has-text('ログイン')")

        # 3. ダッシュボード読込待ち
        page.wait_for_selector(".left-pane", timeout=30000)

        # 4. 「募集中」バッジのある教科を巡回
        recruiting_elements = page.query_selector_all("text=募集中")

        for elem in recruiting_elements:
            parent_subject = elem.evaluate("node => node.closest('.subject-item, li, div')")
            subject_name = parent_subject.text_content().replace("募集中", "").strip() if parent_subject else "教科"

            elem.click()
            time.sleep(2)

            # 5. 未提出の提出箱を抽出（緑色のチェックマークが付いていないもの）
            boxes = page.query_selector_all(".submission-box-item")
            for box in boxes:
                is_submitted = box.query_selector(".icon-check-green, [data-status='submitted']")
                if not is_submitted:
                    title = box.query_selector(".title").text_content().strip() if box.query_selector(".title") else "宿題"
                    deadline = box.query_selector(".deadline").text_content().strip() if box.query_selector(".deadline") else ""
                    
                    unsubmitted_items.append({
                        "subject": subject_name,
                        "title": title,
                        "deadline": deadline
                    })

        browser.close()

    # 結果をJSONとして保存
    result = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(unsubmitted_items),
        "items": unsubmitted_items
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    run()
