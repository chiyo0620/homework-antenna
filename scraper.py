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
            
            # 【待機戦略】左側の教科リストの親要素がDOMにアタッチされるまで待機
            page.wait_for_selector(".courseListBody", state="attached", timeout=20000)
            time.sleep(3)
            print("✅ マイページが表示されました。データ抽出を開始します。")

            # 未読バッジ（赤丸数字）または「募集中」テキストを含む教科を取得
            course_locators = page.locator(".courseListItem:has(.courseListStatusV2:has-text('募集中')), .courseListItem:has(.redBadge)")
            course_count = course_locators.count()
            print(f"📌 更新のある教科を {course_count} 件検出しました。")

            for i in range(course_count):
                try:
                    # 仮想スクロール対策: ループごとにDOMを再評価し、参照切れ（Stale Element）を防止
                    course_locators = page.locator(".courseListItem:has(.courseListStatusV2:has-text('募集中')), .courseListItem:has(.redBadge)")
                    course = course_locators.nth(i)
                    
                    # 教科名の抽出
                    subject_el = course.locator(".roundListItemBody .ellipsisText").first
                    subject_name = subject_el.inner_text().strip() if subject_el.count() > 0 else f"教科{i+1}"
                    
                    print(f"➡️ [{i+1}/{course_count}] 教科「{subject_name}」を処理中...")
                    course.click(force=True)
                    
                    # 提出箱タブへの切り替えと描画待機
                    tab = page.locator('div[role="tab"]:has(.uiIcon_icon_sb)')
                    tab.wait_for(state="visible", timeout=10000)
                    tab.click(force=True)
                    time.sleep(2)
                    
                    # セクションごとにループ（「募集中」「〇月〇日 締切」などの各ブロック）
                    sections = page.locator('.roundListSection')
                    for j in range(sections.count()):
                        section = sections.nth(j)
                        
                        # セクションヘッダー（期限切れタスクのフォールバック用）
                        header_locator = section.locator('.roundListSectionHeader')
                        section_header = header_locator.inner_text().strip() if header_locator.count() > 0 else ""
                        
                        items = section.locator('.roundListItem')
                        for k in range(items.count()):
                            item = items.nth(k)
                            
                            # 【要件】data-status="notSubmitted" の有無で確実に未提出を判定
                            if item.locator('.submissionStatusBadge[data-status="notSubmitted"]').count() > 0:
                                
                                title_el = item.locator('.roundListItemBody .ellipsisText').first
                                title = title_el.inner_text().strip() if title_el.count() > 0 else ""
                                
                                # 期限の抽出（明記されていなければセクションのヘッダーテキストを期限として代用）
                                dl_el = item.locator('.submissionCountDownText')
                                deadline = dl_el.inner_text().strip() if dl_el.count() > 0 else section_header
                                
                                if not title:
                                    continue
                                    
                                # ノイズ除外
                                if "のノート" in title or "共有ノート" in title or "タイムライン" in title:
                                    continue
                                    
                                item_id = hashlib.md5(f"{subject_name}_{title}_{deadline}".encode()).hexdigest()
                                
                                unsubmitted_items.append({
                                    "id": item_id,
                                    "subject": subject_name,
                                    "title": title,
                                    "deadline": deadline
                                })
                                print(f"   📥 未提出タスク抽出: {title} (期限: {deadline})")
                                
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

    # JS側での日時パースを確実にするため、ISO 8601(UTC)のZ付きフォーマットに変更
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # IDをベースに重複排除
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
