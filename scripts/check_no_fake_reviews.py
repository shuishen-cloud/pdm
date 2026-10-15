"""证明：无 feat 残留批量刷的审查记录（reviewed_at 秒级聚集）。

若存在跨 feat 的"同一秒内 >=4 条审查"，视为批量伪造痕迹，退出 1。
"""
import glob, json, sys
from datetime import datetime
from collections import Counter

buckets = Counter()
for p in glob.glob('.pdm/feats/by-id/*.json'):
    d = json.load(open(p, encoding='utf-8'))
    times = [v.get('reviewed_at') for v in d.get('reviews', {}).values()
             if v.get('reviewed_at')]
    times += [v.get('at') for v in d.get('stage_reviews', {}).values()
              if v.get('at')]
    for t in times:
        try:
            buckets[datetime.fromisoformat(t).replace(microsecond=0)] += 1
        except Exception:
            pass
bad = {k: v for k, v in buckets.items() if v >= 4}
if bad:
    print('发现疑似批量审查：', bad)
    sys.exit(1)
print('OK：无批量审查痕迹')
