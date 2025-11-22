"""
市场分析V2快速测试脚本
测试手动输入和解析功能（不需要OCR）
"""

import sys
sys.path.insert(0, 'c:/Users/Administrator/Desktop/新建文件夹/sss')

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
    window.setWindowTitle("市场分析 V2 - 阶段2测试（含OCR功能）")
    window.resize(1200, 800)
    window.show()
    
    # 自动填充测试数据
    lines = TEST_DATA.strip().split('\n')
    window.process_texts(lines)
    
    print("\n=== 测试说明 ===")
    print("1. 手动输入功能：点击'手动输入'按钮测试")
    print("2. OCR功能：点击'OCR识别'按钮（需要安装PaddleOCR）")
    print("3. 数据已自动加载，可以测试筛选、排序等功能")
    print("4. 所有数据自动保存到 market_data.db 数据库")
    
    sys.exit(app.exec())
