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
            
            page.wait_for_selector(".courseNav .courseListItem", state="visible", timeout=25000)
            time.sleep(2)
            print("✅ マイページが表示されました。対象教科を特定します。")

            all_course_items = page.locator(".courseNav .courseListItem")
            target_subjects = []

            for idx in range(all_course_items.count()):
                c_item = all_course_items.nth(idx)
                has_recruiting = c_item.locator(".courseListStatusV2", has_text="募集中").count() > 0
                has_badge = c_item.locator(".redBadge").count() > 0

                if has_recruiting or has_badge:
                    name_el = c_item.locator(".roundListItemBody .ellipsisText").first
                    if name_el.count() > 0:
                        s_name = name_el.inner_text().strip()
                        if s_name and s_name not in target_subjects:
                            target_subjects.append(s_name)

            print(f"📌 対象教科 ({len(target_subjects)}件): {target_subjects}")

            for s_name in target_subjects:
                print(f"➡️ 教科「{s_name}」を処理中...")
                
                course_items = page.locator(".courseNav .courseListItem")
                for c_idx in range(course_items.count()):
                    item = course_items.nth(c_idx)
                    name_el = item.locator(".roundListItemBody .ellipsisText").first
                    if name_el.count() > 0 and name_el.inner_text().strip() == s_name:
                        # 確実に発火させるためInner要素をクリック
                        item.locator(".roundListItemInner").first.click(force=True)
                        break
                
                time.sleep(2)

                # 提出箱タブを正確なクラス名とテキストで指定
                tab = page.locator(".courseMenuTab", has_text="提出箱").first
                try:
                    tab.wait_for(state="visible", timeout=10000)
                    tab.click(force=True)
                except Exception as e:
                    print(f"   ⚠️ 提出箱タブのクリックに失敗しました: {e}")
                    continue

                try:
                    # 右パネルの中身が描画されるまで待機
                    page.wait_for_selector(".courseMenuBody .roundListSection", state="visible", timeout=10000)
                except Exception:
                    print("   ⚠️ 提出箱内にセクションが見つかりませんでした。スキップします。")
                    continue
                    
                time.sleep(2)

                sections = page.locator(".courseMenuBody .roundListSection")
                for j in range(sections.count()):
                    section = sections.nth(j)

                    header_el = section.locator(".roundListSectionHeader")
                    section_header = header_el.inner_text().strip() if header_el.count() > 0 else ""

                    unsubmitted_rows = section.locator('.roundListItem:has(.submissionStatusBadge[data-status="notSubmitted"])')
                    
                    for k in range(unsubmitted_rows.count()):
                        row = unsubmitted_rows.nth(k)
                        
                        title_el = row.locator(".roundListItemBody .ellipsisText").first
                        title = title_el.inner_text().strip() if title_el.count() > 0 else ""

                        if not title:
                            continue

                        if "のノート" in title or "共有ノート" in title or "タイムライン" in title:
                            continue

                        dl_el = row.locator(".submissionCountDownText")
                        deadline = dl_el.inner_text().strip() if dl_el.count() > 0 else section_header

                        item_id = hashlib.md5(f"{s_name}_{title}_{deadline}".encode()).hexdigest()

                        unsubmitted_items.append({
                            "id": item_id,
                            "subject": s_name,
                            "title": title,
                            "deadline": deadline
                        })
                        print(f"   📥 抽出: [{s_name}] {title} (期限: {deadline})")

        except Exception as e:
            print(f"❌ エラーが発生しました: {e}")
            try:
                page.screenshot(path="error_critical.png")
            except:
                pass
            raise e
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

    print(f"🎉 処理完了。未提出タスク {len(final_items)} 件を data.json に保存しました。")

if __name__ == "__main__":
    run()
