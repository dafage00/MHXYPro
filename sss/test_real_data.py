"""
测试真实世界频道数据
"""

import sys
sys.path.insert(0, 'c:/Users/Administrator/Desktop/新建文件夹/sss')

import novel_reader_qt as nr

# 创建解析器
class TestParser:
    def __init__(self):
        self.item_matcher = nr.SmartItemMatcher(nr.DEFAULT_ITEM_ALIASES)
        self.results = []
    
    def _record_price(self, match_info, trade_type, price, full_text, raw_name):
        self.results.append({
            "name": match_info.standard_name,
            "trade_type": trade_type,
            "price": price,
            "raw_name": raw_name,
            "full_text": full_text[:50] + "..." if len(full_text) > 50 else full_text,
        })
    
    _analyze_texts = nr.MarketAnalysisTab._analyze_texts

# 真实测试数据
REAL_DATA = [
    "(世界) [天才哥哥2号]#Y老花天价收宝石 #Y五色灵尘36.5 #30黑宝石16W #30星辉石16.5 #30 红玛瑙7W #30 舍利子8W #30月亮石5W #30太阳石6W #30光芒2W #30 翡翠1W #30 14W收仙露丸子 全场最高 22W收C66 650W收持国多闻 400谛听 1400W广目 350W收涂山瞳龙龟",
]

parser = TestParser()
parser._analyze_texts(REAL_DATA)

print("\n" + "="*80)
print("真实数据解析测试")
print("="*80)

print(f"\n共提取 {len(parser.results)} 条信息\n")

# 期望结果
expected = {
    "五色灵尘": 36.5,
    "黑宝石": 16.0,
    "星辉石": 16.5,
    "红玛瑙": 7.0,
    "舍利子": 8.0,
    "月亮石": 5.0,
    "太阳石": 6.0,
    "光芒石": 2.0,
    "翡翠石": 1.0,
    "仙露丸子": 14.0,
    "C66": 22.0,
    "持国天王": 650.0,
    "多闻天王": 650.0,
    "谛听": 400.0,
    "广目天王": 1400.0,
    "涂山瞳": 350.0,
    "龙龟": 350.0,
}

print("解析结果：")
print(f"{'序号':<4} {'物品名称':<15} {'价格(万)':<10} {'类型':<6} {'原文'}")
print("-" * 80)

for i, r in enumerate(parser.results, 1):
    print(f"{i:<4} {r['name']:<15} {r['price']:<10.1f} {r['trade_type']:<6} {r['full_text']}")

print("\n" + "="*80)
print("验证结果：")
print("="*80)

errors = []
missing = []

for item_name, expected_price in expected.items():
    found = [r for r in parser.results if r['name'] == item_name]
    if not found:
        missing.append(f"未找到: {item_name} (期望{expected_price}W)")
    else:
        actual_price = found[0]['price']
        if abs(actual_price - expected_price) < 0.01:
            print(f"[OK] {item_name:<15} {actual_price:>6.1f}W (期望{expected_price}W)")
        else:
            errors.append(f"[错误] {item_name}: 期望{expected_price}W，实际{actual_price}W")

if missing:
    print("\n缺失的物品：")
    for m in missing:
        print(f"  {m}")

if errors:
    print("\n价格错误：")
    for e in errors:
        print(f"  {e}")

if not errors and not missing:
    print("\n[完美] 所有物品和价格都识别正确！")
else:
    print(f"\n[总结] 成功:{len(expected)-len(errors)-len(missing)}/{len(expected)} 错误:{len(errors)} 缺失:{len(missing)}")
