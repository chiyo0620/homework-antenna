import os
import json
import time
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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            print("【DEBUG】ログイン画面へアクセス中...")
            page.goto("https://loilonote.app/login", wait_until="networkidle")

            # 継続確認ダイアログの解除
            try:
                warning_overlay = page.wait_for_selector("#continue", state="visible", timeout=3000)
                if warning_overlay:
                    warning_overlay.click(force=True)
                    print("【DEBUG】継続ダイアログを解除しました")
            except Exception:
                pass

            # ログインフォームの表示制御
            try:
                page.wait_for_selector("input:not([type='hidden'])", state="visible", timeout=5000)
            except Exception:
                btn = page.get_by_text("ロイロノートでログイン", exact=True)
                if not btn.is_visible():
                    btn = page.get_by_text("Sign in with LoiLoNote", exact=True)
                if btn.is_visible():
                    btn.click(force=True)

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
                with page.expect_navigation(wait_until="networkidle", timeout=30000):
                    submit_btn.click(force=True)

            print("【DEBUG】ログイン成功。メイン画面の読込待ち...")
            page.wait_for_selector("text='募集中'", timeout=20000)

            # 【仮想スクロール対策】画面外の教科をDOMにマウントさせるため下へスクロール
            page.mouse.wheel(0, 1500)
            time.sleep(1)

            recruiting_badges = page.get_by_text("募集中").all()
            print(f"【DEBUG】検知された「募集中」バッジの総数: {len(recruiting_badges)}")

            for i in range(len(recruiting_badges)):
                try:
                    current_badges = page.get_by_text("募集中").all()
                    if i >= len(current_badges):
                        break
                    badge = current_badges[i]
                    badge.scroll_into_view_if_needed()
                    
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
                    }""") or f"教科{i+1}"
                    
                    row = badge.locator("xpath=ancestor::*[contains(@class, 'courseListRow') or self::li][1]")
                    if row.count() > 0:
                        row.first.click(force=True)
                    else:
                        badge.click(force=True)

                    # 右パネルのマウント完了待機
                    page.wait_for_selector(".focusScope.coursePanel", state="attached", timeout=10000)

                    tab = page.get_by_text("提出箱")
                    if tab.count() > 0 and tab.first.is_visible():
                        tab.first.click(force=True)
                        page.wait_for_load_state("networkidle")
                        
                        # 【確実な待機】タスク一覧の期限テキストが出現するまで明示的に待機
                        try:
                            page.wait_for_selector(".focusScope.coursePanel .submissionCountDownText, .focusScope.coursePanel .submissionStatusText", state="visible", timeout=8000)
                        except Exception:
                            print(f"【DEBUG】'{subject_name}' にタスク要素が読み込まれませんでした（空の提出箱の可能性あり）")

                    # デバッグ用スクリーンショット保存
                    print(f"【DEBUG】教科 '{subject_name}' のパネル情報を抽出中...")
                    page.screenshot(path=f"debug_subject_{i}.png")

                    tasks_data = page.evaluate("""() => {
                        const results = [];
                        const seenKeys = new Set();
                        
                        const deadlines = document.querySelectorAll('.submissionCountDownText, .submissionStatusText');
                        deadlines.forEach(dl => {
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

                            // 【判定ロジック修正】タイトル＋締切日時を組み合わせた一意キーで重複排除
                            const uniqueKey = title + "_" + dlText;

                            if (!isSubmitted && !seenKeys.has(uniqueKey)) {
                                seenKeys.add(uniqueKey);
                                results.push({ title: title, deadline: dlText });
                            }
                        });
                        return results;
                    }""")

                    print(f"【DEBUG】'{subject_name}' の抽出結果 ({len(tasks_data)}件): {tasks_data}")

                    for t in tasks_data:
                        title = t['title']
                        deadline = t['deadline']
                        
                        # ノイズ除外
                        if "のノート" in title or title.startswith("2026年") or "共有ノート" in title or "タイムライン" in title:
                            continue

                        item_id = f"{subject_name}_{title}_{deadline}"
                        if not any(x.get("id") == item_id for x in unsubmitted_items):
                            unsubmitted_items.append({
                                "id": item_id,
                                "subject": subject_name,
                                "title": title,
                                "deadline": deadline
                            })

                except Exception as ex:
                    print(f"【ERROR】教科 {i} の処理中に例外発生: {ex}")

        except Exception as err:
            print(f"【ERROR】致命的なエラー: {err}")
            raise err
        finally:
            browser.close()

    # ISO 8601 (JST) 形式の標準フォーマットで保存
    jst = timezone(timedelta(hours=9), 'JST')
    now_jst = datetime.now(jst)
    
    result = {
        "updated_at": now_jst.isoformat(),
        "count": len(unsubmitted_items),
        "items": unsubmitted_items
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"【DEBUG】処理完了。合計 {len(unsubmitted_items)} 件を data.json に書き出しました。")

if __name__ == "__main__":
    run()
