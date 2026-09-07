import os
import json
import time
import hashlib
from datetime import datetime, timezone
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
            timezone_id="Asia/Tokyo",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            print("ログインページへアクセスしています...")
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
            if len(inputs) >= 3:
                inputs[0].fill(school_id)
                inputs[1].fill(user_id)
                inputs[2].fill(password)
            
            submit_btn = page.locator("button:has-text('ログイン'), input[type='submit'], button").first
            if submit_btn.count() > 0:
                submit_btn.click(force=True)

            print("マイページへの遷移を待機しています...")
            page.wait_for_url("**/_/**", timeout=30000)
            
            page.wait_for_selector(".courseNav .courseListItem", state="visible", timeout=25000)
            time.sleep(3)
            print("マイページが表示されました。")

            all_courses = page.locator(".courseNav .courseListItem")
            target_subjects = []

            for idx in range(all_courses.count()):
                c_item = all_courses.nth(idx)
                if c_item.locator(".courseListStatusV2", has_text="募集中").count() > 0 or c_item.locator(".redBadge").count() > 0:
                    name_el = c_item.locator(".roundListItemBody .ellipsisText").first
                    if name_el.count() > 0:
                        s_name = name_el.inner_text().strip()
                        if s_name and s_name not in target_subjects:
                            target_subjects.append(s_name)

            print(f"対象教科: {target_subjects}")

            for s_name in target_subjects:
                print(f"教科「{s_name}」を処理中...")
                
                course_el = page.locator(".courseNav .courseListItem").filter(has_text=s_name).first
                # PlaywrightのActionability Checkによるタイムアウトを回避するためJS経由で確実なクリックを実行
                course_el.evaluate("node => node.click()")
                time.sleep(2)

                tab = page.locator('div[role="tab"]').filter(has_text="提出箱").first
                try:
                    tab.wait_for(state="visible", timeout=10000)
                    tab.evaluate("node => node.click()")
                except Exception as e:
                    print(f"提出箱タブの遷移エラー: {e}")
                    continue

                time.sleep(2)

                sections = page.locator(".courseMenuBody .roundListSection")
                for j in range(sections.count()):
                    section = sections.nth(j)
                    header_el = section.locator(".roundListSectionHeader").first
                    section_header = header_el.inner_text().strip() if header_el.count() > 0 else ""

                    unsubmitted_rows = section.locator('.roundListItem:has(.submissionStatusBadge[data-status="notSubmitted"])')
                    
                    for k in range(unsubmitted_rows.count()):
                        row = unsubmitted_rows.nth(k)
                        title_el = row.locator(".roundListItemBody .ellipsisText").first
                        title = title_el.inner_text().strip() if title_el.count() > 0 else ""

                        if not title or "のノート" in title or "共有ノート" in title or "タイムライン" in title:
                            continue

                        dl_el = row.locator(".submissionCountDownText").first
                        deadline = dl_el.inner_text().strip() if dl_el.count() > 0 else section_header

                        item_id = hashlib.md5(f"{s_name}_{title}_{deadline}".encode()).hexdigest()
                        unsubmitted_items.append({
                            "id": item_id,
                            "subject": s_name,
                            "title": title,
                            "deadline": deadline
                        })
                        print(f"抽出: {title}")

        except Exception as e:
            print(f"エラーが発生しました: {e}")
        finally:
            browser.close()

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    unique_items = {item["id"]: item for item in unsubmitted_items}.values()
    final_items = list(unique_items)

    result = {
        "updated_at": now_utc,
        "count": len(final_items),
        "items": final_items
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    run()
