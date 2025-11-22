"""
市场分析 V2 - 简洁清晰的市场分析界面
基于 market_parser_tester.py 的成功设计
完全复用 novel_reader_qt.py 的解析逻辑
"""

import sys
import sqlite3
import time
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QTableWidget, 
    QTableWidgetItem, QPushButton, QLabel, QSplitter, QComboBox,
    QDialog, QDialogButtonBox, QHeaderView, QMessageBox, QTabWidget,
    QSpinBox
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QColor

# Import core logic from main application
import novel_reader_qt as nr

# Check for OCR availability
try:
    from paddleocr import PaddleOCR
    from PIL import Image
    import numpy as np
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False
    print("PaddleOCR not available. OCR features will be disabled.")

# Check for matplotlib availability
try:
    import matplotlib
    matplotlib.use('Qt5Agg')  # 使用Qt5后端
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Matplotlib not available. Chart features will be disabled.")


class OCRWorker(QThread):
    """OCR识别工作线程"""
    finished_signal = pyqtSignal(list)
    error_signal = pyqtSignal(str)
    
    def __init__(self, ocr_engine, img_array):
        super().__init__()
        self.ocr_engine = ocr_engine
        self.img_array = img_array
        self.start_time = time.time()
    
    def run(self):
        try:
            result = self.ocr_engine.ocr(self.img_array, cls=False)
            if result and result[0]:
                texts = [line[1][0] for line in result[0]]
                self.finished_signal.emit(texts)
            else:
                self.finished_signal.emit([])
        except Exception as e:
            self.error_signal.emit(str(e))


