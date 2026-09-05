import os
import json
from datetime import datetime, timezone, timedelta
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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            page.goto("https://loilonote.app/login", wait_until="networkidle")

            try:
                warning_overlay = page.wait_for_selector("#continue", state="visible", timeout=3000)
                if warning_overlay:
                    warning_overlay.click(force=True)
            except Exception:
                pass

            try:
                page.wait_for_selector("input:not([type='hidden'])", state="visible", timeout=5000)
            except Exception:
                try:
                    btn = page.locator("text='ロイロノートでログイン'").or_(page.locator("text='Sign in with LoiLoNote'")).first
                    if btn.count() > 0:
                        btn.click(force=True)
                except Exception:
                    pass

            page.wait_for_selector("input:not([type='hidden'])", state="visible", timeout=30000)
            inputs = page.query_selector_all("input:not([type='hidden'])")

            school_input = page.locator("input[placeholder*='学校']").first
            if school_input.count() == 0 and len(inputs) > 0: school_input = inputs[0]
            
            user_input = page.locator("input[placeholder*='ユーザー']").first
            if user_input.count() == 0 and len(inputs) > 1: user_input = inputs[1]
            
            pass_input = page.locator("input[type='password']").first
            if pass_input.count() == 0 and len(inputs) > 2: pass_input = inputs[2]

            school_input.fill(school_id)
            user_input.fill(user_id)
            pass_input.fill(password)

            submit_btn = page.locator("button:has-text('ログイン'), input[type='submit'], button[type='submit']").first
            with page.expect_navigation(wait_until="networkidle", timeout=30000):
                submit_btn.click(force=True)

            page.wait_for_selector("text='募集中'", timeout=20000)
            
            # 仮想スクロール対策: 隠れた要素を読み込ませるためリストをスクロール
            try:
                page.mouse.wheel(0, 500)
                page.wait_for_timeout(1000)
            except Exception:
                pass

            badges = page.locator("text='募集中'")
            badges_count = badges.count()

            for i in range(badges_count):
                try:
                    current_badges = page.locator("text='募集中'")
                    if i >= current_badges.count(): break
                    badge = current_badges.nth(i)
                    badge.scroll_into_view_if_needed()
                    
                    subject_name = badge.evaluate("""(node) => {
                        let curr = node.parentElement;
                        while (curr && curr.tagName !== 'BODY') {
                            if (curr.classList.contains('roundListSectionGroup') || curr.classList.contains('courseListBody')) break; 
                            let texts = curr.querySelectorAll('.ellipsisText');
                            if (texts.length > 0) return texts[0].innerText.trim();
                            curr = curr.parentElement;
                        }
                        return '';
                    }""") or f"教科{i+1}"
                    
                    row = badge.locator("xpath=ancestor::*[contains(@class, 'courseListRow') or self::li][1]")
                    if row.count() > 0:
                        row.first.click(force=True)
                    else:
                        badge.click(force=True)
                    
                    page.wait_for_selector(".focusScope.coursePanel", state="attached", timeout=10000)
                    
                    tab = page.locator("text='提出箱'").first
                    if tab.count() > 0:
                        tab.click(force=True)
                        
                        # 【重要】提出箱のタスク一覧がサーバーから読み込まれるのを最大8秒待機する
                        try:
                            page.wait_for_selector(".focusScope.coursePanel .submissionCountDownText, .focusScope.coursePanel .submissionStatusText", state="visible", timeout=8000)
                        except Exception:
                            pass
                    
                    tasks_data = page.evaluate("""() => {
                        const results = [];
                        const seen = new Set();
                        const deadlines = document.querySelectorAll('.submissionCountDownText, .submissionStatusText');
                        
                        deadlines.forEach(dl => {
                            const dlText = dl.innerText.trim();
                            if (!dlText) return;
                            
                            let curr = dl.parentElement;
                            let title = "宿題";
                            while (curr && curr.tagName !== 'BODY') {
                                const titleNodes = curr.querySelectorAll('.ellipsisText');
                                if (titleNodes.length > 0) {
                                    for(let node of titleNodes) {
                                        if (node !== dl && !node.classList.contains('submissionCountDownText') && !node.classList.contains('submissionStatusText')) {
                                            title = node.innerText.trim();
                                            break;
                                        }
                                    }
                                    if (title !== "宿題") break;
                                }
                                curr = curr.parentElement;
                            }
                            
                            let isSubmitted = curr && (curr.innerText.includes('提出済') || curr.querySelector('.icon-check-green'));
                            if (!isSubmitted && !seen.has(title)) {
                                seen.add(title);
                                results.push({ title, deadline: dlText });
                            }
                        });
                        return results;
                    }""")

                    for t in tasks_data:
                        title = t['title']
                        deadline = t['deadline']
                        
                        if any(noise in title for noise in ["のノート", "共有ノート", "タイムライン"]) or title.startswith("2026年"):
                            continue
                            
                        item_id = f"{subject_name}_{title}"
                        if not any(x["id"] == item_id for x in unsubmitted_items):
                            unsubmitted_items.append({
                                "id": item_id,
                                "subject": subject_name,
                                "title": title,
                                "deadline": deadline
                            })

                except Exception as ex:
                    print(f"教科 {i} 処理スキップ: {ex}")

        except Exception as err:
            raise err
        finally:
            browser.close()

    # ISO 8601 (JST) 形式での出力へ統一
    jst = timezone(timedelta(hours=9), 'JST')
    now_jst = datetime.now(jst)
    
    result = {
        "updated_at": now_jst.isoformat(),
        "count": len(unsubmitted_items),
        "items": unsubmitted_items
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    run()
