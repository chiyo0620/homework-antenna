import os
import json
import time
import re
from datetime import datetime, timedelta
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

            # ログイン処理
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

            print("ダッシュボード読み込み待ち...")
            page.wait_for_url("**/_/**", timeout=30000)
            time.sleep(5)
            print("★ ログイン完了")

            # 左サイドバーの「募集中」教科を特定
            recruiting_badges = page.get_by_text("募集中").all()
            print(f"検出された『募集中』教科の数: {len(recruiting_badges)}")

            for i in range(len(recruiting_badges)):
                try:
                    badges = page.get_by_text("募集中").all()
                    if i >= len(badges):
                        break
                    badge = badges[i]
                    
                    # 教科名を正確に取得（通知の数字や「募集中」を取り除く）
                    subject_el = badge.locator("xpath=ancestor::*[contains(@class, 'subject') or contains(@class, 'item') or self::li][1]")
                    raw_text = subject_el.text_content() if subject_el.count() > 0 else ""
                    
                    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
                    subject_name = ""
                    for line in lines:
                        cleaned = re.sub(r'^\d+', '', line).replace("募集中", "").strip()
                        if cleaned and not cleaned.isdigit():
                            subject_name = cleaned
                            break
                    if not subject_name:
                        subject_name = f"教科{i+1}"

                    print(f"[{i+1}/{len(recruiting_badges)}] 教科『{subject_name}』を開いています...")
                    badge.click(force=True)
                    time.sleep(3)

                    # 提出箱タブをクリックして確実に表示
                    tab = page.get_by_text("提出箱")
                    if tab.count() > 0 and tab.first.is_visible():
                        tab.first.click(force=True)
                        time.sleep(2)

                    # 提出箱パネル内のアイテム（タイトルと締切）をピンポイント抽出
                    cards = page.locator("div, a, li").filter(has_text=re.compile(r'明日|今日|\d{1,2}月\d{1,2}日')).all()

                    for card in cards:
                        # 最小単位のカード要素のみを対象とする（余計な親要素を除外）
                        if card.locator("div, a, li").filter(has_text=re.compile(r'明日|今日|\d{1,2}月\d{1,2}日')).count() > 1:
                            continue

                        text = card.text_content().strip()
                        card_lines = [l.strip() for l in text.split('\n') if l.strip()]

                        if len(card_lines) >= 2:
                            title = card_lines[0]
                            deadline = card_lines[1]

                            # 雑多なノート履歴テキストを完全除外
                            if "のノート" in title or title.startswith("2026年") or "テスト直し2026" in title or "二学期2026" in title:
                                continue

                            item_id = f"{subject_name}_{title}"
                            if not any(x.get("id") == item_id for x in unsubmitted_items):
                                unsubmitted_items.append({
                                    "id": item_id,
                                    "subject": subject_name,
                                    "title": title,
                                    "deadline": deadline
                                })
                                print(f"  └ 【成果物】 [{subject_name}] {title} / 締切: {deadline}")

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
    print(f"★ 完了！ {len(unsubmitted_items)} 件の未提出宿題を抽出しました。")

if __name__ == "__main__":
    run()
