
import sys
import re
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QTextEdit, QTableWidget, QTableWidgetItem, 
                             QPushButton, QLabel, QHeaderView, QSplitter)
from PyQt6.QtCore import Qt

# Import logic from the main application
# We assume novel_reader_qt.py is in the same directory
import novel_reader_qt as nr

class TestParser:
    """
    A mock class that mimics MarketAnalysisTab for the purpose of testing _analyze_texts.
    We dynamically borrow the _analyze_texts method from the real class.
    """
    def __init__(self):
        # Initialize the matcher with the real aliases
        self.item_matcher = nr.SmartItemMatcher(nr.DEFAULT_ITEM_ALIASES)
        self.results = []

    def _record_price(self, match_info, trade_type, price, full_text, raw_name):
        """
        Mock implementation of _record_price to store results instead of updating UI.
        """
        self.results.append({
            "name": match_info.standard_name,
            "trade_type": trade_type,
            "price": price,
            "raw_name": raw_name,
            "full_text": full_text,
            "category": f"{match_info.category}-{match_info.subcategory}"
        })

    # Borrow the analyze method
    _analyze_texts = nr.MarketAnalysisTab._analyze_texts

class MarketParserTester(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("市场分析测试工具 (Market Parser Tester)")
        self.resize(1200, 800)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Splitter for Input (Top) and Output (Bottom)
        splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(splitter)
        
        # --- Input Area ---
        input_widget = QWidget()
        input_layout = QVBoxLayout(input_widget)
        
        input_label = QLabel("请在此粘贴游戏聊天记录 (Paste Chat Logs Here):")
        input_layout.addWidget(input_label)
        
        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("在此处粘贴文本...")
        input_layout.addWidget(self.text_input)
        
        self.analyze_btn = QPushButton("开始分析 (Analyze)")
        self.analyze_btn.setMinimumHeight(40)
        self.analyze_btn.clicked.connect(self.run_analysis)
        input_layout.addWidget(self.analyze_btn)
        
        # Add Reload Button
        self.reload_btn = QPushButton("重载代码 (Reload Code)")
        self.reload_btn.setMinimumHeight(30)
        self.reload_btn.clicked.connect(self.reload_code)
        input_layout.addWidget(self.reload_btn)
        
        splitter.addWidget(input_widget)
        
        # --- Output Area ---
        output_widget = QWidget()
        output_layout = QVBoxLayout(output_widget)
        
        self.stats_label = QLabel("分析结果: 0 个物品")
        output_layout.addWidget(self.stats_label)
        
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(6)
        self.result_table.setHorizontalHeaderLabels(["物品名称", "价格 (万)", "交易类型", "分类", "原始名称", "原始文本"])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.result_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        output_layout.addWidget(self.result_table)
        
        splitter.addWidget(output_widget)
        splitter.setSizes([300, 500])

    def reload_code(self):
        try:
            import importlib
            from PyQt6.QtWidgets import QMessageBox
            
            # Reload the module
            importlib.reload(nr)
            
            # Update TestParser with new logic
            TestParser._analyze_texts = nr.MarketAnalysisTab._analyze_texts
            
            QMessageBox.information(self, "Success", "代码已重载！\nCode reloaded successfully!")
        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"Reload failed:\n{str(e)}\n\n{error_msg}")

    def run_analysis(self):
        try:
            text = self.text_input.toPlainText()
            lines = text.split('\n')
            
            # Create our mock parser
            # Note: TestParser.__init__ uses nr.SmartItemMatcher, which will be the new one after reload
            parser = TestParser()
            
            # Run analysis
            # Note: _analyze_texts expects a list of strings
            # We need to bind the method or pass self explicitly if it's just assigned
            # Since we assigned it to the class, calling it on instance works like a normal method
            parser._analyze_texts(lines) 
            
            # Update UI
            self.result_table.setRowCount(0)
            self.result_table.setRowCount(len(parser.results))
            
            for i, res in enumerate(parser.results):
                self.result_table.setItem(i, 0, QTableWidgetItem(str(res['name'])))
                self.result_table.setItem(i, 1, QTableWidgetItem(str(res['price'])))
                
                type_item = QTableWidgetItem(str(res['trade_type']))
                if res['trade_type'] == 'buy':
                    type_item.setForeground(Qt.GlobalColor.red)
                else:
                    type_item.setForeground(Qt.GlobalColor.green)
                self.result_table.setItem(i, 2, type_item)
                
                self.result_table.setItem(i, 3, QTableWidgetItem(str(res['category'])))
                self.result_table.setItem(i, 4, QTableWidgetItem(str(res['raw_name'])))
                self.result_table.setItem(i, 5, QTableWidgetItem(str(res['full_text'])))
                
            self.stats_label.setText(f"分析结果: {len(parser.results)} 个物品")
            
        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            print(error_msg)
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", f"An error occurred:\n{str(e)}\n\n{error_msg}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MarketParserTester()
    window.show()
    sys.exit(app.exec())
