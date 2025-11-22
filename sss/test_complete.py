"""
市场分析V2 - 完整功能测试
按照推荐顺序测试并积累数据
"""

import sys
sys.path.insert(0, 'c:/Users/Administrator/Desktop/新建文件夹/sss')

# 禁用OCR以避免卡住
import market_analysis_v2 as m_v2
m_v2.PADDLEOCR_AVAILABLE = False

from PyQt6.QtWidgets import QApplication
from market_analysis_v2 import MarketAnalysisV2Tab

# 准备多组测试数据（用于积累数据库记录）
TEST_DATA_BATCH_1 = """[10:15:20] [玩家A] 收高必杀 8W
[10:16:30] [玩家B] 119伤害符 15W出售
[10:17:45] [玩家C] 任在703 烧双 赶车 10W
[10:18:50] [玩家D] 高连击 7W 高偷袭 6W"""

TEST_DATA_BATCH_2 = """[11:20:10] [玩家E] 收高神佑 30W
[11:21:25] [玩家F] 飞贼100W 抓鬼80W
[11:22:40] [玩家G] 119伤害符 14W 体质符 12W
[11:23:55] [玩家H] 神兜兜 炼兽真经 有的密"""

TEST_DATA_BATCH_3 = """[14:30:15] [玩家I] 高必杀 8.5W
[14:31:20] [玩家J] D3烧双 9W
[14:32:35] [玩家K] 119命中符 7W 防御符 8W
[14:33:45] [玩家L] 收高吸血 25W"""

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 创建窗口
    window = MarketAnalysisV2Tab()
    window.setWindowTitle("市场分析 V2 - 功能测试与数据积累")
    window.resize(1200, 800)
    window.show()
    
    print("\n" + "="*70)
    print("市场分析 V2 - 完整功能测试指南")
    print("="*70)
    
    print("\n【第1步：自动加载测试数据】")
    print("- 程序将自动加载第一批测试数据")
    print("- 查看表格中的价格是否正确")
    print("- 所有数据已自动保存到 market_data.db")
    
    # 自动加载第一批数据
    lines = TEST_DATA_BATCH_1.strip().split('\n')
    window.process_texts(lines)
    print("[OK] 已加载批次1")
    
    print("\n【第2步：手动输入更多数据】")
    print("方法1：点击'手动输入'按钮，粘贴下面的数据")
    print("方法2：在控制台等待，程序将自动加载")
    print("\n--- 批次2测试数据 ---")
    print(TEST_DATA_BATCH_2)
    print("\n--- 批次3测试数据 ---")
    print(TEST_DATA_BATCH_3)
    
    print("\n【第3步：测试功能】")
    print("1. 筛选功能：")
    print("   - 选择不同分类（宝宝/炼妖、临时符、收费带队等）")
    print("   - 选择交易类型（收购/出售）")
    print("   - 点击'刷新'更新显示")
    print("\n2. 排序功能：")
    print("   - 点击表头可按该列排序")
    print("   - 再次点击可反向排序")
    print("\n3. 统计显示：")
    print("   - 查看底部统计栏")
    print("   - 显示总条数、收购/出售分布")
    
    print("\n【第4步：验证数据库】")
    print("- 数据库文件：market_data.db")
    print("- 关闭并重新打开程序，数据仍然保存")
    print("- 可使用SQLite工具查看数据库内容")
    
    print("\n【第5步：积累更多数据】")
    print("- 点击'手动输入'，粘贴更多聊天记录")
    print("- 建议积累20-30条记录")
    print("- 这样趋势分析功能会更有意义")
    
    print("\n【测试完成后】")
    print("- 请告诉我测试结果")
    print("- 确认所有功能正常后")
    print("- 我将开始开发阶段5：趋势分析功能")
    
    print("\n" + "="*70)
    print("测试提示：")
    print("- OCR功能已禁用（避免卡住）")
    print("- 如需启用OCR，请用 python test_market_v2.py")
    print("- 重载代码功能可用于调试")
    print("="*70 + "\n")
    
    # 延迟加载更多数据（可选）
    def load_more_data():
        print("\n[自动] 3秒后将加载批次2...")
        import time
        time.sleep(3)
        lines2 = TEST_DATA_BATCH_2.strip().split('\n')
        window.process_texts(lines2)
        print("[OK] 已加载批次2")
        
        print("\n[自动] 再过3秒将加载批次3...")
        time.sleep(3)
        lines3 = TEST_DATA_BATCH_3.strip().split('\n')
        window.process_texts(lines3)
        print("[OK] 已加载批次3")
        
        print("\n[完成] 已加载全部3批测试数据")
        print(f"当前数据库中应该有约 {len(window.parsed_items)} 条记录")
        print("\n请测试筛选、排序等功能，然后告诉我结果！")
    
    # 使用定时器延迟加载（避免阻塞UI）
    from PyQt6.QtCore import QTimer
    QTimer.singleShot(3000, lambda: window.process_texts(TEST_DATA_BATCH_2.strip().split('\n')))
    QTimer.singleShot(6000, lambda: window.process_texts(TEST_DATA_BATCH_3.strip().split('\n')))
    
    sys.exit(app.exec())
