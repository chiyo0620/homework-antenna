import os
import json
import time
import re
from playwright.sync_api import sync_playwright

def extract_deadline_and_title(text):
    # 「今日 13:00」「明日 13:00」「9月9日(水) 13:00」などの日時パターンを検出
    pattern = r'(今日|明日|\d{1,2}月\d{1,2}日(?:\([月火水木金土日]\))?)\s*(\d{1,2}:\d{2})?'
    match = re.search(pattern, text)
    
    if match:
        deadline = match.group(0).strip()
        title = text.replace(deadline, "").strip()
        return title, deadline
    return text, ""

def run():
    school_id = os.environ.get("LOILO_SCHOOL_ID")
    user_id = os.environ.get("LOILO_USER_ID")
    password = os.environ.get("LOILO_PASSWORD")

    unsubmitted_items = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="ja-JP",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            print("1. ロイロノートWeb版へアクセス中...")
            page.goto("https://loilonote.app/login", wait_until="networkidle")
            time.sleep(2)

            # ブラウザ警告ポップアップ解除
            warning_overlay = page.query_selector("#continue")
            if warning_overlay and warning_overlay.is_visible():
                warning_overlay.click(force=True)
                time.sleep(1)

            # ログインフォーム入力
            visible_inputs = page.query_selector_all("input:not([type='hidden'])")
            if len(visible_inputs) < 2:
                btn = page.get_by_text("ロイロノートでログイン", exact=True)
                if not btn.is_visible():
                    btn = page.get_by_text("Sign in with LoiLoNote", exact=True)
                btn.click(force=True)
                time.sleep(2)

            page.wait_for_selector("input:not([type='hidden'])", timeout=20000)
            inputs = page.query_selector_all("input:not([type='hidden'])")

            school_input = page.query_selector("input[placeholder*='学校']") or (inputs[0] if len(inputs) > 0 else None)
            user_input = page.query_selector("input[placeholder*='ユーザー']") or (inputs[1] if len(inputs) > 1 else None)
            pass_input = page.query_selector("input[type='password']") or (inputs[2] if len(inputs) > 2 else None)

            if school_input and user_input and pass_input:
                school_input.fill(school_id)
                user_input.fill(user_id)
                pass_input.fill(password)

            submit_btn = (
                page.query_selector("button:has-text('ログイン')") or 
                page.query_selector("input[type='submit']") or 
                page.query_selector("button[type='submit']") or
                page.query_selector("button")
            )
            if submit_btn:
                submit_btn.click(force=True)

            # 2. ダッシュボード表示待ち
            print("ダッシュボード読み込み待ち...")
            page.wait_for_url("**/_/**", timeout=30000)
            time.sleep(5)
            print("★ ログイン完了")

            # 3. 「募集中」バッジのある教科を巡回
            recruiting_badges = page.get_by_text("募集中").all()
            print(f"検出された『募集中』教科の数: {len(recruiting_badges)}")

            for i in range(len(recruiting_badges)):
                try:
                    badges = page.get_by_text("募集中").all()
                    if i >= len(badges):
                        break
                    badge = badges[i]
                    
                    # 教科名を取得（「1募集中」などの先頭数字や「募集中」を除去）
                    parent_element = badge.locator("xpath=ancestor::*[contains(@class, 'item') or self::li or self::div][1]")
                    full_text = parent_element.text_content() if parent_element.count() > 0 else f"教科{i+1}"
                    
                    raw_name = full_text.replace("募集中", "").strip()
                    cleaned_name = re.sub(r'^\d+', '', raw_name).strip()
                    subject_name = cleaned_name if cleaned_name else f"教科{i+1}"
                    
                    print(f"[{i+1}/{len(recruiting_badges)}] 教科『{subject_name}』を開いています...")
                    badge.click(force=True)
                    time.sleep(3)

                    # 日時が含まれるタスク要素を検索
                    cards = page.locator("div, a, li").filter(has_text=re.compile(r'今日|明日|\d{1,2}月\d{1,2}日')).all()

                    for card in cards:
                        card_text = card.text_content().strip()
                        if len(card_text) > 150 or len(card_text) < 5:
                            continue

                        # 重複する親要素を回避
                        if card.locator("div, a, li").filter(has_text=re.compile(r'今日|明日|\d{1,2}月\d{1,2}日')).count() > 1:
                            continue

                        # タイトルと締切を分断・抽出
                        title, deadline = extract_deadline_and_title(card_text)

                        if not title and not deadline:
                            continue
                        if not title:
                            title = "宿題"

                        item_id = f"{subject_name}_{title}"
                        if not any(x.get("id") == item_id for x in unsubmitted_items):
                            unsubmitted_items.append({
                                "id": item_id,
                                "subject": subject_name,
                                "title": title,
                                "deadline": deadline
                            })
                            print(f"  └ 未提出タスク発見: [{subject_name}] {title} / 締切: {deadline}")

                except Exception as ex:
                    print(f"  └ スキップ: {ex}")

        except Exception as err:
            print(f"エラー発生: {err}")
            raise err

        browser.close()

    result = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(unsubmitted_items),
        "items": unsubmitted_items
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"★ 完了！ {len(unsubmitted_items)} 件の未提出宿題を取得・保存しました。")

if __name__ == "__main__":
    run()