class ManualInputDialog(QDialog):
    """手动输入对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("手动输入聊天记录")
        self.resize(600, 400)
        
        layout = QVBoxLayout(self)
        
        # 说明文字
        label = QLabel("请粘贴聊天记录（每行一条）：")
        layout.addWidget(label)
        
        # 输入框
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText(
            "示例：\n"
            "[22:57:10] [玩家名] 收高必杀 8W\n"
            "[22:58:15] [玩家名] 119伤害符 15W出售\n"
            "..."
        )
        layout.addWidget(self.text_edit)
        
        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.resize(600, 400)
    
    def get_text(self) -> str:
        return self.text_edit.toPlainText()


class MarketDatabase:
    """市场数据库管理类"""
    
    def __init__(self, db_path="market_data.db"):
        self.db_path = db_path
        self.conn = None
        self._init_database()
    
    def _init_database(self):
        """初始化数据库"""
        self.conn = sqlite3.connect(self.db_path)
        cursor = self.conn.cursor()
        
        # 创建表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT NOT NULL,
                standard_name TEXT NOT NULL,
                price REAL NOT NULL,
                trade_type TEXT NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT,
                raw_name TEXT,
                full_text TEXT,
                timestamp DATETIME NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 创建索引
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_item_timestamp 
            ON market_records(standard_name, timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON market_records(timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_category 
            ON market_records(category)
        """)
        
        self.conn.commit()
    
    def insert_record(self, item_dict: dict):
        """插入记录"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO market_records 
            (item_name, standard_name, price, trade_type, category, subcategory, 
             raw_name, full_text, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item_dict.get('name'),
            item_dict.get('name'),
            item_dict.get('price'),
            item_dict.get('trade_type'),
            item_dict.get('category', '').split('-')[0] if '-' in item_dict.get('category', '') else item_dict.get('category', ''),
            item_dict.get('category', '').split('-')[1] if '-' in item_dict.get('category', '') else '',
            item_dict.get('raw_name'),
            item_dict.get('full_text'),
            item_dict.get('timestamp', datetime.now())
        ))
        self.conn.commit()
    
    def query_by_item(self, item_name: str, days: int = 7) -> List[tuple]:
        """查询物品历史"""
        cursor = self.conn.cursor()
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        cursor.execute("""
            SELECT timestamp, price, trade_type, full_text
            FROM market_records
            WHERE standard_name = ? AND timestamp BETWEEN ? AND ?
            ORDER BY timestamp ASC
        """, (item_name, start_date, end_date))
        
        return cursor.fetchall()
    
    def get_item_statistics(self, item_name: str, days: int = 7) -> dict:
        """获取物品统计信息"""
        records = self.query_by_item(item_name, days)
        if not records:
            return {}
        
        prices = [r[1] for r in records]
        return {
            'count': len(prices),
            'min_price': min(prices),
            'max_price': max(prices),
            'avg_price': sum(prices) / len(prices),
            'latest_price': prices[-1] if prices else 0
        }
    
    def get_all_items_stats(self, days: int = 7) -> List[dict]:
        """获取所有物品的统计信息"""
        cursor = self.conn.cursor()
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        cursor.execute("""
            SELECT standard_name, COUNT(*) as count,
                   MIN(price) as min_price, MAX(price) as max_price,
                   AVG(price) as avg_price
            FROM market_records
            WHERE timestamp BETWEEN ? AND ? AND price > 0
            GROUP BY standard_name
            ORDER BY count DESC
        """, (start_date, end_date))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'name': row[0],
                'count': row[1],
                'min_price': row[2],
                'max_price': row[3],
                'avg_price': row[4]
            })
        
        return results
    
    def cleanup_old_records(self, months=3):
        """清理旧数据"""
        cursor = self.conn.cursor()
        cutoff_date = datetime.now() - timedelta(days=months * 30)
        
        cursor.execute("""
            DELETE FROM market_records
            WHERE timestamp < ?
        """, (cutoff_date,))
        
        self.conn.commit()
        return cursor.rowcount
    
    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()


class TestParser:
    """
    解析器包装类，复用主程序的解析逻辑
    参考 market_parser_tester.py 的设计
    """
    
    def __init__(self):
        self.item_matcher = nr.SmartItemMatcher(nr.DEFAULT_ITEM_ALIASES)
        self.results = []
    
    def _record_price(self, match_info, trade_type, price, full_text, raw_name):
        """记录价格（覆盖主程序的UI更新方法）"""
        self.results.append({
            "name": match_info.standard_name,
            "trade_type": trade_type,
            "price": price,
            "raw_name": raw_name,
            "full_text": full_text,
            "category": f"{match_info.category}-{match_info.subcategory}",
            "timestamp": datetime.now()
        })
    
    # 复用主程序的解析方法
    _analyze_texts = nr.MarketAnalysisTab._analyze_texts


class MarketAnalysisV2Tab(QWidget):
    """市场分析 V2 - 主界面"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 数据存储
        self.raw_logs: List[str] = []  # 原始聊天记录
        self.parsed_items: List[dict] = []  # 解析后的物品
        self.db = MarketDatabase()  # 数据库
        
        # 筛选条件
        self.filter_category = "全部"
        self.filter_trade_type = "全部"
        
        # OCR 相关
        self.ocr_engine = None
        self.is_capturing = False
        self.is_processing = False
        self.ocr_worker = None
        self.capture_timer = QTimer(self)
        self.capture_timer.timeout.connect(self._capture_and_analyze)
        
        # 初始化OCR
        self._init_ocr()
        
        self._build_ui()
    
    def _init_ocr(self):
        """初始化OCR引擎"""
        if not PADDLEOCR_AVAILABLE:
            print("[V2] PaddleOCR未安装，OCR功能将被禁用")
            return
        
        try:
            print("[V2] 正在初始化PaddleOCR...")
            self.ocr_engine = PaddleOCR(
                use_angle_cls=False,
                lang='ch',
                det_db_box_thresh=0.5,
                rec_batch_num=6
            )
            print("[V2] OCR引擎初始化成功")
        except Exception as e:
            print(f"[V2] OCR初始化失败: {e}")
            self.ocr_engine = None
    
    def _build_ui(self):
        """构建界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # === 工具栏 ===
        toolbar_layout = QHBoxLayout()
        
        # OCR识别按钮
        self.btn_ocr = QPushButton("OCR识别")
        self.btn_ocr.setCheckable(True)
        self.btn_ocr.clicked.connect(self.toggle_ocr)
        if not self.ocr_engine:
            self.btn_ocr.setEnabled(False)
            self.btn_ocr.setToolTip("OCR引擎未安装")
        toolbar_layout.addWidget(self.btn_ocr)
        
        # 识别间隔
        toolbar_layout.addWidget(QLabel("间隔(秒):"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 60)
        self.interval_spin.setValue(3)
        toolbar_layout.addWidget(self.interval_spin)
        
        # 手动输入按钮
        self.btn_manual_input = QPushButton("手动输入")
        self.btn_manual_input.clicked.connect(self.show_manual_input)
        toolbar_layout.addWidget(self.btn_manual_input)
        
        # 清空数据按钮
        self.btn_clear = QPushButton("清空数据")
        self.btn_clear.clicked.connect(self.clear_data)
        toolbar_layout.addWidget(self.btn_clear)
        
        # 重载代码按钮（调试功能）
        self.btn_reload = QPushButton("重载代码")
        self.btn_reload.clicked.connect(self.reload_code)
        toolbar_layout.addWidget(self.btn_reload)
        
        toolbar_layout.addStretch()
        
        # 状态标签
        self.status_label = QLabel("就绪")
        toolbar_layout.addWidget(self.status_label)
        
        layout.addLayout(toolbar_layout)
        
        # === 主分割器（上下分割）===
        main_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # === 上半部分：数据采集区域 ===
        collection_widget = QWidget()
        collection_layout = QVBoxLayout(collection_widget)
        collection_layout.setContentsMargins(0, 0, 0, 0)
        
        # 标题
        collection_label = QLabel("识别到的聊天记录 (最近100条):")
        collection_layout.addWidget(collection_label)
        
        # 文本显示区域
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setPlaceholderText(
            "点击\"手动输入\"粘贴聊天记录进行测试...\n"
            "或等待OCR自动识别功能（待实现）"
        )
        collection_layout.addWidget(self.log_display)
        
        # 统计栏
        self.stats_label = QLabel("识别条数: 0 | 提取物品: 0")
        collection_layout.addWidget(self.stats_label)
        
        main_splitter.addWidget(collection_widget)
        
        # === 下半部分：数据展示区域 ===
        display_widget = QWidget()
        display_layout = QVBoxLayout(display_widget)
        display_layout.setContentsMargins(0, 0, 0, 0)
        
        # 筛选栏
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("分类:"))
        
        self.category_filter = QComboBox()
        self.category_filter.addItems([
            "全部", "宝宝/炼妖", "临时符", "收费带队", 
            "军火/装备", "硬通货", "消耗品", "杂货"
        ])
        self.category_filter.currentTextChanged.connect(self.apply_filter)
        filter_layout.addWidget(self.category_filter)
        
        filter_layout.addWidget(QLabel("类型:"))
        
        self.type_filter = QComboBox()
        self.type_filter.addItems(["全部", "收购", "出售"])
        self.type_filter.currentTextChanged.connect(self.apply_filter)
        filter_layout.addWidget(self.type_filter)
        
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.clicked.connect(self.update_table)
        filter_layout.addWidget(self.btn_refresh)
        
        filter_layout.addStretch()
        
        display_layout.addLayout(filter_layout)
        
        # 结果表格
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(6)
        self.result_table.setHorizontalHeaderLabels([
            "物品名称", "价格(万)", "交易类型", "分类", "时间", "原始文本"
        ])
        
        # 设置列宽
        header = self.result_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        
        self.result_table.setColumnWidth(0, 120)
        self.result_table.setColumnWidth(1, 80)
        self.result_table.setColumnWidth(2, 80)
        self.result_table.setColumnWidth(3, 120)
        self.result_table.setColumnWidth(4, 100)
        
        # 启用排序
        self.result_table.setSortingEnabled(True)
        
        display_layout.addWidget(self.result_table)
        
        # 统计栏
        self.display_stats_label = QLabel("共提取 0 条信息 | 收购 0 条 | 出售 0 条")
        display_layout.addWidget(self.display_stats_label)
        
        main_splitter.addWidget(display_widget)
        
        # 设置分割器初始大小比例 (40% : 60%)
        main_splitter.setSizes([300, 600])
        
        layout.addWidget(main_splitter)
    
    def toggle_ocr(self):
        """切换OCR识别状态"""
        if not self.ocr_engine:
            QMessageBox.warning(self, "OCR未安装", "请先安装PaddleOCR")
            self.btn_ocr.setChecked(False)
            return
        
        if self.btn_ocr.isChecked():
            # 开始识别
            self.is_capturing = True
            self.btn_ocr.setText("停止识别")
            self.status_label.setText("OCR识别中...")
            
            # 启动定时器
            interval = self.interval_spin.value() * 1000
            self.capture_timer.start(interval)
            
            # 立即执行一次
            self._capture_and_analyze()
        else:
            # 停止识别
            self.is_capturing = False
            self.btn_ocr.setText("OCR识别")
            self.status_label.setText("OCR已停止")
            self.capture_timer.stop()
    
    def _capture_and_analyze(self):
        """截图并分析"""
        if not self.is_capturing:
            return
        
        if self.is_processing:
            print("[V2] 正在处理中，跳过本次识别")
            return
        
        try:
            # 截图
            screenshot = self._take_screenshot()
            if screenshot is None:
                self.status_label.setText("截图失败")
                return
            
            # 转换为numpy数组
            img_array = self._screenshot_to_array(screenshot)
            if img_array is None:
                return
            
            # 创建OCR工作线程
            self.is_processing = True
            self.status_label.setText("识别中...")
            
            self.ocr_worker = OCRWorker(self.ocr_engine, img_array)
            self.ocr_worker.finished_signal.connect(self._on_ocr_finished)
            self.ocr_worker.error_signal.connect(self._on_ocr_error)
            self.ocr_worker.start()
            
        except Exception as e:
            print(f"[V2] 截图分析出错: {e}")
            self.status_label.setText(f"出错: {e}")
            self.is_processing = False
    
    def _take_screenshot(self):
        """截图（复用主程序的逻辑）"""
        try:
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtGui import QScreen
            
            # 获取主屏幕
            screen = QApplication.primaryScreen()
            if not screen:
                return None
            
            # 全屏截图（后续可添加区域选择）
            screenshot = screen.grabWindow(0)
            return screenshot
            
        except Exception as e:
            print(f"[V2] 截图失败: {e}")
            return None
    
    def _screenshot_to_array(self, screenshot):
        """将截图转换为numpy数组"""
        try:
            from PyQt6.QtCore import QByteArray
            
            qimage = screenshot.toImage()
            width = qimage.width()
            height = qimage.height()
            ptr = qimage.bits()
            ptr.setsize(qimage.sizeInBytes())
            arr = QByteArray(ptr.asstring())
            pil_image = Image.frombytes("RGB", (width, height), arr.data())
            img_array = np.array(pil_image)
            
            return img_array
        except Exception as e:
            print(f"[V2] 图像转换失败: {e}")
            self.status_label.setText(f"图像转换失败: {e}")
            return None
    
    def _on_ocr_finished(self, texts: List[str]):
        """OCR识别完成回调"""
        print(f"[V2] OCR识别完成，{len(texts)}条文本")
        
        if not self.is_capturing:
            self.is_processing = False
            return
        
        try:
            # 处理识别到的文本
            if texts:
                self.process_texts(texts)
                self.status_label.setText(f"识别完成，{len(texts)}条文本")
            else:
                self.status_label.setText("未识别到文本")
        
        except Exception as e:
            print(f"[V2] 处理OCR结果出错: {e}")
            self.status_label.setText(f"处理出错: {e}")
        finally:
            self.is_processing = False
    
    def _on_ocr_error(self, error: str):
        """OCR错误回调"""
        print(f"[V2] OCR错误: {error}")
        self.status_label.setText(f"OCR错误: {error}")
        self.is_processing = False
    
    def show_manual_input(self):
        """显示手动输入对话框"""
        dialog = ManualInputDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            text = dialog.get_text()
            if text.strip():
                lines = text.split('\n')
                self.process_texts(lines)
    
    def process_texts(self, texts: List[str]):
        """处理文本列表"""
        if not texts:
            return
        
        self.status_label.setText("解析中...")
        
        # 添加到原始日志（限制最多100条）
        self.raw_logs.extend(texts)
        if len(self.raw_logs) > 100:
            self.raw_logs = self.raw_logs[-100:]
        
        # 更新日志显示
        self.log_display.setPlainText('\n'.join(self.raw_logs))
        
        # 创建解析器并解析
        parser = TestParser()
        parser._analyze_texts(texts)
        
        # 保存结果
        new_items = parser.results
        self.parsed_items.extend(new_items)
        
        # 写入数据库
        for item in new_items:
            try:
                self.db.insert_record(item)
            except Exception as e:
                print(f"数据库插入失败: {e}")
        
        # 更新界面
        self.update_table()
        self.update_stats()
        
        self.status_label.setText(f"完成，提取 {len(new_items)} 条信息")
    
    def update_table(self):
        """更新表格显示"""
        # 应用筛选
        filtered_items = self.get_filtered_items()
        
        # 清空表格
        self.result_table.setRowCount(0)
        self.result_table.setRowCount(len(filtered_items))
        
        # 填充数据
        for i, item in enumerate(filtered_items):
            # 物品名称
            self.result_table.setItem(i, 0, QTableWidgetItem(item['name']))
            
            # 价格
            self.result_table.setItem(i, 1, QTableWidgetItem(f"{item['price']:.1f}"))
            
            # 交易类型
            type_item = QTableWidgetItem(item['trade_type'])
            if item['trade_type'] == 'buy':
                type_item.setForeground(QColor(255, 0, 0))  # 红色
            else:
                type_item.setForeground(QColor(0, 128, 0))  # 绿色
            self.result_table.setItem(i, 2, type_item)
            
            # 分类
            self.result_table.setItem(i, 3, QTableWidgetItem(item['category']))
            
            # 时间
            timestamp = item.get('timestamp', datetime.now())
            if isinstance(timestamp, str):
                time_str = timestamp
            else:
                time_str = timestamp.strftime("%H:%M:%S")
            self.result_table.setItem(i, 4, QTableWidgetItem(time_str))
            
            # 原始文本
            self.result_table.setItem(i, 5, QTableWidgetItem(item['full_text']))
        
        # 更新统计
        self.update_display_stats(filtered_items)
    
    def get_filtered_items(self) -> List[dict]:
        """获取筛选后的物品列表"""
        filtered = self.parsed_items
        
        # 分类筛选
        if self.filter_category != "全部":
            filtered = [
                item for item in filtered 
                if item['category'].startswith(self.filter_category)
            ]
        
        # 类型筛选
        if self.filter_trade_type == "收购":
            filtered = [item for item in filtered if item['trade_type'] == 'buy']
        elif self.filter_trade_type == "出售":
            filtered = [item for item in filtered if item['trade_type'] == 'sell']
        
        return filtered
    
    def apply_filter(self):
        """应用筛选条件"""
        self.filter_category = self.category_filter.currentText()
        self.filter_trade_type = self.type_filter.currentText()
        self.update_table()
    
    def update_stats(self):
        """更新采集区统计"""
        log_count = len(self.raw_logs)
        item_count = len(self.parsed_items)
        self.stats_label.setText(f"识别条数: {log_count} | 提取物品: {item_count}")
    
    def update_display_stats(self, items: List[dict]):
        """更新展示区统计"""
        total = len(items)
        buy_count = len([i for i in items if i['trade_type'] == 'buy'])
        sell_count = len([i for i in items if i['trade_type'] == 'sell'])
        
        self.display_stats_label.setText(
            f"共提取 {total} 条信息 | 收购 {buy_count} 条 | 出售 {sell_count} 条"
        )
    
    def clear_data(self):
        """清空数据"""
        reply = QMessageBox.question(
            self, 
            "确认清空", 
            "确定要清空所有数据吗？\n（数据库历史记录不会被清空）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.raw_logs.clear()
            self.parsed_items.clear()
            self.log_display.clear()
            self.update_table()
            self.update_stats()
            self.status_label.setText("数据已清空")
    
    def reload_code(self):
        """重载代码（调试功能）"""
        try:
            import importlib
            importlib.reload(nr)
            
            # 更新解析方法
            TestParser._analyze_texts = nr.MarketAnalysisTab._analyze_texts
            
            QMessageBox.information(self, "成功", "代码已重载！")
            self.status_label.setText("代码已重载")
        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            QMessageBox.critical(self, "错误", f"重载失败:\n{str(e)}\n\n{error_msg}")
    
    def closeEvent(self, event):
        """关闭事件"""
        # 停止OCR
        if self.is_capturing:
            self.is_capturing = False
            self.capture_timer.stop()
        
        # 关闭数据库
        self.db.close()
        super().closeEvent(event)
# ==================== 新增：价格趋势图标签页 ====================
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.dates import DateFormatter
import matplotlib.dates as mdates

class PriceTrendTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setWindowTitle("价格趋势")
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 顶部操作栏
        top_bar = QHBoxLayout()
        refresh_btn = QPushButton("刷新趋势图")
        refresh_btn.clicked.connect(self.plot_trend)
        top_bar.addWidget(QLabel("热门物品趋势："))
        top_bar.addWidget(refresh_btn)
        top_bar.addStretch()

        # 图表
        self.figure = Figure(figsize=(12, 7), facecolor='#2b2b2b')
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setStyleSheet("background:#2b2b2b;")

        layout.addLayout(top_bar)
        layout.addWidget(self.canvas, 1)
        self.plot_trend()  # 启动时自动画一次

    def plot_trend(self):
        try:
            conn = sqlite3.connect("market_data.db")
            df = pd.read_sql("""
                SELECT name, price, timestamp 
                FROM market_items 
                WHERE name IN ('高级必杀','伤害符','黑宝石','C66','神兜兜','炼兽真经','五色灵尘')
                ORDER BY timestamp
            """, conn, parse_dates=['timestamp'])
            conn.close()

            if df.empty:
                self.figure.clear()
                ax = self.figure.add_subplot(111)
                ax.text(0.5, 0.5, "暂无数据\n去采集几条记录再来看哦~", 
                       ha='center', va='center', fontsize=20, color='gray')
                ax.axis('off')
                self.canvas.draw()
                return

            self.figure.clear()
            ax = self.figure.add_subplot(111)
            ax.set_facecolor('#2b2b2b')
            self.figure.patch.set_facecolor('#2b2b2b')

            colors = ['#ff6b6b', '#4ecdc4', '#45b7d1', '#f9ca24', '#f3722c', '#a29bfe', '#fd79a8']
            for i, item in enumerate(df['name'].unique()):
                data = df[df['name'] == item]
                ax.plot(data['timestamp'], data['price'], 
                       'o-', label=f"{item} ({data['price'].iloc[-1]:.1f}万)", 
                       color=colors[i % len(colors)], linewidth=2.5, markersize=6)

            ax.set_title("梦幻西游热门物品实时价格趋势", fontsize=18, color='white', pad=20)
            ax.set_ylabel("价格（万）", fontsize=14, color='white')
            ax.set_xlabel("时间", fontsize=14, color='white')
            ax.legend(facecolor='#3a3a3a', labelcolor='white')
            ax.grid(True, alpha=0.3, color='gray')
            ax.tick_params(colors='white')
            ax.spines['bottom'].set_color('white')
            ax.spines['top'].set_color('white')
            ax.spines['left'].set_color('white')
            ax.spines['right'].set_color('white')

            # 美化时间轴
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
            self.figure.autofmt_xdate()

            self.canvas.draw()
        except Exception as e:
            print(f"趋势图绘制出错: {e}")

# 测试代码
if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    window = MarketAnalysisV2Tab()
    window.resize(1200, 800)
    window.show()
    sys.exit(app.exec())


