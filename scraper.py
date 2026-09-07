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

            warning = page.query_selector("#continue")
            if warning and warning.is_visible():
                warning.click(force=True)
                time.sleep(1)

            if len(page.query_selector_all("input:not([type='hidden'])")) < 2:
                btn = page.get_by_text("ロイロノートでログイン", exact=True)
                if not btn.is_visible():
                    btn = page.get_by_text("Sign in with LoiLoNote", exact=True)
                if btn and btn.is_visible():
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
                page.query_selector("button")
            )
            if submit_btn:
                submit_btn.click(force=True)

            print("送信完了。マイページへの遷移を待機しています...")
            page.wait_for_url("**/_/**", timeout=30000)
            
            # 【待機戦略】左側の教科リストの親要素がDOMにアタッチされるまで待機
            page.wait_for_selector(".courseListBody", state="attached", timeout=20000)
            time.sleep(3)
            print("✅ マイページが表示されました。データ抽出を開始します。")

            # --- 課題1 & 2: 教科切替と全件網羅ロジック ---
            badges = page.get_by_text("募集中")
            badge_count = badges.count()
            print(f"📌 「募集中」のバッジを {badge_count} 件検出しました。")

            for i in range(badge_count):
                try:
                    # 仮想スクロール対策: ループごとにDOMを再評価し、参照切れ（Stale Element）を防止
                    current_badge = page.get_by_text("募集中").nth(i)
                    row = current_badge.locator("xpath=ancestor::*[contains(@class, 'courseListRow') or self::li][1]")
                    
                    # 教科名の抽出
                    subject_name = f"教科{i+1}"
                    subject_el = row.locator(".ellipsisText").first
                    if subject_el.count() > 0:
                        subject_name = subject_el.inner_text().strip()
                    
                    print(f"➡️ [{i+1}/{badge_count}] 教科「{subject_name}」を処理中...")
                    row.click(force=True)
                    
                    # 【待機戦略】右パネルのタブが切り替わるまで明示的に待機
                    page.wait_for_selector("text=提出箱", state="visible", timeout=10000)
                    
                    tab = page.get_by_text("提出箱")
                    if tab.count() > 0 and tab.first.is_visible():
                        tab.first.click(force=True)
                    
                    # SPAの非同期通信によるタスクカード描画を待機
                    time.sleep(2)
                    
                    # 【課題2解決】タスクパネル内の「すべて」のカード要素を取得
                    task_cards = page.locator(".focusScope.coursePanel")
                    task_count = task_cards.count()
                    seen_titles = set()
                    
                    for j in range(task_count):
                        card = task_cards.nth(j)
                        
                        # 【フィルタ要件】提出済み・緑チェックマークを除外
                        if card.locator("text='提出済'").count() > 0 or card.locator(".icon-check-green").count() > 0:
                            continue
                            
                        title_el = card.locator(".ellipsisText").first
                        title = title_el.inner_text().strip() if title_el.count() > 0 else ""
                        
                        dl_el = card.locator(".submissionCountDownText, .submissionStatusText").first
                        deadline = dl_el.inner_text().strip() if dl_el.count() > 0 else ""
                            
                        if not title or not deadline:
                            continue
                            
                        # 【フィルタ要件】指定のノイズ文字列を除外
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

    # index.html の `+ "Z"` 処理に合わせて UTC で現在時刻を生成
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
