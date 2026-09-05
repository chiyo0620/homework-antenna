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
        # タイムゾーン指定で 13:00 → 22:00 のズレを確実に防止
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

            # --- ログイン処理 ---
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

            # 【先輩の修正1】座標ではなくHTML構造で左メニューだけを狙い撃つ
            # 左メニューのクラス（.courseListRow）のうち、「募集中」という文字を含んでいる行だけを取得
            target_rows = page.locator(".courseListRow").filter(has_text="募集中")
            
            # もし .courseListRow が無ければ、フォールバックとして li を使う
            if target_rows.count() == 0:
                target_rows = page.locator("li").filter(has_text="募集中")
                
            course_count = target_rows.count()
            print(f"検出された『募集中』教科の数: {course_count}")

            for i in range(course_count):
                try:
                    # 画面が切り替わっても安全なように毎回再取得 (nthを使用)
                    current_rows = page.locator(".courseListRow").filter(has_text="募集中")
                    if current_rows.count() == 0:
                        current_rows = page.locator("li").filter(has_text="募集中")
                        
                    if i >= current_rows.count():
                        break
                        
                    row = current_rows.nth(i)
                    
                    # 教科名の取得
                    subject_el = row.locator(".ellipsisText").first
                    subject_name = subject_el.text_content().strip() if subject_el.count() > 0 else f"教科{i+1}"
                    
                    print(f"[{i+1}/{course_count}] 教科『{subject_name}』を開いています...")
                    
                    # 確実にクリックして右画面を切り替える
                    row.scroll_into_view_if_needed()
                    row.click(force=True)
                    time.sleep(3)

                    # 提出箱タブをクリック（現在画面に見えているものだけ）
                    tab = page.locator("text=提出箱").filter(is_visible=True).first
                    if tab.count() > 0:
                        tab.click(force=True)
                        time.sleep(2)

                    # 【先輩の修正2】右画面のタスク（.coursePanel）だけを取得
                    cards = page.locator(".coursePanel").filter(is_visible=True)
                    card_count = cards.count()

                    for j in range(card_count):
                        card = cards.nth(j)
                        
                        title_el = card.locator(".ellipsisText").first
                        if title_el.count() == 0:
                            continue
                        title = title_el.text_content().strip()

                        # 締切日時の取得
                        deadline = ""
                        cd_el = card.locator(".submissionCountDownText").first
                        st_el = card.locator(".submissionStatusText").first
                        
                        if cd_el.count() > 0 and cd_el.is_visible():
                            deadline = cd_el.text_content().strip()
                        elif st_el.count() > 0 and st_el.is_visible():
                            deadline = st_el.text_content().strip()

                        if not deadline:
                            continue

                        # 提出済の除外
                        card_text = card.text_content() or ""
                        if "提出済" in card_text or card.locator(".icon-check-green").count() > 0:
                            continue

                        # ノイズ除外
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
                            print(f"  └ 【抽出成功】 [{subject_name}] {title} / 締切: {deadline}")

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
