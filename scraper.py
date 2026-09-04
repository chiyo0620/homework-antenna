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
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print("1. ロイロノートWeb版へアクセス中...")
        page.goto("https://loilonote.app", wait_until="domcontentloaded")
        time.sleep(3)

        # 「ロイロノート」が含まれるログインボタンがあればクリック（すでにフォームが出ている場合はスキップ）
        loilo_btn = page.query_selector("text=/ロイロノート/")
        if loilo_btn:
            print("ログイン選択ボタンをクリックします...")
            try:
                loilo_btn.click()
                time.sleep(2)
            except Exception as e:
                print(f"ボタンクリックをスキップして直接フォームを探します: {e}")

        # 2. 入力フォームの読み込み待ち
        print("入力フォームを探しています...")
        page.wait_for_selector("input", timeout=20000)

        # 学校ID・ユーザーID・パスワード入力欄を取得
        inputs = page.query_selector_all("input")
        
        school_input = page.query_selector("input[placeholder*='学校']") or (inputs[0] if len(inputs) > 0 else None)
        user_input = page.query_selector("input[placeholder*='ユーザー']") or (inputs[1] if len(inputs) > 1 else None)
        pass_input = page.query_selector("input[type='password']") or (inputs[2] if len(inputs) > 2 else None)

        if school_input and user_input and pass_input:
            school_input.fill(school_id)
            user_input.fill(user_id)
            pass_input.fill(password)
            print("ログイン情報を入力しました。")

        # ログインボタンをクリック
        login_btn = page.query_selector("button:has-text('ログイン')") or page.query_selector("input[type='submit']")
        if login_btn:
            login_btn.click()
            print("ログインボタンを押しました。")

        # 3. ダッシュボード表示待ち
        print("ダッシュボードの読み込み待ち...")
        page.wait_for_selector(".left-pane, .subject-item, text=募集中", timeout=30000)
        print("ログイン成功！")

        # 4. 「募集中」バッジのある教科を巡回
        recruiting_elements = page.query_selector_all("text=募集中")
        print(f"募集中の教科数: {len(recruiting_elements)}")

        for elem in recruiting_elements:
            parent_subject = elem.evaluate("node => node.closest('.subject-item, li, div')")
            subject_name = parent_subject.text_content().replace("募集中", "").strip() if parent_subject else "教科"

            elem.click()
            time.sleep(2)

            # 5. 未提出の提出箱を抽出
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
    print("データ保存完了!")

if __name__ == "__main__":
    run()
