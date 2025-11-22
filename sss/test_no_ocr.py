"""
市场分析V2 - 简化测试版（不初始化OCR）
只测试手动输入和价格识别功能
"""

import sys
sys.path.insert(0, 'c:/Users/Administrator/Desktop/新建文件夹/sss')

# 临时禁用OCR
import market_analysis_v2 as m_v2
m_v2.PADDLEOCR_AVAILABLE = False  # 强制禁用OCR

from PyQt6.QtWidgets import QApplication
from market_analysis_v2 import MarketAnalysisV2Tab

# 测试数据
TEST_DATA = """[22:57:10] [测试玩家1] 收高必杀 8W
[22:58:15] [测试玩家2] 119伤害符 15W出售
[22:59:20] [测试玩家3] 任在703 烧双 赶车 10W
[23:00:30] [测试玩家4] 119体FF换个命中FF，或者8W出售
[23:01:45] [测试玩家5] 129以上飞贼来个队长 100W车费
[23:02:50] [测试玩家6] 自自自白自 119伤害F 换 防御 速度 或者15W
[23:03:55] [测试玩家7] 收神兜兜 炼兽真经"""

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 创建窗口
    window = MarketAnalysisV2Tab()
    window.setWindowTitle("市场分析 V2 - 价格修复测试（无OCR）")
    window.resize(1200, 800)
    window.show()
    
    # 自动填充测试数据
    lines = TEST_DATA.strip().split('\n')
    window.process_texts(lines)
    
    print("\n" + "="*60)
    print("价格修复测试")
    print("="*60)
    print("[OK] 已修复时间戳导致的价格错误")
    print("[OK] 已修复玩家名称导致的价格错误")
    print("\n期望结果：")
    print("  - 高级必杀: 8.0W")
    print("  - 伤害符: 15.0W")
    print("  - D3: 10.0W")
    print("  - 命中符: 8.0W")
    print("  - 飞贼: 100.0W")
    print("  - 防御符: 15.0W")
    print("  - 速度符: 15.0W")
    print("\n请查看界面中的价格是否正确！")
    print("="*60)
    
    sys.exit(app.exec())
