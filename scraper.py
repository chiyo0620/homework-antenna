import os
import json
import time
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

def run():
    school_id = os.environ.get("LOILO_SCHOOL_ID")
    user_id = os.environ.get("LOILO_USER_ID")
    password = os.environ.get("LOILO_PASSWORD")

    print("🚀 スクレイパーを起動します...")
    unsubmitted_items = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            print("🌐 ログインページへアクセスしています...")
            page.goto("https://loilonote.app/login", wait_until="networkidle")
            time.sleep(2)

            warning = page.locator("#continue").first
            if warning.count() > 0 and warning.is_visible():
                warning.click(force=True)
                time.sleep(1)

            # 英語（CI環境）と日本語の両方に対応する正規表現ボタンクリック
            login_btn = page.locator("text=/ロイロノートでログイン|Sign in with LoiLoNote/i").first
            if login_btn.count() > 0 and login_btn.is_visible():
                login_btn.click(force=True)
                time.sleep(2)

            # パスワード入力欄が表示されるまで待機（汎用的な input ではなく type 属性で一意に待機）
            page.locator("input[type='password']").wait_for(state="visible", timeout=20000)

            # LocatorAPIを使用した堅牢な入力欄の取得
            school_input = page.locator("input[placeholder*='学校'], input[name='client_id']").first
            if school_input.count() == 0:
                school_input = page.locator("input:not([type='hidden'])").nth(0)

            user_input = page.locator("input[placeholder*='ユーザー'], input[name='username']").first
            if user_input.count() == 0:
                user_input = page.locator("input:not([type='hidden'])").nth(1)

            pass_input = page.locator("input[type='password']").first

            school_input.fill(school_id)
            user_input.fill(user_id)
            pass_input.fill(password)
            
            submit_btn = page.locator("button:has-text('ログイン'), button:has-text('Sign in'), input[type='submit']").first
            if submit_btn.count() > 0:
                submit_btn.click(force=True)

            print("送信完了。マイページへの遷移を待機しています...")
            page.wait_for_url("**/_/**", timeout=30000)
            
            page.wait_for_selector(".courseListBody", state="attached", timeout=20000)
            time.sleep(3)
            print("✅ マイページが表示されました。データ抽出を開始します。")

            badges = page.get_by_text("募集中")
            badge_count = badges.count()
            print(f"📌 「募集中」のバッジを {badge_count} 件検出しました。")

            for i in range(badge_count):
                try:
                    current_badge = page.get_by_text("募集中").nth(i)
                    row = current_badge.locator("xpath=ancestor::*[contains(@class, 'courseListRow') or self::li][1]")
                    
                    subject_name = f"教科{i+1}"
                    subject_el = row.locator(".ellipsisText").first
                    if subject_el.count() > 0:
                        subject_name = subject_el.inner_text().strip()
                    
                    print(f"➡️ [{i+1}/{badge_count}] 教科「{subject_name}」を処理中...")
                    row.click(force=True)
                    
                    page.wait_for_selector("text=提出箱", state="visible", timeout=10000)
                    
                    tab = page.get_by_text("提出箱")
                    if tab.count() > 0 and tab.first.is_visible():
                        tab.first.click(force=True)
                    
                    time.sleep(2)
                    
                    task_cards = page.locator(".focusScope.coursePanel")
                    task_count = task_cards.count()
                    seen_titles = set()
                    
                    for j in range(task_count):
                        card = task_cards.nth(j)
                        
                        if card.locator("text='提出済'").count() > 0 or card.locator(".icon-check-green").count() > 0:
                            continue
                            
                        title_el = card.locator(".ellipsisText").first
                        title = title_el.inner_text().strip() if title_el.count() > 0 else ""
                        
                        dl_el = card.locator(".submissionCountDownText, .submissionStatusText").first
                        deadline = dl_el.inner_text().strip() if dl_el.count() > 0 else ""
                            
                        if not title or not deadline:
                            continue
                            
                        if "のノート" in title or title.startswith("2026年") or "共有ノート" in title or "タイムライン" in title:
                            continue
                            
                        if title not in seen_titles:
                            seen_titles.add(title)
                            item_id = f"{subject_name}_{title}"
                            
                            unsubmitted_items.append({
                                "id": item_id,
                                "subject": subject_name,
                                "title": title,
                                "deadline": deadline
                            })
                            print(f"   📥 タスク抽出: {title}")
                            
                except Exception as ex:
                    print(f"⚠️ 教科 {i+1} の処理中にエラー（スキップします）: {ex}")
                    continue

        except Exception as e:
            print(f"❌ 致命的なエラーが発生しました: {e}")
            try:
                page.screenshot(path="error_critical.png")
            except:
                pass
            raise e
        finally:
            browser.close()

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    
    result = {
        "updated_at": now_utc,
        "count": len(unsubmitted_items),
        "items": unsubmitted_items
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        
    print(f"🎉 処理完了。未提出タスク {len(unsubmitted_items)} 件を data.json に保存しました。")

if __name__ == "__main__":
    run()
