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
        # 日本時間設定（正常動作確認済み）
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            print("1. ロイロノートWeb版へアクセス中...")
            page.goto("https://loilonote.app/login", wait_until="networkidle")
            time.sleep(2)

            warning_overlay = page.query_selector("#continue")
            if warning_overlay and warning_overlay.is_visible():
                warning_overlay.click(force=True)
                time.sleep(1)

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

            recruiting_badges = page.get_by_text("募集中").all()
            print(f"検出された『募集中』教科の数: {len(recruiting_badges)}")

            for i in range(len(recruiting_badges)):
                try:
                    badges = page.get_by_text("募集中").all()
                    if i >= len(badges):
                        break
                    badge = badges[i]
                    
                    # 教科名の取得（正常動作確認済み）
                    subject_name = badge.evaluate("""(badge) => {
                        let curr = badge.parentElement;
                        while (curr && curr.tagName !== 'BODY') {
                            if (curr.classList.contains('roundListSectionGroup') || curr.classList.contains('courseListBody')) {
                                break; 
                            }
                            let texts = curr.querySelectorAll('.ellipsisText');
                            if (texts.length > 0) {
                                return texts[0].innerText.trim();
                            }
                            curr = curr.parentElement;
                        }
                        return '';
                    }""")

                    if not subject_name:
                        subject_name = f"教科{i+1}"

                    print(f"[{i+1}/{len(recruiting_badges)}] 教科『{subject_name}』を開いています...")
                    
                    # 【今回の唯一の変更点】バッジではなく、教科名テキストを安全に直接クリックする
                    row = badge.locator("xpath=ancestor::*[contains(@class, 'courseListRow') or self::li][1]")
                    text_target = row.locator(".ellipsisText").first
                    
                    if text_target.count() > 0:
                        text_target.click(force=True)
                    else:
                        badge.click(force=True)
                        
                    time.sleep(3)

                    tab = page.get_by_text("提出箱")
                    if tab.count() > 0 and tab.first.is_visible():
                        tab.first.click(force=True)
                        time.sleep(2)

                    # タスクの抽出（正常動作確認済み）
                    cards = page.locator(".focusScope .coursePanel").all()
                    if not cards:
                        cards = page.locator(".focusScope.coursePanel").all()
                    if not cards:
                        cards = page.locator(".coursePanel").filter(is_visible=True).all()

                    for card in cards:
                        title_el = card.locator(".ellipsisText").first
                        if title_el.count() == 0:
                            continue
                        title = title_el.text_content().strip()

                        deadline = ""
                        countdown_el = card.locator(".submissionCountDownText")
                        status_el = card.locator(".submissionStatusText")
                        
                        if countdown_el.count() > 0 and countdown_el.first.text_content().strip():
                            deadline = countdown_el.first.text_content().strip()
                        elif status_el.count() > 0 and status_el.first.text_content().strip():
                            deadline = status_el.first.text_content().strip()

                        if not deadline:
                            continue

                        card_text = card.text_content() or ""
                        if "提出済" in card_text or card.locator(".icon-check-green").count() > 0:
                            continue

                        if "のノート" in title or title.startswith("2026年") or "共有ノート" in title or "タイムライン" in title:
                            continue

                        item_id = f"{subject_name}_{title}"
                        if not any(x.get("id") == item_id for x in unsubmitted_items):
                            unsubmitted_items.append({
                                "id": item_id,
                                "subject": subject_name,
                                "title": title,
                                "deadline": deadline
                            })
                            print(f"  └ 【抽出】 [{subject_name}] {title} / 締切: {deadline}")

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
