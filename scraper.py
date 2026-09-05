import os
import json
import time
import re
from playwright.sync_api import sync_playwright

def run():
    school_id = os.environ.get("LOILO_SCHOOL_ID")
    user_id = os.environ.get("LOILO_USER_ID")
    password = os.environ.get("LOILO_PASSWORD")

    unsubmitted_items = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # 日本時間(Asia/Tokyo)でブラウザを起動
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            print("[INFO] 1. ロイロノートWeb版へアクセス中...")
            page.goto("https://loilonote.app/login", wait_until="networkidle")

            # 警告オーバーレイ解除
            warning_overlay = page.query_selector("#continue")
            if warning_overlay and warning_overlay.is_visible():
                warning_overlay.click(force=True)
                page.wait_for_timeout(1000)

            # ログインフォーム入力
            visible_inputs = page.query_selector_all("input:not([type='hidden'])")
            if len(visible_inputs) < 2:
                btn = page.get_by_text("ロイロノートでログイン", exact=True)
                if not btn.is_visible():
                    btn = page.get_by_text("Sign in with LoiLoNote", exact=True)
                btn.click(force=True)
                page.wait_for_timeout(2000)

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

            print("[INFO] ダッシュボード読み込み待ち...")
            page.wait_for_url("**/_/**", timeout=30000)
            page.wait_for_load_state("networkidle")
            print("[SUCCESS] ★ ログイン完了")

            # 「募集中」バッジの要素を取得
            page.wait_for_selector("text=募集中", timeout=15000)
            recruiting_badges = page.get_by_text("募集中").all()
            print(f"[INFO] 検出された『募集中』教科の数: {len(recruiting_badges)}")

            for i in range(len(recruiting_badges)):
                try:
                    badges = page.get_by_text("募集中").all()
                    if i >= len(badges):
                        break
                    badge = badges[i]

                    # 対象の行要素を取得
                    row = badge.locator("xpath=ancestor::*[contains(@class, 'courseListRow') or self::li][1]")
                    
                    # 教科名テキストの取得
                    subject_el = row.locator(".ellipsisText").first
                    if subject_el.count() > 0:
                        subject_name = subject_el.text_content().strip()
                    else:
                        subject_name = f"教科{i+1}"

                    print(f"\n----------------------------------------")
                    print(f"[PROCESS] [{i+1}/{len(recruiting_badges)}] 教科『{subject_name}』の巡回を開始")

                    # スクロールして確実に表示させてから物理クリック
                    row.scroll_into_view_if_needed()
                    row.click(force=True)
                    page.wait_for_timeout(2000)

                    # 提出箱タブの表示とクリック（明示的待機）
                    submission_tab = page.locator("text=提出箱").filter(is_visible=True).first
                    if submission_tab.count() > 0:
                        submission_tab.click(force=True)
                        page.wait_for_timeout(2000)

                    # 宿題カードのDOM構造を精密解析（JavaScript直接評価）
                    cards_info = page.evaluate("""() => {
                        const items = [];
                        // アクティブ表示されているパネル内の全カードを取得
                        const panels = document.querySelectorAll('.focusScope .coursePanel, .coursePanel');
                        
                        panels.forEach(panel => {
                            // 非表示パネルは完全にスキップ
                            const style = window.getComputedStyle(panel);
                            if (style.display === 'none' || style.visibility === 'hidden') return;
                            if (panel.offsetParent === null && style.position !== 'fixed') return;

                            // タイトルの取得
                            const titleEl = panel.querySelector('.ellipsisText');
                            if (!titleEl) return;
                            const title = titleEl.innerText.strip ? titleEl.innerText.strip() : titleEl.innerText.trim();

                            // 締切の取得
                            const cdEl = panel.querySelector('.submissionCountDownText');
                            const stEl = panel.querySelector('.submissionStatusText');
                            let deadline = "";
                            if (cdEl && cdEl.innerText.trim()) deadline = cdEl.innerText.trim();
                            else if (stEl && stEl.innerText.trim()) deadline = stEl.innerText.trim();

                            // 提出済チェック
                            const isSubmitted = panel.innerText.includes('提出済') || panel.querySelector('.icon-check-green') !== null;

                            if (title && deadline && !isSubmitted) {
                                items.push({ title: title, deadline: deadline });
                            }
                        });
                        return items;
                    }""")

                    print(f"[INFO] 教科『{subject_name}』から検出された未提出カード数: {len(cards_info)}")

                    for card in cards_info:
                        title = card['title']
                        deadline = card['deadline']

                        # ノイズ（過去のノート等）を除外
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
                            print(f"  └ [FOUND] [{subject_name}] {title} | 締切: {deadline}")

                except Exception as ex:
                    print(f"  └ [ERROR] スキップ（例外発生）: {ex}")

        except Exception as err:
            print(f"[FATAL] エラーが発生しました: {err}")
            raise err

        browser.close()

    result = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(unsubmitted_items),
        "items": unsubmitted_items
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n========================================")
    print(f"[COMPLETE] 合計 {len(unsubmitted_items)} 件の宿題を出力完了")
    print(f"========================================")

if __name__ == "__main__":
    run()
