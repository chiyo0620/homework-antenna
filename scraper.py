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
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
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

            page.wait_for_url("**/_/**", timeout=30000)
            time.sleep(5)

            recruiting_badges = page.get_by_text("募集中").all()

            for i in range(len(recruiting_badges)):
                try:
                    badges = page.get_by_text("募集中").all()
                    if i >= len(badges):
                        break
                    badge = badges[i]
                    
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
                    
                    # 確実に教科行をクリックして画面を切り替える
                    badge.evaluate("""(b) => {
                        let row = b.closest('.courseListRow') || b.closest('li');
                        if (row) row.click();
                        else b.click();
                    }""")
                    time.sleep(3)

                    # 【確実な修正1】現在画面に「見えている提出箱タブ」だけを厳格にクリックする
                    visible_tabs = page.locator("text=提出箱").filter(is_visible=True).all()
                    if visible_tabs:
                        visible_tabs[0].click(force=True)
                    time.sleep(2)

                    # 【確実な修正2】見えているタスクだけを抽出し、裏に隠れた別教科のタスクを除外
                    tasks_data = page.evaluate("""() => {
                        const results = [];
                        const seenTitles = new Set();
                        
                        const deadlines = document.querySelectorAll('.submissionCountDownText, .submissionStatusText');
                        deadlines.forEach(dl => {
                            // offsetParentがnull＝画面に表示されていない（裏に隠れている）ため無視
                            if (dl.offsetParent === null) return;
                            
                            const dlText = dl.innerText.trim();
                            if (!dlText) return;
                            
                            let curr = dl.parentElement;
                            let title = "";
                            
                            while (curr && curr.tagName !== 'BODY') {
                                const titleNodes = curr.querySelectorAll('.ellipsisText');
                                if (titleNodes.length > 0) {
                                    for(let node of titleNodes) {
                                        if (node !== dl && !node.classList.contains('submissionCountDownText') && !node.classList.contains('submissionStatusText')) {
                                            title = node.innerText.trim();
                                            break;
                                        }
                                    }
                                    if (title) break;
                                }
                                curr = curr.parentElement;
                            }
                            
                            if (!title) title = "宿題";
                            
                            let isSubmitted = false;
                            if (curr && (curr.innerText.includes('提出済') || curr.querySelector('.icon-check-green'))) {
                                isSubmitted = true;
                            }

                            if (!isSubmitted && !seenTitles.has(title)) {
                                seenTitles.add(title);
                                results.push({ title: title, deadline: dlText });
                            }
                        });
                        return results;
                    }""")

                    for t in tasks_data:
                        title = t['title']
                        deadline = t['deadline']
                        
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

                except Exception as ex:
                    pass

        except Exception as err:
            raise err

        browser.close()

    result = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(unsubmitted_items),
        "items": unsubmitted_items
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    run()
