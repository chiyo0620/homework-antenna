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
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            print("1. ロイロノートWeb版へアクセス中...")
            page.goto("https://loilonote.app", wait_until="networkidle")
            time.sleep(3)

            print(f"アクセス完了: URL={page.url}")

            # 画面上の選択肢（ボタン・リンク）をログに出力
            elements = page.query_selector_all("button, a, div[role='button']")
            btn_texts = [e.text_content().strip() for e in elements if e.text_content().strip()]
            print(f"検出されたボタン類: {btn_texts}")

            # 「ロイロノート」「ID」「ログイン」に関連するボタンを探してクリック
            target = None
            for e in elements:
                txt = e.text_content().strip()
                if any(k in txt for k in ["ロイロ", "学校ID", "IDでログイン", "ログイン"]):
                    target = e
                    break

            if target:
                print(f"ログインボタン『{target.text_content().strip()}』をクリックします...")
                target.click()
                time.sleep(3)

            # 2. 入力フォームの確認
            print("入力フォームを探しています...")
            page.wait_for_selector("input", timeout=15000)

            inputs = page.query_selector_all("input")
            print(f"入力欄（input）を {len(inputs)} 個検出しました。")

            school_input = page.query_selector("input[placeholder*='学校']") or (inputs[0] if len(inputs) > 0 else None)
            user_input = page.query_selector("input[placeholder*='ユーザー']") or (inputs[1] if len(inputs) > 1 else None)
            pass_input = page.query_selector("input[type='password']") or (inputs[2] if len(inputs) > 2 else None)

            if school_input and user_input and pass_input:
                school_input.fill(school_id)
                user_input.fill(user_id)
                pass_input.fill(password)
                print("ログイン情報を入力完了。")

            login_btn = page.query_selector("button:has-text('ログイン')") or page.query_selector("input[type='submit']") or page.query_selector("button[type='submit']")
            if login_btn:
                login_btn.click()
                print("ログイン送信ボタンを押しました。")

            # 3. ダッシュボード表示待ち
            print("ダッシュボード読み込み待ち...")
            page.wait_for_selector(".left-pane, .subject-item, text=募集中", timeout=30000)
            print("★ ログイン成功！")

            # 4. 「募集中」教科の巡回・抽出
            recruiting_elements = page.query_selector_all("text=募集中")
            print(f"募集中の教科数: {len(recruiting_elements)}")

            for elem in recruiting_elements:
                parent_subject = elem.evaluate("node => node.closest('.subject-item, li, div')")
                subject_name = parent_subject.text_content().replace("募集中", "").strip() if parent_subject else "教科"

                elem.click()
                time.sleep(2)

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

        except Exception as err:
            print(f"\n--- [デバッグ情報] エラーが発生しました ---")
            print(f"エラー内容: {err}")
            print(f"エラー時のURL: {page.url}")
            body_text = page.inner_text("body")[:300] if page.query_selector("body") else "No body"
            print(f"画面上のテキスト抜粋:\n{body_text}")
            print("-------------------------------------------\n")
            raise err

        browser.close()

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
