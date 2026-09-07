import os
import time
from playwright.sync_api import sync_playwright

def run():
    # 1. 環境変数の読み込み
    school_id = os.environ.get("LOILO_SCHOOL_ID")
    user_id = os.environ.get("LOILO_USER_ID")
    password = os.environ.get("LOILO_PASSWORD")

    print("スクレイパーを起動します...")

    with sync_playwright() as p:
        # 2. JSTおよび日本語環境での Playwright ブラウザ起動
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="ja-JP",
            timezone_id="Asia/Tokyo",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            # 3. ロイロノートのログインページアクセス
            print("ログインページへアクセスしています...")
            page.goto("https://loilonote.app/login", wait_until="networkidle")
            time.sleep(2)

            # 警告オーバーレイ（以前のセッション等が残っている場合）があれば閉じる
            warning_overlay = page.query_selector("#continue")
            if warning_overlay and warning_overlay.is_visible():
                warning_overlay.click(force=True)
                time.sleep(1)

            # ログイン画面の遷移対応（「ロイロノートでログイン」ボタンがある場合）
            visible_inputs = page.query_selector_all("input:not([type='hidden'])")
            if len(visible_inputs) < 2:
                btn = page.get_by_text("ロイロノートでログイン", exact=True)
                if not btn.is_visible():
                    btn = page.get_by_text("Sign in with LoiLoNote", exact=True)
                if btn and btn.is_visible():
                    btn.click(force=True)
                    time.sleep(2)

            # フォーム入力要素の待機（タイムアウト20秒）
            page.wait_for_selector("input:not([type='hidden'])", timeout=20000)
            inputs = page.query_selector_all("input:not([type='hidden'])")

            # 入力フィールドの特定と入力処理
            school_input = page.query_selector("input[placeholder*='学校']") or (inputs[0] if len(inputs) > 0 else None)
            user_input = page.query_selector("input[placeholder*='ユーザー']") or (inputs[1] if len(inputs) > 1 else None)
            pass_input = page.query_selector("input[type='password']") or (inputs[2] if len(inputs) > 2 else None)

            if school_input and user_input and pass_input:
                if school_id and user_id and password:
                    school_input.fill(school_id)
                    user_input.fill(user_id)
                    pass_input.fill(password)
                else:
                    print("⚠️ 環境変数が一部設定されていません。GitHub Actions環境外の場合は確認してください。")
            else:
                raise Exception("ログインフォームの入力フィールドが正しく見つかりませんでした。")

            # ログイン送信
            submit_btn = (
                page.query_selector("button:has-text('ログイン')") or 
                page.query_selector("input[type='submit']") or 
                page.query_selector("button[type='submit']") or
                page.query_selector("button")
            )
            if submit_btn:
                submit_btn.click(force=True)
            else:
                raise Exception("ログインボタンが見つかりませんでした。")

            # 4. ログイン成功後のマイページ / 授業一覧画面への遷移待機
            print("ログイン情報を送信しました。マイページへの遷移を待機しています...")
            # URLが "_/" (ロイロノートのマイページ特有のパス) に変わるまで待機
            page.wait_for_url("**/_/**", timeout=30000)
            
            # ページが完全に描画され、動的コンポーネントが初期化されるまで少し待機
            time.sleep(5) 

            # ==========================================
            # 【クリーン化済】
            # 今後の開発では、ここから下に
            # ・左側教科リストの正確な要素取得
            # ・右側タスク一覧の動的待機と抽出
            # を追加していきます。
            # ==========================================

            # 5. 動作検証用の確認処理
            print("✅ ログインに成功しました")
            screenshot_path = "login_success.png"
            page.screenshot(path=screenshot_path)
            print(f"📸 ログイン後の画面状態をスクリーンショットとして保存しました: {screenshot_path}")

        except Exception as e:
            print(f"❌ エラーが発生しました: {e}")
            # エラー発生時にどこで止まったかを視覚的に確認するためのスクリーンショット
            try:
                page.screenshot(path="error_state.png")
                print("📸 エラー時の画面を error_state.png に保存しました。ログと併せて確認してください。")
            except:
                pass
            raise e
        finally:
            browser.close()

if __name__ == "__main__":
    run()
