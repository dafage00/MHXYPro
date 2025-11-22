"""
验证解析逻辑 - 确认价格是否正确
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
            "full_text": full_text,
        })
    
    _analyze_texts = nr.MarketAnalysisTab._analyze_texts

# 测试数据
TEST_LINES = [
    "[22:57:10] [测试玩家1] 收高必杀 8W",
    "[22:58:15] [测试玩家2] 119伤害符 15W出售",
    "[22:59:20] [测试玩家3] 任在703 烧双 赶车 10W",
    "[23:00:30] [测试玩家4] 119体FF换个命中FF，或者8W出售",
]

parser = TestParser()
parser._analyze_texts(TEST_LINES)

print("\n=== 解析结果 ===")
print(f"共提取 {len(parser.results)} 条信息\n")

for i, r in enumerate(parser.results, 1):
    print(f"{i}. {r['name']:<15} {r['price']:>6.1f}W  {r['trade_type']:<4}  原文: {r['full_text']}")

# 验证结果
expected = {
    "高级必杀": 8.0,
    "伤害符": 15.0,
    "D3": 10.0,
    "命中符": 8.0,
}

print("\n=== 验证 ===")
errors = []
for item_name, expected_price in expected.items():
    found = [r for r in parser.results if r['name'] == item_name]
    if not found:
        errors.append(f"❌ {item_name}: 未找到")
    elif len(found) > 1:
        prices = [r['price'] for r in found]
        errors.append(f"⚠️  {item_name}: 找到多个 {prices}")
    else:
        actual_price = found[0]['price']
        if abs(actual_price - expected_price) < 0.01:
            print(f"✅ {item_name}: {actual_price}W (正确)")
        else:
            errors.append(f"❌ {item_name}: 期望{expected_price}W，实际{actual_price}W")

if errors:
    print("\n发现问题：")
    for err in errors:
        print(err)
else:
    print("\n✅ 所有价格识别正确！")
