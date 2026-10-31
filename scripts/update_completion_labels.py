from pathlib import Path
p=Path('web/viewer.mjs');s=p.read_text(encoding='utf-8-sig');s=s.replace("实际检查模型 · 使用手动对齐结果","实际检查日期 · 使用手动对齐结果")
s=s.replace("$('timeMode').textContent='实际检查日期 · 使用手动对齐结果';","$('timeMode').textContent='实际检查日期 · 使用手动对齐结果'+(timeline[nearest].visualizationCompletion?' · 可视化内腔补全':'');")
s=s.replace("原始 Table.tsv 各日期值相同，不能反映趋势；插值帧不作为测量。","显示模型含可视化内腔补全；曲线保留原始网格测量值，补全与插值均不作为测量。")
s=s.replace("new URL('./morph-worker.mjs',import.meta.url)","new URL('./morph-worker.mjs?v=solid-1',import.meta.url)")
p.write_text(s,encoding='utf-8')
p=Path('web/morph-worker.mjs');s=p.read_text(encoding="utf-8");s=s.replace("fetch(new URL(item.url,data.baseURL))","fetch(new URL(item.url,data.baseURL),{cache:'no-cache'})");p.write_text(s,encoding="utf-8")
p=Path('index.html');s=p.read_text(encoding='utf-8-sig').replace('aligned-sdf-chart-safe-3','solid-completion-1');p.write_text(s,encoding='utf-8')
