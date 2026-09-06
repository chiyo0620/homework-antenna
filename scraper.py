import os
import json
import time
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

# API通信キャプチャ用のグローバル変数
CAPTURED_API_DATA = {}

def handle_response(response):
    """裏側で走るXHR/Fetch通信（JSON）をすべてフックして取得する"""
    try:
        if response.request.resource_type in ["xhr", "fetch"]:
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                url = response.url
                # 分析・トラッキング系の不要な通信を除外
                if "analytics" not in url and "log" not in url:
                    CAPTURED_API_DATA[url] = response.json()
    except Exception:
        pass

def run():
    school_id = os.environ.get("LOILO_SCHOOL_ID")
    user_id = os.environ.get("LOILO_USER_ID")
    password = os.environ.get("LOILO_PASSWORD")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        # レスポンス監視のフックを設定
        page.on("response", handle_response)

        try:
            print("【DEBUG】ログイン画面へアクセス中...")
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
                if btn.is_visible():
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

            print("【DEBUG】ログイン実行、メイン画面待機中...")
            page.wait_for_url("**/_/**", timeout=30000)
            time.sleep(5)

            # 各教科を巡回してAPI通信を強制的に発生させる
            page.mouse.wheel(0, 1500)
            time.sleep(2)

            recruiting_badges = page.get_by_text("募集中").all()
            print(f"【DEBUG】検知された「募集中」バッジの総数: {len(recruiting_badges)}")

            for i in range(len(recruiting_badges)):
                try:
                    badges = page.get_by_text("募集中").all()
                    if i >= len(badges):
                        break
                    badge = badges[i]
                    badge.scroll_into_view_if_needed()
                    
                    row = badge.locator("xpath=ancestor::*[contains(@class, 'courseListRow') or self::li][1]")
                    if row.count() > 0:
                        row.click(force=True)
                    else:
                        badge.click(force=True)

                    page.wait_for_selector(".focusScope.coursePanel", state="attached", timeout=10000)

                    tab = page.get_by_text("提出箱")
                    if tab.count() > 0 and tab.first.is_visible():
                        tab.first.click(force=True)
                        page.wait_for_load_state("networkidle")
                        time.sleep(2)

                except Exception as ex:
                    print(f"【ERROR】教科 {i} 巡回スキップ: {ex}")

        except Exception as err:
            print(f"【ERROR】致命的なエラー: {err}")
            raise err
        finally:
            browser.close()

    # キャプチャしたAPIレスポンスをルートに保存
    with open("api_debug.json", "w", encoding="utf-8") as f:
        json.dump(CAPTURED_API_DATA, f, ensure_ascii=False, indent=2)
    print("【DEBUG】api_debug.json をルートディレクトリに保存しました。")

    # 既存の data.json を壊さないための安全なタイムスタンプ更新
    try:
        with open("data.json", "r", encoding="utf-8") as f:
            old_data = json.load(f)
    except:
        old_data = {"count": 0, "items": []}
    
    jst = timezone(timedelta(hours=9), 'JST')
    old_data["updated_at"] = datetime.now(jst).isoformat()
    
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(old_data, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    run()
