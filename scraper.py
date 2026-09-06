page.wait_for_url("**/_/**", timeout=30000)
            time.sleep(5)

            # 【追加】仮想スクロール対策：画面外の教科を読み込ませるために下へスクロール
            page.mouse.wheel(0, 1500)
            time.sleep(2)

            recruiting_badges = page.get_by_text("募集中").all()
            print(f"【DEBUG】見つかった「募集中」バッジの総数: {len(recruiting_badges)}") # ログ強化

            for i in range(len(recruiting_badges)):
                try:
                    badges = page.get_by_text("募集中").all()
                    if i >= len(badges):
                        break
                    badge = badges[i]
                    badge.scroll_into_view_if_needed() # 要素を画面内に入れる
                    
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
                    
                    row = badge.locator("xpath=ancestor::*[contains(@class, 'courseListRow') or self::li][1]")
                    if row.count() > 0:
                        row.click(force=True)
                    else:
                        badge.click(force=True)
                    time.sleep(3)

                    tab = page.get_by_text("提出箱")
                    if tab.count() > 0 and tab.first.is_visible():
                        tab.first.click(force=True)
                        time.sleep(2)

                    # 【追加】デバッグ出力の強化：クリック後の状態を保存
                    print(f"【DEBUG】教科 '{subject_name}' のパネルを開きました。抽出を開始します。")
                    page.screenshot(path=f"debug_subject_{i}.png")

                    tasks_data = page.evaluate("""() => {
                        const results = [];
                        const seenKeys = new Set(); // 【修正】タイトル単体での除外をやめる
                        
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

                            // 【修正】タイトル + 締切日時の組み合わせで一意キーを作る
                            const uniqueKey = title + "_" + dlText;

                            if (!isSubmitted && !seenKeys.has(uniqueKey)) {
                                seenKeys.add(uniqueKey);
                                results.push({ title: title, deadline: dlText });
                            }
                        });
                        return results;
                    }""")
                    
                    print(f"【DEBUG】'{subject_name}' で抽出されたタスク: {tasks_data}")
