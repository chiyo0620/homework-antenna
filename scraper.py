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
                btn = page.get_by_text("ロイロノートでログイン", exact=True) or page.get_by_text("Sign in with LoiLoNote", exact=True)
                if btn and btn.is_visible():
                    btn.click(force=True)
                    time.sleep(2)

            page.wait_for_selector("input:not([type='hidden'])", timeout=20000)
            inputs = page.query_selector_all("input:not([type='hidden'])")
            if len(inputs) >= 3:
                inputs[0].fill(school_id)
                inputs[1].fill(user_id)
                inputs[2].fill(password)
            
            submit_btn = page.query_selector("button:has-text('ログイン')") or page.query_selector("input[type='submit']") or page.query_selector("button")
            if submit_btn:
                submit_btn.click(force=True)

            print("送信完了。マイページへの遷移を待機しています...")
            page.wait_for_url("**/_/**", timeout=30000)
            page.wait_for_selector(".courseListBody", state="attached", timeout=20000)
            time.sleep(3)
            print("✅ マイページが表示されました。データ抽出を開始します。")

            # すべての教科要素を取得（仮想DOM対策のため都度再取得する前提）
            courses_locator = page.locator(".courseListBody .courseListItem")
            course_count = courses_locator.count()
            print(f"📌 教科を {course_count} 件検出しました。抽出を開始します。")

            for i in range(course_count):
                try:
                    course = page.locator(".courseListBody .courseListItem").nth(i)
                    course.scroll_into_view_if_needed()
                    
                    subject_el = course.locator(".ellipsisText").first
                    subject_name = subject_el.inner_text().strip() if subject_el.count() > 0 else f"教科{i+1}"
                    
                    # 効率化: 赤バッジ（未読）または「募集中」ラベルがある教科のみ探索
                    has_badge = course.locator(".redBadge").count() > 0
                    has_recruiting = course.locator(".courseListStatusV2").count() > 0
                    
                    if not (has_badge or has_recruiting):
                        continue
                        
                    print(f"➡️ [{i+1}/{course_count}] 教科「{subject_name}」を処理中...")
                    course.click(force=True)
                    
                    # 右パネルの再描画と「提出箱」タブの出現を待機
                    submission_tab = page.locator('[id$="-submissionBox"]').first
                    submission_tab.wait_for(state="attached", timeout=10000)
                    submission_tab.click(force=True)
                    
                    # 提出箱の中身（セクション）が描画されるまで待機
                    try:
                        page.wait_for_selector('.courseMenuBody .roundListSection', state="attached", timeout=5000)
                    except:
                        print(f"   ℹ️ 提出箱が空、または読み込みタイムアウト（スキップ）")
                        continue
                        
                    # セクション（「募集中」「〇月〇日締切」などのブロック）ごとに処理
                    sections = page.locator('.courseMenuBody .roundListSection')
                    seen_titles = set()
                    
                    for j in range(sections.count()):
                        section = sections.nth(j)
                        header_el = section.locator('.roundListSectionHeader').first
                        header_text = header_el.inner_text().strip() if header_el.count() > 0 else ""
                        
                        items = section.locator('.roundListItem')
                        for k in range(items.count()):
                            item = items.nth(k)
                            
                            # 未提出バッジ（赤の！）があるか属性ベースで判定
                            if item.locator('[data-status="notSubmitted"]').count() > 0:
                                title_el = item.locator(".roundListItemBody .ellipsisText").first
                                title = title_el.inner_text().strip() if title_el.count() > 0 else ""
                                
                                # ノイズ除外
                                if not title or "のノート" in title or "共有ノート" in title or "タイムライン" in title:
                                    continue
                                
                                # 締切のパース: 募集中セクションは個別時刻を持ち、それ以外は見出しが締切日
                                if "募集中" in header_text:
                                    dl_el = item.locator(".submissionCountDownText").first
                                    deadline = dl_el.inner_text().strip() if dl_el.count() > 0 else "指定なし"
                                else:
                                    deadline = header_text.replace("締切", "").strip()
                                
                                if title not in seen_titles:
                                    seen_titles.add(title)
                                    unsubmitted_items.append({
                                        "id": f"{subject_name}_{title}",
                                        "subject": subject_name,
                                        "title": title,
                                        "deadline": deadline
                                    })
                                    print(f"   📥 未提出タスク抽出: {title} (締切: {deadline})")
                                    
                except Exception as ex:
                    print(f"⚠️ 教科 {i+1} の処理中にエラー（スキップします）: {ex}")
                    continue

        except Exception as e:
            print(f"❌ 致命的なエラーが発生しました: {e}")
            raise e
        finally:
            browser.close()

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
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
