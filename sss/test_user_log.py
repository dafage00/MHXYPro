
import sys
import os
from novel_reader_qt import MarketAnalysisTab, SmartItemMatcher, DEFAULT_ITEM_ALIASES

# Mock for testing
class MockMarketTab(MarketAnalysisTab):
    def __init__(self):
        # Initialize only what's needed for _analyze_texts
        self.alias_config = DEFAULT_ITEM_ALIASES
        self.item_matcher = SmartItemMatcher(self.alias_config)
        self.market_data = {}
        self.item_repository = {}
        self.raw_messages = []
        
    def _update_ui(self):
        pass

def test_specific_log():
    tab = MockMarketTab()
    
    text = "[й杂货я ] 质量兽决73 万吸收小法68 万 金刚9 9定魂9 9夜光8 0碧水08龙鳞49 强化8.5 吸血6 0必杀7 0夜战7 0偷袭7 0 迅敏8 0连环6 0矫健6 0狂怒20撞击15静月4 0灵光1 0灵身1 0 大雨45 小雨05树苗34 超6624彩果23 月华5 人在天台 高收一切。"
    
    print(f"Testing text: {text}")
    print(f"'月华' in matcher: {'月华' in tab.item_matcher.alias_to_canonical}")
    tab._analyze_texts([text])
    
    # Check results
    expected = {
        "金刚石": 99.0,
        "定魂珠": 99.0,
        "夜光珠": 80.0,
        "避水珠": 8.0,
        "龙鳞": 49.0,
        "强化石": 8.5,
        "吸血": 60.0,
        "必杀": 70.0,
        "夜战": 70.0,
        "偷袭": 70.0,
        "迅敏": 80.0,
        "连环": 60.0,
        "矫健": 60.0,
        "狂怒": 20.0,
        "撞击": 15.0,
        "静岳": 40.0,
        "灵光": 10.0,
        "灵身": 10.0,
        "水漫金山": 45.0,
        "水攻": 5.0,
        "树苗": 34.0,
        "超级金柳露": 24.0,
        "彩果": 23.0,
        "月华露": 5.0
    }
    
    print("\nResults:")
    found_items = set()
    for item_name, data in tab.market_data.items():
        if not data['buy']:
            continue
        price = data['buy'][0] if isinstance(data['buy'][0], float) else data['buy'][0]['price']
        found_items.add(item_name)
        
        if item_name in expected:
            exp_price = expected[item_name]
            if price == exp_price:
                print(f"[OK] {item_name}: {price}")
            else:
                print(f"[FAIL] {item_name}: Expected {exp_price}, got {price}")
        else:
            print(f"[EXTRA] {item_name}: {price}")
            
    print("\nMissing items:")
    for item in expected:
        if item not in found_items:
            print(f"[MISSING] {item}")

if __name__ == "__main__":
    test_specific_log()
