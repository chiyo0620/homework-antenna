import os
import json
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# APIレスポンス横取り用のグローバル変数
CAPTURED_API_DATA = {}

def handle_response(response):
    """裏側で走るAPI通信（JSON）をフックして取得・保存する関数"""
    try:
        # XHR/FetchリクエストかつJSONを返すものをキャプチャ
        if response.request.resource_type in ["xhr", "fetch"]:
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                url = response.url
                # 解析に不要なトラッキング通信などは除外
                if "analytics" not in url and "log" not in url:
                    CAPTURED_API_DATA[url] = response.json()
    except Exception:
        pass

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
        
        # 【新機能】レスポンス監視の開始
        page.on("response", handle_response)

        try:
            # ネットワークがアイドル状態になるまで待機（固定秒数スリープ排除）
            page.goto("https://loilonote.app/login", wait_until="networkidle")

            # 警告オーバーレイの処理
            try:
                warning_overlay = page.wait_for_selector("#continue", state="visible", timeout=2000)
                if warning_overlay:
                    warning_overlay.click(force=True)
            except PlaywrightTimeoutError:
                pass

            # ログインフォームの表示待機
            page.wait_for_selector("input:not([type='hidden'])", state="visible", timeout=10000)
            inputs = page.query_selector_all("input:not([type='hidden'])")

            if len(inputs) < 2:
                try:
                    btn = page.locator("text='ロイロノートでログイン'").or_(page.locator("text='Sign in with LoiLoNote'")).first
                    btn.click(force=True)
                    page.wait_for_selector("input:not([type='hidden'])", state="visible", timeout=5000)
                    inputs = page.query_selector_all("input:not([type='hidden'])")
                except PlaywrightTimeoutError:
                    pass

            school_input = page.locator("input[placeholder*='学校']").first
            if school_input.count() == 0 and len(inputs) > 0: school_input = inputs[0]
            
            user_input = page.locator("input[placeholder*='ユーザー']").first
            if user_input.count() == 0 and len(inputs) > 1: user_input = inputs[1]
            
            pass_input = page.locator("input[type='password']").first
            if pass_input.count() == 0 and len(inputs) > 2: pass_input = inputs[2]

            school_input.fill(school_id)
            user_input.fill(user_id)
            pass_input.fill(password)

            # 【確実な待機】ログイン後の画面遷移完了を待機
            submit_btn = page.locator("button:has-text('ログイン'), input[type='submit'], button[type='submit']").first
            with page.expect_navigation(wait_until="networkidle", timeout=30000):
                submit_btn.click(force=True)

            page.wait_for_selector("text='募集中'", timeout=15000)
            recruiting_badges = page.locator("text='募集中'").all()

            for i in range(len(recruiting_badges)):
                try:
                    # ループごとに要素を再取得（DOM再描画による detached エラー対策）
                    badges = page.locator("text='募集中'").all()
                    if i >= len(badges): break
                    badge = badges[i]
                    
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
                    
                    # 【確実な待機】クリック後、右側のタスクパネルがDOMにマウントされるのを明示的に待機
                    if row.count() > 0:
                        row.first.click(force=True)
                    else:
                        badge.click(force=True)
                    
                    page.wait_for_selector(".focusScope.coursePanel", state="attached", timeout=5000)
                    
                    tab = page.locator("text='提出箱'").first
                    if tab.count() > 0:
                        tab.click(force=True)
                        # 【重要】提出箱タブ切り替えに伴う通信と再描画の完了を待機
                        page.wait_for_load_state("networkidle")
                    
                    # --- 現状はDOMからも安定取得（バックアップとして並行稼働） ---
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
                        
                        # ノイズフィルタ（設定要件を厳密に継承）
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
                    print(f"教科 {i} の処理中に軽微なエラー（スキップ継続）: {ex}")

        except Exception as err:
            raise err
        finally:
            browser.close()

    # 【Step 2に向けた布石】フックした内部APIデータを保存
    if CAPTURED_API_DATA:
        with open("debug_api_responses.json", "w", encoding="utf-8") as f:
            json.dump(CAPTURED_API_DATA, f, ensure_ascii=False, indent=2)
        print("✅ 内部API通信のキャプチャに成功しました。")

    # 【堅牢化】JST（日本時間）オフセットを含めた正確なISO 8601形式で出力
    jst = timezone(timedelta(hours=9), 'JST')
    now_jst = datetime.now(jst)
    
    result = {
        "updated_at": now_jst.isoformat(),  # 例: "2026-09-06T06:23:01+09:00"
        "count": len(unsubmitted_items),
        "items": unsubmitted_items
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    run()
