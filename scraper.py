import os
import json
import time
from playwright.sync_api import sync_playwright

def run():
    school_id = os.environ.get("LOILO_SCHOOL_ID")
    user_id = os.environ.get("LOILO_USER_ID")
    password = os.environ.get("LOILO_PASSWORD")

    unsubmitted_items = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        # 1. ロイロノートWeb版へアクセス・ログイン
        page.goto("https://loilonote.app")
        page.wait_for_selector("text=ロイロノートでログイン", timeout=15000)
        page.click("text=ロイロノートでログイン")

        page.fill("input[placeholder*='学校ID']", school_id)
        page.fill("input[placeholder*='ユーザーID']", user_id)
        page.fill("input[placeholder*='パスワード']", password)
        page.click("button:has-text('ログイン')")

        # ダッシュボード読込待ち
        page.wait_for_selector(".left-pane", timeout=20000)

        # 2. 「募集中」バッジのある教科を巡回
        # 左側リスト内の「募集中」要素を取得
        recruiting_elements = page.query_selector_all("text=募集中")

        for elem in recruiting_elements:
            # 教科名を取得（親要素からテキスト抽出）
            parent_subject = elem.evaluate("node => node.closest('.subject-item, li, div')")
            subject_name = parent_subject.text_content().replace("募集中", "").strip() if parent_subject else "教科"

            # 教科をクリックして提出箱一覧を開く
            elem.click()
            time.sleep(2)

            # 3. 未提出の提出箱を抽出（緑色のチェックマークが付いていないもの）
            boxes = page.query_selector_all(".submission-box-item") # 実際の要素に合わせて判定
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
