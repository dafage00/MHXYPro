import os
import sys
import json
import time
import re
import socket
import posixpath
import html
import copy
import difflib
import unicodedata
try:
    import qrcode
    from PIL import ImageQt
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import unquote, parse_qs, urlparse
from typing import List, Dict, Optional, Tuple, Any, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
import threading
from functools import partial

from PyQt6.QtCore import Qt, QUrl, QTimer, pyqtSlot, pyqtSignal, QDate, QByteArray, QBuffer, QIODevice, QRect, QThread
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QPushButton,
    QSplitter,
    QTextEdit,
    QComboBox,
    QLineEdit,
    QTabWidget,
    QFileDialog,
    QMessageBox,
    QGroupBox,
    QFormLayout,
    QSlider,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QDialog,
    QRadioButton,
    QButtonGroup,
    QTimeEdit,
    QDateEdit,
    QCheckBox,
    QSpinBox,
    QDoubleSpinBox,
    QInputDialog,
    QGridLayout,
    QDialogButtonBox,
    QMenu,
    QAbstractItemView,
    QTreeWidget,
    QTreeWidgetItem,
    QPlainTextEdit,
    QTextBrowser,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineDownloadRequest
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

from PyQt6.QtGui import QTextCursor, QTextCharFormat, QDesktopServices, QScreen, QPixmap, QImage, QPainter, QPen, QColor

from daily_brief_fetchers import (
    BriefFetcherBase,
    SampleStaticFetcher,
    build_default_fetchers,
)

# OCR 相关导入（可选，如果未安装会提示）
try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False

try:
    from PIL import ImageGrab, Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import numpy as np
    # 兼容旧版 PaddleOCR 使用的 np.int/np.float/np.bool 等别名
    if not hasattr(np, "int"):
        np.int = int  # type: ignore[attr-defined]
    if not hasattr(np, "float"):
        np.float = float  # type: ignore[attr-defined]
    if not hasattr(np, "bool"):
        np.bool = bool  # type: ignore[attr-defined]
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    from pypinyin import lazy_pinyin
    PINYIN_AVAILABLE = True
except ImportError:
    PINYIN_AVAILABLE = False

from novel_manager import NovelManager
from novel_fetcher import create_fetcher
from tts_manager import TTSManager
import time


CONFIG_FILE = os.path.join(os.path.dirname(__file__), "download_sites.json")
HISTORY_FILE = os.path.join(os.path.dirname(__file__), "novels_data", "browser_history.json")
CACHE_DIR = os.path.join(os.path.dirname(__file__), "novels_data", "browser_cache")
ALARM_DATA_FILE = os.path.join(os.path.dirname(__file__), "novels_data", "alarms.json")
LEDGER_DATA_FILE = os.path.join(os.path.dirname(__file__), "novels_data", "ledger.json")
DAILY_BRIEF_FILE = os.path.join(os.path.dirname(__file__), "novels_data", "daily_brief.json")

# --- 游戏物品数据库优化版 (商人专用) ---

ITEM_CATEGORY_CHOICES = ["硬通货", "军火/装备", "宝宝/炼妖", "杂货"]
DEFAULT_ITEM_CATEGORY = "杂货"

# 物品分类树 - 逻辑优化
CATEGORY_TREE: Dict[str, Dict[str, List[str]]] = {
    "硬通货": {
        "五宝": ["金刚石", "定魂珠", "夜光珠", "龙鳞", "避水珠"],
        "宝石": ["黑宝石", "红玛瑙", "月亮石", "舍利子", "光芒石", "太阳石", "神秘石", "翡翠石"],
        "修炼": ["九转金丹", "修炼果"],
        "强化": ["强化石", "符石", "星辉石", "元身"],
    },
    "消耗品": {
        "炼兽": ["金柳露", "超级金柳露", "净瓶玉露"],
        "任务": ["导标旗", "飞行符", "摄妖香", "洞冥草"],
        "回复": ["包子", "烤鸭", "翡翠豆腐", "佛跳墙", "大金", "九转"],
    },
    "军火/装备": {
        "未鉴定": ["未鉴定", "指南书", "百炼精铁", "灵饰指南书", "元灵晶石"],
        "环装": ["60环", "70环", "80环", "武器", "装备"],
        "灵饰": ["戒指", "耳饰", "手镯", "佩饰"],
    },
    "宝宝/炼妖": {
        "兽决": ["魔兽要诀", "高级魔兽要诀"],
        "胚子": ["持国", "广目", "童子", "画魂", "吸血鬼"],
        "神兽": ["超级神兽", "神兜兜"],
    },
    "杂货": {
        "任务道具": ["藏宝图", "特赦令牌"],
        "其他": ["花豆", "彩果", "树苗"],
    }
}

# 物品别名数据库 - 包含常用黑话
DEFAULT_ITEM_ALIASES: Dict[str, Dict[str, object]] = {
    # --- 五宝 ---
    "金刚石": {"aliases": ["金刚", "大金刚"], "category": "硬通货", "subcategory": "五宝"},
    "定魂珠": {"aliases": ["定魂", "大定魂"], "category": "硬通货", "subcategory": "五宝"},
    "夜光珠": {"aliases": ["夜光"], "category": "硬通货", "subcategory": "五宝"},
    "龙鳞": {"aliases": ["龙鳞"], "category": "硬通货", "subcategory": "五宝"},
    "避水珠": {"aliases": ["避水"], "category": "硬通货", "subcategory": "五宝"},
    "特赦令牌": {"aliases": ["牌子", "令牌", "做牌子"], "category": "杂货", "subcategory": "任务道具"},

    # --- 宝石 ---
    "黑宝石": {"aliases": ["黑宝", "黑石头"], "category": "硬通货", "subcategory": "宝石"},
    "红玛瑙": {"aliases": ["玛瑙", "红石头"], "category": "硬通货", "subcategory": "宝石"},
    "月亮石": {"aliases": ["月亮"], "category": "硬通货", "subcategory": "宝石"},
    "舍利子": {"aliases": ["舍利"], "category": "硬通货", "subcategory": "宝石"},
    "光芒石": {"aliases": ["光芒"], "category": "硬通货", "subcategory": "宝石"},
    "太阳石": {"aliases": ["太阳"], "category": "硬通货", "subcategory": "宝石"},
    "星辉石": {"aliases": ["星辉"], "category": "硬通货", "subcategory": "强化"},

    # --- 炼兽/消耗 ---
    # --- 炼兽/消耗 ---
    "金柳露": {"aliases": ["66", "六六", "柳露"], "category": "消耗品", "subcategory": "炼兽"},
    "超级金柳露": {"aliases": ["c66", "C66", "超66", "超级66"], "category": "消耗品", "subcategory": "培养"},
    "静岳": {"aliases": ["静月", "真元静岳"], "category": "宝宝/炼妖", "subcategory": "内丹"},
    "狂怒": {"aliases": ["狂怒"], "category": "宝宝/炼妖", "subcategory": "内丹"},
    "撞击": {"aliases": ["撞击"], "category": "宝宝/炼妖", "subcategory": "内丹"},
    "灵光": {"aliases": ["灵光"], "category": "宝宝/炼妖", "subcategory": "内丹"},
    "灵身": {"aliases": ["灵身"], "category": "宝宝/炼妖", "subcategory": "内丹"},
    "迅敏": {"aliases": ["迅敏"], "category": "宝宝/炼妖", "subcategory": "内丹"},
    "连环": {"aliases": ["连环"], "category": "宝宝/炼妖", "subcategory": "内丹"},
    "矫健": {"aliases": ["矫健"], "category": "宝宝/炼妖", "subcategory": "内丹"},
    "水漫金山": {"aliases": ["大雨", "水漫"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "水攻": {"aliases": ["小雨"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "避水珠": {"aliases": ["碧水"], "category": "硬通货", "subcategory": "五宝"},
    "金刚石": {"aliases": ["金刚"], "category": "硬通货", "subcategory": "五宝"},
    "定魂珠": {"aliases": ["定魂"], "category": "硬通货", "subcategory": "五宝"},
    "夜光珠": {"aliases": ["夜光"], "category": "硬通货", "subcategory": "五宝"},
    "龙鳞": {"aliases": ["龙鳞"], "category": "硬通货", "subcategory": "五宝"},
    "强化石": {"aliases": ["强化"], "category": "硬通货", "subcategory": "强化"},
    "吸血": {"aliases": ["吸血"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "必杀": {"aliases": ["必杀"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "夜战": {"aliases": ["夜战"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "偷袭": {"aliases": ["偷袭"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "月华露": {"aliases": ["月华"], "category": "消耗品", "subcategory": "培养"},
    "彩果": {"aliases": ["彩果", "果"], "category": "杂货", "subcategory": "其他"},
    "树苗": {"aliases": ["树苗", "摇钱树苗", "特赦令牌树苗"], "category": "杂货", "subcategory": "其他"},
    "魔兽要诀": {"aliases": ["兽决", "低兽决", "垃圾兽决", "兽诀"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级魔兽要诀": {"aliases": ["高兽决", "高兽", "高级兽决", "高兽诀"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "神兜兜": {"aliases": ["兜兜"], "category": "宝宝/炼妖", "subcategory": "神兽"},
    "修炼果": {"aliases": ["果子"], "category": "硬通货", "subcategory": "修炼"},
    "九转金丹": {"aliases": ["金丹"], "category": "硬通货", "subcategory": "修炼"},

    # --- 杂货/任务 ---
    "藏宝图": {"aliases": ["宝图", "图"], "category": "杂货", "subcategory": "任务道具"},
    "符石": {"aliases": ["符石", "一级符石"], "category": "硬通货", "subcategory": "强化"},
    
    # --- 军火 ---
    "未鉴定": {"aliases": ["未鉴定", "军火"], "category": "军火/装备", "subcategory": "未鉴定"},
    "灵饰指南书": {"aliases": ["灵饰书", "戒指书", "耳饰书"], "category": "军火/装备", "subcategory": "未鉴定"},
    "元灵晶石": {"aliases": ["晶石", "铁"], "category": "军火/装备", "subcategory": "未鉴定"},
    
    # --- 任务相关 ---
    "抓鬼": {"aliases": ["抓鬼任务", "X抓鬼", "抓鬼", "鬼"], "category": "杂货", "subcategory": "任务道具"},
    "环任务": {"aliases": ["环", "环装"], "category": "杂货", "subcategory": "任务道具"},
    "试剑石": {"aliases": ["试剑"], "category": "杂货", "subcategory": "任务道具"},
    "三级种子": {"aliases": ["种子", "三级"], "category": "杂货", "subcategory": "其他"},
    "蝴蝶卡": {"aliases": ["蝶卡"], "category": "杂货", "subcategory": "其他"},
    "珍珠": {"aliases": ["珠"], "category": "杂货", "subcategory": "其他"},
    "金银锦盒": {"aliases": ["锦盒", "金银盒"], "category": "杂货", "subcategory": "任务道具"},
    
    # --- 兽决技能 ---
    "小法": {"aliases": ["小法术"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "吸收": {"aliases": ["吸收法术"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "质量兽决": {"aliases": ["质量"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级再生": {"aliases": ["高再生", "再生"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级防御": {"aliases": ["高防御", "高防", "防御"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级必杀": {"aliases": ["高必杀", "高必"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级偷袭": {"aliases": ["高偷袭", "高偷"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级连击": {"aliases": ["高连击", "高连"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级神佑复生": {"aliases": ["高神佑", "高神"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级吸血": {"aliases": ["高吸血", "高吸"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级夜战": {"aliases": ["高夜战", "高夜"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级敏捷": {"aliases": ["高敏捷", "高敏"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级法术暴击": {"aliases": ["高法暴", "高法爆", "高级法爆", "法爆"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级魔之心": {"aliases": ["高魔心", "魔心"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级法术连击": {"aliases": ["高法连", "法连"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级法术波动": {"aliases": ["高法波", "法波"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级反震": {"aliases": ["高反震", "反震"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级强力": {"aliases": ["高强力", "强力"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级隐身": {"aliases": ["高隐身", "隐身"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级驱鬼": {"aliases": ["高驱鬼", "驱鬼"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级感知": {"aliases": ["高感知", "感知"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级招架": {"aliases": ["高招架", "招架"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级幸运": {"aliases": ["高幸运", "幸运"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级冥思": {"aliases": ["高冥思", "冥思"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级慧根": {"aliases": ["高慧根", "慧根"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级永恒": {"aliases": ["高永恒", "永恒"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级精神集中": {"aliases": ["高精神", "精神集中"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级神迹": {"aliases": ["高神迹", "神迹"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级否定信仰": {"aliases": ["高否定", "否定信仰"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "高级鬼魂术": {"aliases": ["高鬼魂", "鬼魂"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "催心浪": {"aliases": ["催心"], "category": "宝宝/炼妖", "subcategory": "内丹"},
    "生死决": {"aliases": ["生死"], "category": "宝宝/炼妖", "subcategory": "内丹"},
    "壁垒击破": {"aliases": ["壁垒"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "大法": {"aliases": ["大法", "泰山", "泰山压顶", "奔雷", "奔雷咒", "地狱", "地狱烈火", "烈火"], "category": "宝宝/炼妖", "subcategory": "兽决"},
    "炼兽真经": {"aliases": ["真经", "炼兽"], "category": "硬通货", "subcategory": "修炼"},
    
    # --- 临时符 ---
    "伤害符": {"aliases": ["伤害符", "伤害", "伤害F", "伤害FF", "伤害FFF"], "category": "临时符", "subcategory": "伤害"},
    "体质符": {"aliases": ["体质符", "体质", "血符", "血F", "血FF", "血FFF", "魔王血", "魔王血fff"], "category": "临时符", "subcategory": "体质"},
    "命中符": {"aliases": ["命中符", "命中", "命", "命F", "命FF", "命FFF"], "category": "临时符", "subcategory": "命中"},
    "防御符": {"aliases": ["防御符", "防御", "防御F", "防御FF", "防御FFF"], "category": "临时符", "subcategory": "防御"},
    "魔法符": {"aliases": ["魔法符", "魔法", "魔法F", "魔法FF"], "category": "临时符", "subcategory": "魔法"},
    "速度符": {"aliases": ["速度符", "速度", "速度F", "速度FF"], "category": "临时符", "subcategory": "速度"},
    "耐力符": {"aliases": ["耐力符", "耐力", "耐力F", "耐力FF", "临时耐力"], "category": "临时符", "subcategory": "耐力"},
    "灵力符": {"aliases": ["灵力符", "灵力", "法伤符", "法伤", "法伤F", "法伤FF", "法伤FFF"], "category": "临时符", "subcategory": "灵力"},
    "愤怒符": {"aliases": ["愤怒符", "愤怒", "愤怒F", "愤怒FF"], "category": "临时符", "subcategory": "愤怒"},
    "魔力符": {"aliases": ["魔力符", "魔力", "魔力F", "魔力FF"], "category": "临时符", "subcategory": "魔法"},
    "法防符": {"aliases": ["法防符", "法防", "法防F", "法防FF", "法防FFF"], "category": "临时符", "subcategory": "防御"},
    
    # --- 收费带队 ---
    "D3": {"aliases": ["D3", "d3", "地三", "地3", "烧双", "D3烧双"], "category": "收费带队", "subcategory": "场景"},
    "飞贼": {"aliases": ["飞贼", "贼"], "category": "收费带队", "subcategory": "活动"},
    "铃铛": {"aliases": ["铃铛"], "category": "收费带队", "subcategory": "周末活动"},
    "慈心": {"aliases": ["慈心"], "category": "收费带队", "subcategory": "周末活动"},
    
    # --- 装备相关 ---
    "图吉": {"aliases": ["展级图吉"], "category": "军火/装备", "subcategory": "武器"},
    "小板": {"aliases": ["板"], "category": "军火/装备", "subcategory": "防具"},
    "小钉": {"aliases": ["钉"], "category": "军火/装备", "subcategory": "武器"},
    "套装": {"aliases": ["套", "级套装"], "category": "军火/装备", "subcategory": "装备"},
    
    # --- 宝石类 ---
    "五色灵尘": {"aliases": ["灵尘", "五色"], "category": "硬通货", "subcategory": "宝石"},
    "黑宝石": {"aliases": ["黑宝"], "category": "硬通货", "subcategory": "宝石"},
    "星辉石": {"aliases": ["星辉"], "category": "硬通货", "subcategory": "宝石"},
    "红玛瑙": {"aliases": ["玛瑙", "红玛"], "category": "硬通货", "subcategory": "宝石"},
    "舍利子": {"aliases": ["舍利"], "category": "硬通货", "subcategory": "宝石"},
    "月亮石": {"aliases": ["月亮"], "category": "硬通货", "subcategory": "宝石"},
    "太阳石": {"aliases": ["太阳"], "category": "硬通货", "subcategory": "宝石"},
    "光芒石": {"aliases": ["光芒"], "category": "硬通货", "subcategory": "宝石"},
    "翡翠石": {"aliases": ["翡翠"], "category": "硬通货", "subcategory": "宝石"},
    
    # --- 消耗品 ---
    "仙露丸子": {"aliases": ["仙露", "丸子"], "category": "消耗品", "subcategory": "药品"},
    
    # --- 宝宝/召唤兽 ---
    "谛听": {"aliases": ["谛听"], "category": "宝宝/炼妖", "subcategory": "神兽"},
    "持国天王": {"aliases": ["持国", "持国天"], "category": "宝宝/炼妖", "subcategory": "神兽"},
    "多闻天王": {"aliases": ["多闻", "多闻天"], "category": "宝宝/炼妖", "subcategory": "神兽"},
    "广目天王": {"aliases": ["广目", "广目天"], "category": "宝宝/炼妖", "subcategory": "神兽"},
    "涂山瞳": {"aliases": ["涂山"], "category": "宝宝/炼妖", "subcategory": "神兽"},
    "龙龟": {"aliases": ["龟"], "category": "宝宝/炼妖", "subcategory": "召唤兽"},
    "凤凰": {"aliases": ["凤"], "category": "宝宝/炼妖", "subcategory": "神兽"},
}

COMMON_GAME_ITEMS: Dict[str, str] = {
    key: meta.get("category", DEFAULT_ITEM_CATEGORY)
    for key, meta in DEFAULT_ITEM_ALIASES.items()
}

ITEM_NAME_STOPWORDS = {
    "收", "卖", "出", "求", "秒", "来", "速来", "高价", "低价", "便宜", 
    "价格", "数量", "其他", "一起", "套", "一套", "一车", "一组", 
    "一个", "两个", "几个", "很多", "大量", "少量", "多件", "多张", 
    "多瓶", "件", "个", "瓶", "张", "条", "只", "W", "w", "万", "m", "M"
}

MAX_ITEM_NAME_LENGTH = 8
COMMON_GAME_ITEM_NAMES = set(DEFAULT_ITEM_ALIASES.keys())

CATEGORY_KEYWORD_MAP: List[Tuple[str, str, List[str]]] = []
for cat, sub_map in CATEGORY_TREE.items():
    for sub_cat, keywords in sub_map.items():
        CATEGORY_KEYWORD_MAP.append((cat, sub_cat, keywords))

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002700-\U000027BF"
    "\U000024C2-\U0001F251"
    "]+",
    flags=re.UNICODE,
)

GENERIC_PRICE_PATTERN = re.compile(
    r'([\u4e00-\u9fa5A-Za-z0-9\-·\(\)【】\[\]]{2,20})[^\d]{0,6}?(\d+(?:\.\d+)?)([亿千万wW百千]?)(?!\d)'
)

BUY_KEYWORDS = [
    "收", "回收", "求购", "求", "收购", "收一个", "收个", "收货", "收价", "收来", "收下", "收走",
    "收购价", "求个", "收点", "求带"
]
SELL_KEYWORDS = [
    "出", "出售", "甩", "卖", "处理", "带走", "要的", "有的", "拿走", "出个", "出售一", "甩卖", "甩出",
    "来个", "来一", "来拿", "来价", "来秒", "来个老板", "来人", "欢迎咨询", "欢迎秒", "给钱就卖"
]


def preprocess_text_line(text: str) -> str:
    """清洗 OCR 文本 -保留中文、数字、字母"""
    if not hasattr(preprocess_text_line, '_call_count'):
        preprocess_text_line._call_count = 0
    
    # 移除时间戳 (如 "[22:57:10]", "[11:30:45]")
    text = re.sub(r'\[\d{1,2}:\d{2}:\d{2}\]', ' ', text)
    
    # 移除玩家名称格式 (如 "[测试玩家1]", "[玩家名]")
    # 注意：这个要小心，不要误删其他方括号内容
    text = re.sub(r'\[[^\]]{2,10}\]', ' ', text)
    
    # 移除引号、顿号、感叹号、句号、冒号
    text = re.sub(r'["""\'、!！。;：:]', " ", text)
    
    # 移除游戏内颜色代码/表情代码 (如 #Y, #G, #cff00ff, #23)
    text = re.sub(r'#([0-9a-fA-F]{6}|[0-9a-fA-F]{3}|[A-Z]|\d+)', " ", text)
    
    # 移除括号内的内容 (通常是玩家ID或其他注释，如 "(P 36 97797777)" 或 "(11555117)")
    text = re.sub(r'[（\(][^）\)]*[）\)]', " ", text)
    
    # 移除场景/位置编号 (如 "在703", "任在703", "场景703", "来703")
    # 这些数字不是价格，而是游戏场景编号
    text = re.sub(r'(在|任在|场景|来|去|到)\s*\d{1,4}', r'\1', text)
    
    # [New] 合并被误加空格的数字 (如 "9 9" -> "99", "8 0" -> "80")
    # 仅合并两个单数字，避免合并 "20 20" 这种情况
    text = re.sub(r'(?<=\d)\s+(?=\d)', '', text)
    
    # [New] 将 "超66", "C66" 替换为 "超级金柳露"，避免 "66" 被识别为价格
    text = re.sub(r'(c66|C66|超66)', '超级金柳露', text, flags=re.IGNORECASE)
    
    # 合并多个空格
    text = re.sub(r'\s+', ' ', text)
    result = text.strip()
    
    return result


def normalize_price_value(price_str: str) -> Optional[float]:
    if not price_str:
        return None
    # 移除逗号和空格
    price_str = price_str.replace(",", "").replace(" ", "").lower()
    
    # 处理 "1200w" "1.2亿" 等格式
    multiplier = 1.0
    if "亿" in price_str:
        multiplier = 10000.0
    elif "千万" in price_str:
        multiplier = 1000.0
    elif any(unit in price_str for unit in ["万", "w", "m"]):
        multiplier = 1.0
    elif "千" in price_str or "k" in price_str:
        multiplier = 0.1
    
    # 提取数字部分 - 修复：\d 改为 \d，确保提取完整数字
    match = re.search(r'(\d+(?:\.\d+)?)', price_str)
    if not match:
        return None
        
    value = float(match.group(0))
    
    # 智能数值修正 (针对没有单位的情况)
    # 如果没有单位，且数值 > 10000，假设是游戏币直接数值，转换为万
    if multiplier == 1.0 and not any(u in price_str for u in ["万", "w", "m", "亿"]):
        if value > 10000:
            value = value / 10000.0
            
    return round(value * multiplier, 4)


@dataclass
class ItemMatchResult:
    standard_name: str
    category: str
    subcategory: str
    confidence: float
    method: str
    raw_name: str


class SmartItemMatcher:
    """负责物品名称匹配、错别字纠正、分类推断"""

    def __init__(self, alias_config: Dict[str, Dict[str, object]]):
        self.alias_config: Dict[str, Dict[str, object]] = {}
        self.alias_to_canonical: Dict[str, str] = {}
        self.pinyin_to_canonical: Dict[str, str] = {}
        self.canonical_meta: Dict[str, Dict[str, object]] = {}
        self.canonical_names: List[str] = []
        self.update_aliases(alias_config)

    def update_aliases(self, alias_config: Dict[str, Dict[str, object]]):
        self.alias_config = alias_config or {}
        self.alias_to_canonical.clear()
        self.pinyin_to_canonical.clear()
        self.canonical_meta.clear()
        self.canonical_names = sorted(self.alias_config.keys())

        for canonical, meta in self.alias_config.items():
            aliases = set(meta.get("aliases", []) or [])
            aliases.add(canonical)
            normalized_aliases = set()
            for alias in aliases:
                normalized = self._normalize_token(alias)
                if not normalized:
                    continue
                self.alias_to_canonical[normalized] = canonical
                normalized_aliases.add(normalized)
                if PINYIN_AVAILABLE:
                    py_key = self._pinyin_key(alias)
                    if py_key:
                        self.pinyin_to_canonical[py_key] = canonical
            stored_meta = {
                "aliases": list(normalized_aliases),
                "category": meta.get("category", "杂项"),
                "subcategory": meta.get("subcategory", "未分类"),
                "keywords": meta.get("keywords", []),
            }
            self.canonical_meta[canonical] = stored_meta

    def _normalize_token(self, token: str) -> str:
        if not token:
            return ""
        token = unicodedata.normalize("NFKC", token)
        token = token.replace(" ", "").replace("\u3000", "")
        token = re.sub(r'[^\u4e00-\u9fa5A-Za-z0-9]', "", token)
        return token.lower()

    def _pinyin_key(self, token: str) -> str:
        if not PINYIN_AVAILABLE:
            return ""
        token = token.strip()
        if not token:
            return ""
        return "".join(lazy_pinyin(token)).lower()

    def _calc_similarity(self, a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        return difflib.SequenceMatcher(None, a, b).ratio()

    def match(self, raw_name: str) -> Optional[ItemMatchResult]:
        if not raw_name:
            return None
        normalized = self._normalize_token(raw_name)
        if not normalized or len(normalized) < 2:
            return None

        # 1. 精确匹配 (Priority 1)
        canonical = self.alias_to_canonical.get(normalized)
        if canonical:
            return self._make_result(canonical, 1.0, "exact", raw_name)

        # 2. 包含匹配 (Priority 2) - 比如 "收C66" -> "超级金柳露"
        for alias_norm, canon in self.alias_to_canonical.items():
            if len(alias_norm) > 1 and (alias_norm in normalized or normalized in alias_norm):
                # 长度差异不能太大
                if abs(len(alias_norm) - len(normalized)) <= 2:
                    return self._make_result(canon, 0.9, "contains", raw_name)

        # 3. 拼音匹配 (Priority 3)
        if PINYIN_AVAILABLE:
            py_key = self._pinyin_key(raw_name)
            canonical = self.pinyin_to_canonical.get(py_key)
            if canonical:
                return self._make_result(canonical, 0.85, "pinyin", raw_name)

        # 4. 编辑距离匹配 (Priority 4) - 仅当置信度很高时
        best_match = None
        best_score = 0.0
        for canon in self.canonical_names:
            # 对比标准名
            score = self._calc_similarity(normalized, self._normalize_token(canon))
            if score > best_score:
                best_score = score
                best_match = canon
            
            # 对比别名
            meta = self.canonical_meta.get(canon, {})
            for alias in meta.get("aliases", []):
                score_alias = self._calc_similarity(normalized, alias)
                if score_alias > best_score:
                    best_score = score_alias
                    best_match = canon

        if best_match and best_score >= 0.85:  # 提高阈值，减少误判
            return self._make_result(best_match, best_score, "fuzzy", raw_name)

        return None

    def scan(self, text: str) -> Optional[ItemMatchResult]:
        """在文本中扫描已知的物品别名"""
        if not text:
            return None
            
        normalized_text = self._normalize_token(text)
        best_match = None
        best_pos = -1
        best_len = 0
        
        # 遍历所有别名，寻找是否存在于文本中
        # 这是一个 O(N*M) 的操作，但 N (别名数量) 不大，M (文本长度) 很短，所以可以接受
        for alias, canon in self.alias_to_canonical.items():
            # alias 已经是 normalized 的
            # 我们需要找到它在 normalized_text 中的位置
            idx = normalized_text.rfind(alias)
            if idx != -1:
                # 找到了。策略：优先选择位置最靠后的 (离价格最近)，其次选择最长的 (特异性高)
                end_pos = idx + len(alias)
                if end_pos > best_pos:
                    best_pos = end_pos
                    best_match = (canon, alias)
                    best_len = len(alias)
                elif end_pos == best_pos:
                    if len(alias) > best_len:
                        best_match = (canon, alias)
                        best_len = len(alias)
        
        if best_match:
            # 注意：这里返回的 raw_name 是 alias，而不是原始文本中的片段
            # 这在 _analyze_texts 中使用 rfind(match_back.raw_name) 时可能会有问题
            # 如果原始文本中的 alias 大小写不同。
            # 但 alias_to_canonical 中的 alias 是 normalized (lower case)。
            # normalized_text 也是 lower case。
            # 所以我们需要返回原始文本中对应的片段吗？
            # _analyze_texts 会在 clean_line (未 lower) 中查找 raw_name。
            # 如果 raw_name 是 lower 的，可能会找不到。
            # 所以我们需要返回原始文本中的片段。
            
            # 由于我们不知道原始文本中 alias 的确切形式 (大小写)，
            # 我们只能返回 alias (normalized)。
            # 并在 _analyze_texts 中做不区分大小写的查找，或者在这里做映射。
            # 简单起见，我们假设 alias 大多是中文或数字，大小写不敏感。
            # 对于英文 (如 D3, c66)，我们需要小心。
            # 让我们尝试在原始 text 中找到它。
            
            # 重新在原始 text 中定位
            # 这是一个简化的定位，可能不完美
            canon_name, matched_alias = best_match
            
            # 尝试在 text 中找到 matched_alias (忽略大小写)
            idx = text.lower().rfind(matched_alias)
            if idx != -1:
                actual_raw_name = text[idx : idx + len(matched_alias)]
                return self._make_result(canon_name, 0.9, "scan", actual_raw_name)
            
            # Fallback
            return self._make_result(canon_name, 0.9, "scan", matched_alias)
            
        return None

    def scan_forward(self, text: str) -> Optional[ItemMatchResult]:
        """在文本中扫描已知的物品别名 (优先匹配开头的)"""
        if not text:
            return None
            
        normalized_text = self._normalize_token(text)
        best_match = None
        best_pos = float('inf')
        best_len = 0
        
        for alias, canon in self.alias_to_canonical.items():
            idx = normalized_text.find(alias)
            if idx != -1:
                # 找到了。策略：优先选择位置最靠前的 (离价格最近)，其次选择最长的
                if idx < best_pos:
                    best_pos = idx
                    best_match = (canon, alias)
                    best_len = len(alias)
                elif idx == best_pos:
                    if len(alias) > best_len:
                        best_match = (canon, alias)
                        best_len = len(alias)
        
        if best_match:
            canon_name, matched_alias = best_match
            idx = text.lower().find(matched_alias)
            if idx != -1:
                actual_raw_name = text[idx : idx + len(matched_alias)]
                return self._make_result(canon_name, 0.9, "scan_fwd", actual_raw_name)
            return self._make_result(canon_name, 0.9, "scan_fwd", matched_alias)
            
        return None

    def _infer_category_from_name(self, name: str) -> Tuple[Optional[str], Optional[str]]:
        for cat, sub_cat, keywords in CATEGORY_KEYWORD_MAP:
            for kw in keywords:
                if kw and kw in name:
                    return cat, sub_cat
        return None, None

    def _make_result(self, canonical: str, confidence: float, method: str, raw_name: str) -> ItemMatchResult:
        meta = self.canonical_meta.get(canonical, {})
        category = meta.get("category", "杂项")
        subcategory = meta.get("subcategory", "未分类")
        return ItemMatchResult(
            standard_name=canonical,
            category=category,
            subcategory=subcategory,
            confidence=round(confidence, 3),
            method=method,
            raw_name=raw_name,
        )

PROFIT_ITEM_GROUPS = [
    {
        "name": "环装/五宝/兽决专区",
        "items": [
            {"name": "60武器", "default_price": None},
            {"name": "70武器", "default_price": None},
            {"name": "80武器", "default_price": None},
            {"name": "60防具", "default_price": None},
            {"name": "70防具", "default_price": None},
            {"name": "80防具", "default_price": None},
            {"name": "金刚石", "default_price": None},
            {"name": "定魂珠", "default_price": None},
            {"name": "夜光珠", "default_price": None},
            {"name": "避水珠", "default_price": None},
            {"name": "龙鳞石", "default_price": None},
            {"name": "特赦令牌", "default_price": None},
            {"name": "兽诀", "default_price": None},
            {"name": "高兽诀", "default_price": None},
        ],
    },
    {
        "name": "C6修炼果专区",
        "items": [
            {"name": "月华露", "default_price": None},
            {"name": "金丹", "default_price": None},
            {"name": "金柳露", "default_price": None},
            {"name": "超级金柳露", "default_price": None},
            {"name": "净瓶玉露", "default_price": None},
            {"name": "超级净瓶玉露", "default_price": None},
            {"name": "修炼果", "default_price": None},
        ],
    },
    {
        "name": "宝石/乐器/花卉专区",
        "items": [
            {"name": "玛瑙", "default_price": None},
            {"name": "符石", "default_price": None},
            {"name": "太阳石", "default_price": None},
            {"name": "光芒石", "default_price": None},
            {"name": "舍利子", "default_price": None},
            {"name": "黑宝石", "default_price": None},
            {"name": "月亮石", "default_price": None},
            {"name": "强化石", "default_price": None},
            {"name": "神秘石", "default_price": None},
            {"name": "翡翠石", "default_price": None},
            {"name": "星辉石", "default_price": None},
            {"name": "吹拉弹唱", "default_price": None},
            {"name": "花卉", "default_price": None},
        ],
    },
    {
        "name": "其他专区",
        "items": [
            {"name": "法宝书", "default_price": None},
            {"name": "盒子", "default_price": None},
            {"name": "厕纸", "default_price": None},
            {"name": "宝图", "default_price": None},
            {"name": "莲藕", "default_price": None},
            {"name": "海马", "default_price": None},
            {"name": "彩果", "default_price": None},
            {"name": "图策", "default_price": None},
            {"name": "炼妖石", "default_price": None},
            {"name": "变身卡", "default_price": None},
            {"name": "珍珠", "default_price": None},
            {"name": "内丹", "default_price": None},
            {"name": "高内丹", "default_price": None},
            {"name": "附魔", "default_price": None},
            {"name": "灵饰书", "default_price": None},
            {"name": "晶石", "default_price": None},
        ],
    },
]


class DailyBriefManager:
    """负责每日简报的数据存储与读取"""

    def __init__(self, storage_path: str = DAILY_BRIEF_FILE):
        self.storage_path = storage_path
        self._data = self._load()

    def _load(self) -> Dict:
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as exc:
                print(f"加载每日简报失败: {exc}")
        return {}

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            print(f"保存每日简报失败: {exc}")

    def get_brief(self, date_str: str) -> Optional[Dict]:
        return self._data.get(date_str)

    def save_brief(self, date_str: str, brief: Dict):
        self._data[date_str] = brief
        self._save()

    def list_dates(self) -> List[str]:
        return sorted(self._data.keys(), reverse=True)


class DailyBriefGenerator:
    """负责协调抓取器并生成摘要"""

    def __init__(self, fetchers: Optional[List[BriefFetcherBase]] = None):
        self.fetchers: List[BriefFetcherBase] = fetchers or build_default_fetchers()
        if not self.fetchers:
            self.fetchers = [SampleStaticFetcher()]

    def register_fetcher(self, fetcher: BriefFetcherBase):
        self.fetchers.append(fetcher)

    def generate_brief(self, min_items: int = 30) -> Dict:
        aggregated: List[Dict] = []
        for fetcher in self.fetchers:
            try:
                fetched = fetcher.fetch_items()
                processed = []
                for item in fetched:
                    record = self._build_record(item)
                    if record:
                        processed.append(record)
                aggregated.extend(processed)
            except Exception as exc:
                print(f"抓取器 {fetcher.name} 失败: {exc}")

        aggregated = self._normalize_items(aggregated)
        if len(aggregated) < min_items:
            filler = SampleStaticFetcher().fetch_items()
            for item in filler:
                record = self._build_record(item)
                if record:
                    aggregated.append(record)
            aggregated = self._normalize_items(aggregated)
        aggregated = self._ensure_minimum(aggregated, min_items)

        return {
            "generated_at": datetime.now().isoformat(),
            "item_count": len(aggregated),
            "items": aggregated,
            "sources": [fetcher.name for fetcher in self.fetchers],
        }

    def _build_record(self, item: Dict) -> Optional[Dict]:
        raw_title = item.get("title", "无标题").strip()
        content = item.get("content") or item.get("summary") or ""
        summary = item.get("summary") or self._summarize_text(content)
        category = item.get("category") or self._classify_category(
            raw_title, content, item.get("category_hint")
        )
        title = self._generate_title(raw_title, summary, category)
        popularity = item.get("popularity", 1)
        score = item.get("score") or self._score_item(summary, category, popularity)

        if not summary:
            summary = raw_title
        if len(summary) < 10 and len(content) < 80:
            return None

        return {
            "title": title,
            "summary": summary or raw_title,
            "category": category,
            "source": item.get("source", "未知"),
            "published_at": item.get("published_at", datetime.now().isoformat()),
            "url": item.get("url", ""),
            "score": score,
        }

    def _normalize_items(self, items: List[Dict]) -> List[Dict]:
        seen = set()
        normalized = []
        for item in items:
            key = (item.get("title"), item.get("source"))
            if key in seen:
                continue
            seen.add(key)
            normalized.append(
                {
                    "title": item.get("title", "无标题"),
                    "summary": item.get("summary", "（暂无摘要）"),
                    "category": item.get("category", "其他"),
                    "source": item.get("source", "未知"),
                    "published_at": item.get("published_at", ""),
                    "url": item.get("url", ""),
                    "score": item.get("score", 0.0),
                }
            )
        normalized.sort(key=lambda x: x.get("score", 0), reverse=True)
        return normalized

    def _ensure_minimum(self, items: List[Dict], min_items: int) -> List[Dict]:
        if len(items) >= min_items:
            return items
        remaining = min_items - len(items)
        now = datetime.now().isoformat()
        for idx in range(remaining):
            items.append(
                {
                    "title": f"占位资讯 {idx + 1}",
                    "summary": "等待真实抓取器补充，此条为占位内容。",
                    "category": "临时占位",
                    "source": "系统占位",
                    "published_at": now,
                    "url": "",
                    "score": 0.0,
                }
            )
        return items

    def _summarize_text(self, content: str, max_sentences: int = 2) -> str:
        if not content:
            return ""
        noise_phrases = [
            "扫码关注",
            "登录",
            "注册",
            "礼包",
            "礼包码",
            "二维码",
            "公众号",
            "打开游戏",
            "点击进入",
            "关注我们",
            "下载客户端",
        ]
        highlight_keywords = [
            "维护",
            "更新",
            "公告",
            "奖励",
            "物价",
            "涨",
            "跌",
            "攻略",
            "阵容",
            "打法",
            "活动",
            "福利",
            "优化",
        ]
        sentences = re.split(r"[。！？!?]", content)
        cleaned: List[str] = []
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 10:
                continue
            if any(noise in sentence for noise in noise_phrases):
                continue
            cleaned.append(sentence)
        if not cleaned:
            return content[:120]

        scored: List[tuple[int, str]] = []
        for sentence in cleaned:
            score = len(sentence)
            for kw in highlight_keywords:
                if kw in sentence:
                    score += 40
            scored.append((score, sentence))

        top_sentences = [s for _, s in sorted(scored, reverse=True)[:max_sentences]]
        summary = "。".join(top_sentences)
        if len(summary) > 200:
            summary = summary[:200] + "……"
        if not summary.endswith("。"):
            summary += "。"
        return summary

    def _classify_category(self, title: str, content: str, hint: Optional[str]) -> str:
        if hint:
            mapping = {
                "公告": "维护公告解读",
                "新闻": "维护公告解读",
                "物价": "物价变动分析",
                "攻略": "高手攻略",
            }
            if hint in mapping:
                return mapping[hint]
        text = f"{title} {content}".lower()
        if any(keyword in text for keyword in ["维护", "公告", "停机", "更新"]):
            return "维护公告解读"
        if any(keyword in text for keyword in ["物价", "价格", "行情", "涨", "跌"]):
            return "物价变动分析"
        if any(keyword in text for keyword in ["攻略", "打法", "技巧", "心得", "阵容"]):
            return "高手攻略"
        return "综合资讯"

    def _generate_title(self, original_title: str, summary: str, category: str) -> str:
        original_title = original_title.strip()
        if not original_title:
            return summary[:20]
        prefix_map = {
            "维护公告解读": "维护解读",
            "物价变动分析": "物价观察",
            "高手攻略": "攻略精选",
        }
        prefix = prefix_map.get(category)
        if prefix and not original_title.startswith(prefix):
            return f"{prefix}｜{original_title}"
        return original_title

    def _score_item(self, summary: str, category: str, popularity: float) -> float:
        base = len(summary)
        bonus = {
            "维护公告解读": 1.2,
            "物价变动分析": 1.1,
            "高手攻略": 1.0,
        }.get(category, 0.9)
        popularity_factor = 1 + max(popularity, 1) * 0.05
        return base * bonus * popularity_factor


class BrowserPage(QWebEnginePage):
    """自定义页面，拦截新窗口请求并在当前视图打开"""

    def __init__(self, profile=None, parent=None):
        if profile:
            super().__init__(profile, parent)
        else:
            super().__init__(parent)

    def createWindow(self, _type):
        return self


class DownloadTab(QWidget):
    """内嵌浏览器 + 常用网站页"""

    def __init__(self, manager: NovelManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.fetcher = create_fetcher("local")
        self.download_cache_dir = self.manager.get_download_cache_path()

        self.default_sites = [
            {"name": "起点小说", "url": "https://www.qidian.com/"},
            {"name": "鸠摩小说", "url": "https://www.jiumosoushu.cc/"},
            {"name": "书旗小说", "url": "https://ognv.shuqi.com/"},
            {"name": "微信读书", "url": "https://weread.qq.com/"},
            {"name": "QQ阅读小说", "url": "https://book.qq.com/"},
        ]
        self.custom_sites: List[Dict] = []
        self._load_custom_sites()
        
        # 初始化历史记录
        self.history_list: List[Dict] = []
        self._load_history()
        
        # 确保缓存目录存在
        os.makedirs(CACHE_DIR, exist_ok=True)

        self._build_ui()
        self._setup_download_monitor()

    # ---------- UI ----------
    def _build_ui(self):
        main_layout = QVBoxLayout(self)

        tip_label = QLabel(
            "提示：在下面的浏览器中打开小说网站，下载 TXT 文件并保存到程序的下载缓存目录。\n"
            f"当前下载缓存目录：{self.download_cache_dir}"
        )
        tip_label.setWordWrap(True)
        main_layout.addWidget(tip_label)

        # 地址栏 + 控制按钮
        addr_layout = QHBoxLayout()
        self.url_edit = QLineEdit("https://www.qidian.com/")
        self.go_button = QPushButton("前往")
        self.back_button = QPushButton("后退")
        self.forward_button = QPushButton("前进")
        self.reload_button = QPushButton("刷新")
        self.open_dir_button = QPushButton("打开下载目录")

        addr_layout.addWidget(QLabel("地址："))
        addr_layout.addWidget(self.url_edit)
        addr_layout.addWidget(self.go_button)
        addr_layout.addWidget(self.back_button)
        addr_layout.addWidget(self.forward_button)
        addr_layout.addWidget(self.reload_button)
        addr_layout.addWidget(self.open_dir_button)

        main_layout.addLayout(addr_layout)

        # 设置浏览器缓存和Cookie持久化
        from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
        profile = QWebEngineProfile.defaultProfile()
        profile.setPersistentStoragePath(CACHE_DIR)
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.AllowPersistentCookies)
        
        # 设置User Agent，使用最新Chrome的User Agent以支持更多视频格式
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        profile.setHttpUserAgent(user_agent)
        
        # 浏览器
        self.web_view = QWebEngineView(self)
        page = BrowserPage(profile, self.web_view)
        self.web_view.setPage(page)
        
        # 启用硬件加速和其他设置以支持视频播放
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ErrorPageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.FocusOnNavigationEnabled, True)
        # 尝试启用更多视频相关设置
        try:
            # 这些属性可能在某些PyQt6版本中不存在，使用try-except保护
            settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
            settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        except:
            pass
        
        self.web_view.load(QUrl(self.url_edit.text()))
        main_layout.addWidget(self.web_view, stretch=1)
        self.web_view.page().profile().downloadRequested.connect(self.on_download_requested)

        # 常用网站区域
        sites_group = QGroupBox("常用网站")
        sites_layout = QVBoxLayout()
        fixed_row = QHBoxLayout()
        for site in self.default_sites:
            btn = QPushButton(site["name"])
            btn.clicked.connect(lambda _, u=site["url"]: self.open_url(u))
            fixed_row.addWidget(btn)
        fixed_row.addStretch()
        sites_layout.addLayout(fixed_row)

        # 自定义网站
        custom_form = QFormLayout()
        self.custom_name_edit = QLineEdit()
        self.custom_url_edit = QLineEdit()
        custom_form.addRow("名称：", self.custom_name_edit)
        custom_form.addRow("网址：", self.custom_url_edit)
        sites_layout.addLayout(custom_form)

        btn_row = QHBoxLayout()
        self.add_site_button = QPushButton("添加到常用")
        self.open_site_button = QPushButton("打开选中")
        self.delete_site_button = QPushButton("删除选中")
        btn_row.addWidget(self.add_site_button)
        btn_row.addWidget(self.open_site_button)
        btn_row.addWidget(self.delete_site_button)
        btn_row.addStretch()
        sites_layout.addLayout(btn_row)

        self.custom_sites_combo = QComboBox()
        sites_layout.addWidget(self.custom_sites_combo)

        sites_group.setLayout(sites_layout)
        main_layout.addWidget(sites_group)
        
        # 历史记录区域
        history_group = QGroupBox("访问历史")
        history_layout = QVBoxLayout()
        
        history_buttons = QHBoxLayout()
        self.clear_history_button = QPushButton("清空历史")
        self.refresh_history_button = QPushButton("刷新")
        history_buttons.addWidget(self.clear_history_button)
        history_buttons.addWidget(self.refresh_history_button)
        history_buttons.addStretch()
        history_layout.addLayout(history_buttons)
        
        self.history_list_widget = QListWidget()
        self.history_list_widget.setMaximumHeight(120)
        self.history_list_widget.itemDoubleClicked.connect(self.on_history_item_double_clicked)
        history_layout.addWidget(self.history_list_widget)
        
        history_group.setLayout(history_layout)
        main_layout.addWidget(history_group)
        
        self._refresh_history_list()

        # 下载进度区域
        download_group = QGroupBox("下载进度")
        download_layout = QVBoxLayout()
        
        self.download_status_label = QLabel("")
        self.download_status_label.setWordWrap(True)
        download_layout.addWidget(self.download_status_label)
        
        self.download_progress_bar = QProgressBar()
        self.download_progress_bar.setVisible(False)
        download_layout.addWidget(self.download_progress_bar)
        
        self.download_speed_label = QLabel("")
        download_layout.addWidget(self.download_speed_label)
        
        download_buttons = QHBoxLayout()
        self.download_pause_button = QPushButton("暂停")
        self.download_pause_button.setEnabled(False)
        self.download_cancel_button = QPushButton("取消")
        self.download_cancel_button.setEnabled(False)
        download_buttons.addWidget(self.download_pause_button)
        download_buttons.addWidget(self.download_cancel_button)
        download_buttons.addStretch()
        download_layout.addLayout(download_buttons)
        
        download_group.setLayout(download_layout)
        main_layout.addWidget(download_group)

        self._refresh_custom_sites_combo()
        
        # 当前下载对象
        self.current_download: QWebEngineDownloadRequest = None
        self.download_start_time = None
        self.last_received_bytes = 0
        self.last_update_time = None

        # 信号连接
        self.go_button.clicked.connect(self.on_go_clicked)
        self.url_edit.returnPressed.connect(self.on_go_clicked)  # 回车键前往
        self.back_button.clicked.connect(self.on_back_clicked)
        self.forward_button.clicked.connect(self.on_forward_clicked)
        self.reload_button.clicked.connect(self.on_reload_clicked)
        self.open_dir_button.clicked.connect(self.on_open_dir_clicked)
        self.add_site_button.clicked.connect(self.on_add_site)
        self.delete_site_button.clicked.connect(self.on_delete_site)
        self.open_site_button.clicked.connect(self.on_open_site)
        self.web_view.urlChanged.connect(self.on_url_changed)
        self.download_pause_button.clicked.connect(self.on_pause_download)
        self.download_cancel_button.clicked.connect(self.on_cancel_download)
        self.clear_history_button.clicked.connect(self.on_clear_history)
        self.refresh_history_button.clicked.connect(self._refresh_history_list)

    # ---------- 历史记录管理 ----------
    def _load_history(self):
        """加载历史记录"""
        if not os.path.exists(HISTORY_FILE):
            self.history_list = []
            return
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.history_list = data.get("history", [])
            # 限制历史记录数量，只保留最近200条
            if len(self.history_list) > 200:
                self.history_list = self.history_list[-200:]
        except Exception:
            self.history_list = []
    
    def _save_history(self):
        """保存历史记录"""
        try:
            os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
            data = {"history": self.history_list}
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def _add_to_history(self, url: str, title: str = ""):
        """添加到历史记录"""
        url = url.strip()
        if not url:
            return
        
        # 检查是否已存在（避免重复）
        for item in self.history_list:
            if item.get("url") == url:
                # 更新时间和标题
                item["time"] = time.time()
                item["title"] = title or url
                self._save_history()
                self._refresh_history_list()
                return
        
        # 添加新记录
        self.history_list.append({
            "url": url,
            "title": title or url,
            "time": time.time()
        })
        
        # 限制数量
        if len(self.history_list) > 200:
            self.history_list = self.history_list[-200:]
        
        self._save_history()
        self._refresh_history_list()
    
    def _refresh_history_list(self):
        """刷新历史记录列表显示"""
        self.history_list_widget.clear()
        # 按时间倒序显示
        sorted_history = sorted(self.history_list, key=lambda x: x.get("time", 0), reverse=True)
        for item in sorted_history[:50]:  # 只显示最近50条
            url = item.get("url", "")
            title = item.get("title", url)
            time_str = ""
            if "time" in item:
                try:
                    from datetime import datetime
                    dt = datetime.fromtimestamp(item["time"])
                    time_str = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    pass
            display_text = f"{title} - {time_str}" if time_str else title
            self.history_list_widget.addItem(display_text)
    
    @pyqtSlot(QListWidgetItem)
    def on_history_item_double_clicked(self, item: QListWidgetItem):
        """双击历史记录项，打开URL"""
        index = self.history_list_widget.row(item)
        sorted_history = sorted(self.history_list, key=lambda x: x.get("time", 0), reverse=True)
        if 0 <= index < len(sorted_history):
            url = sorted_history[index].get("url", "")
            if url:
                self.open_url(url)
    
    @pyqtSlot()
    def on_clear_history(self):
        """清空历史记录"""
        if QMessageBox.question(self, "确认", "确定要清空所有历史记录吗？") == QMessageBox.StandardButton.Yes:
            self.history_list = []
            self._save_history()
            self._refresh_history_list()
    
    # ---------- 自定义站点持久化 ----------
    def _load_custom_sites(self):
        if not os.path.exists(CONFIG_FILE):
            self.custom_sites = []
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.custom_sites = data.get("custom_sites", [])
        except Exception:
            self.custom_sites = []

    def _save_custom_sites(self):
        data = {"custom_sites": self.custom_sites}
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _refresh_custom_sites_combo(self):
        self.custom_sites_combo.clear()
        for site in self.custom_sites:
            self.custom_sites_combo.addItem(f"{site.get('name', '')} - {site.get('url', '')}")

    # ---------- 浏览器控制 ----------
    @pyqtSlot()
    def on_go_clicked(self):
        self.open_url(self.url_edit.text())

    def open_url(self, url: str):
        url = url.strip()
        if not url:
            QMessageBox.warning(self, "提示", "请输入网址")
            return
        if not (url.startswith("http://") or url.startswith("https://")):
            url = "https://" + url
        self.url_edit.setText(url)
        self.web_view.load(QUrl(url))

    @pyqtSlot(QUrl)
    def on_url_changed(self, qurl: QUrl):
        url_str = qurl.toString()
        self.url_edit.setText(url_str)
        self.back_button.setEnabled(self.web_view.history().canGoBack())
        self.forward_button.setEnabled(self.web_view.history().canGoForward())
        
        # 添加到历史记录
        if url_str and not url_str.startswith("about:blank"):
            # 获取页面标题（异步，延迟添加到历史记录）
            def get_title():
                try:
                    title = self.web_view.title()
                    if title:
                        self._add_to_history(url_str, title)
                    else:
                        self._add_to_history(url_str)
                except:
                    self._add_to_history(url_str)
            # 延迟获取标题，等待页面加载
            QTimer.singleShot(1000, get_title)

    @pyqtSlot()
    def on_open_dir_clicked(self):
        if not os.path.exists(self.download_cache_dir):
            os.makedirs(self.download_cache_dir, exist_ok=True)
        os.startfile(self.download_cache_dir)

    @pyqtSlot()
    def on_add_site(self):
        name = self.custom_name_edit.text().strip()
        url = self.custom_url_edit.text().strip()
        if not name or not url:
            QMessageBox.warning(self, "提示", "请填写名称和网址")
            return
        if not (url.startswith("http://") or url.startswith("https://")):
            url = "https://" + url
        self.custom_sites.append({"name": name, "url": url})
        self._save_custom_sites()
        self._refresh_custom_sites_combo()
        self.custom_name_edit.clear()
        self.custom_url_edit.clear()

    @pyqtSlot()
    def on_delete_site(self):
        idx = self.custom_sites_combo.currentIndex()
        if idx < 0 or idx >= len(self.custom_sites):
            QMessageBox.warning(self, "提示", "请选择要删除的网站")
            return
        if QMessageBox.question(self, "确认", "确定删除选中的网站吗？") != QMessageBox.StandardButton.Yes:
            return
        self.custom_sites.pop(idx)
        self._save_custom_sites()
        self._refresh_custom_sites_combo()

    @pyqtSlot()
    def on_open_site(self):
        idx = self.custom_sites_combo.currentIndex()
        if idx < 0 or idx >= len(self.custom_sites):
            QMessageBox.warning(self, "提示", "请选择要打开的网站")
            return
        site = self.custom_sites[idx]
        self.open_url(site.get("url", ""))

    @pyqtSlot()
    def on_back_clicked(self):
        self.web_view.back()
        history = self.web_view.history()
        current = history.currentItem()
        if current:
            self.url_edit.setText(current.url().toString())

    @pyqtSlot()
    def on_forward_clicked(self):
        self.web_view.forward()
        history = self.web_view.history()
        current = history.currentItem()
        if current:
            self.url_edit.setText(current.url().toString())

    @pyqtSlot()
    def on_reload_clicked(self):
        self.web_view.reload()
        current = self.web_view.history().currentItem()
        if current:
            self.url_edit.setText(current.url().toString())

    def on_download_requested(self, download: QWebEngineDownloadRequest):
        filename = download.downloadFileName() or f"download_{int(time.time())}"
        base_name = os.path.basename(filename)
        target_path = os.path.join(self.download_cache_dir, base_name)
        root, ext = os.path.splitext(target_path)
        counter = 1
        while os.path.exists(target_path):
            target_path = f"{root}_{counter}{ext}"
            counter += 1
        directory = os.path.dirname(target_path)
        os.makedirs(directory, exist_ok=True)
        download.setDownloadDirectory(directory)
        download.setDownloadFileName(os.path.basename(target_path))
        download.accept()
        
        # 保存当前下载对象
        self.current_download = download
        self.download_start_time = time.time()
        self.last_received_bytes = 0
        self.last_update_time = time.time()
        
        # 显示进度条
        self.download_progress_bar.setVisible(True)
        self.download_progress_bar.setValue(0)
        self.download_status_label.setText(f"正在下载：{os.path.basename(target_path)}")
        self.download_speed_label.setText("")
        self.download_pause_button.setEnabled(True)
        self.download_cancel_button.setEnabled(True)
        self.download_pause_button.setText("暂停")
        
        # 连接下载信号
        download.receivedBytesChanged.connect(self.on_download_progress)
        download.totalBytesChanged.connect(self.on_download_progress)
        download.stateChanged.connect(self.on_download_state_changed)
        download.isPausedChanged.connect(self.on_download_pause_changed)
    
    @pyqtSlot()
    def on_download_progress(self):
        """更新下载进度"""
        if not self.current_download:
            return
        
        received = self.current_download.receivedBytes()
        total = self.current_download.totalBytes()
        
        if total > 0:
            percent = int(received * 100 / total)
            self.download_progress_bar.setMaximum(100)
            self.download_progress_bar.setValue(percent)
            
            # 计算下载速度和剩余时间
            current_time = time.time()
            if self.last_update_time:
                elapsed = current_time - self.last_update_time
                if elapsed > 0:
                    bytes_diff = received - self.last_received_bytes
                    speed = bytes_diff / elapsed  # 字节/秒
                    
                    # 格式化速度
                    if speed < 1024:
                        speed_str = f"{speed:.1f} B/s"
                    elif speed < 1024 * 1024:
                        speed_str = f"{speed / 1024:.1f} KB/s"
                    else:
                        speed_str = f"{speed / (1024 * 1024):.1f} MB/s"
                    
                    # 计算剩余时间
                    remaining_bytes = total - received
                    if speed > 0:
                        remaining_seconds = remaining_bytes / speed
                        if remaining_seconds < 60:
                            time_str = f"{int(remaining_seconds)}秒"
                        elif remaining_seconds < 3600:
                            time_str = f"{int(remaining_seconds / 60)}分{int(remaining_seconds % 60)}秒"
                        else:
                            hours = int(remaining_seconds / 3600)
                            minutes = int((remaining_seconds % 3600) / 60)
                            time_str = f"{hours}小时{minutes}分"
                    else:
                        time_str = "计算中..."
                    
                    self.download_speed_label.setText(f"速度：{speed_str} | 剩余时间：{time_str}")
            
            self.last_received_bytes = received
            self.last_update_time = current_time
        else:
            # 总大小未知
            if received > 0:
                self.download_progress_bar.setMaximum(0)  # 不确定进度
                self.download_speed_label.setText(f"已下载：{self._format_bytes(received)}")
    
    def _format_bytes(self, bytes_count: int) -> str:
        """格式化字节数"""
        if bytes_count < 1024:
            return f"{bytes_count} B"
        elif bytes_count < 1024 * 1024:
            return f"{bytes_count / 1024:.1f} KB"
        else:
            return f"{bytes_count / (1024 * 1024):.1f} MB"
    
    @pyqtSlot()
    def on_download_state_changed(self):
        """下载状态改变"""
        if not self.current_download:
            return
        
        state = self.current_download.state()
        if state == QWebEngineDownloadRequest.DownloadState.DownloadCompleted:
            self.download_status_label.setText(f"下载完成：{os.path.basename(self.current_download.downloadFileName())}")
            self.download_progress_bar.setValue(100)
            self.download_pause_button.setEnabled(False)
            self.download_cancel_button.setEnabled(False)
            self.download_speed_label.setText("")
            # 延迟隐藏进度条
            QTimer.singleShot(3000, lambda: self.download_progress_bar.setVisible(False))
            self.current_download = None
        elif state == QWebEngineDownloadRequest.DownloadState.DownloadCancelled:
            self.download_status_label.setText("下载已取消")
            self.download_progress_bar.setVisible(False)
            self.download_pause_button.setEnabled(False)
            self.download_cancel_button.setEnabled(False)
            self.download_speed_label.setText("")
            self.current_download = None
        elif state == QWebEngineDownloadRequest.DownloadState.DownloadInterrupted:
            self.download_status_label.setText("下载已中断")
            self.download_speed_label.setText("")
    
    @pyqtSlot()
    def on_download_pause_changed(self):
        """暂停状态改变"""
        if not self.current_download:
            return
        
        if self.current_download.isPaused():
            self.download_pause_button.setText("继续")
            self.download_status_label.setText(f"已暂停：{os.path.basename(self.current_download.downloadFileName())}")
        else:
            self.download_pause_button.setText("暂停")
            self.download_status_label.setText(f"正在下载：{os.path.basename(self.current_download.downloadFileName())}")
    
    @pyqtSlot()
    def on_pause_download(self):
        """暂停/继续下载"""
        if not self.current_download:
            return
        
        if self.current_download.isPaused():
            self.current_download.resume()
        else:
            self.current_download.pause()
    
    @pyqtSlot()
    def on_cancel_download(self):
        """取消下载"""
        if not self.current_download:
            return
        
        if QMessageBox.question(self, "确认", "确定要取消下载吗？") == QMessageBox.StandardButton.Yes:
            self.current_download.cancel()
            self.current_download = None
            self.download_progress_bar.setVisible(False)
            self.download_pause_button.setEnabled(False)
            self.download_cancel_button.setEnabled(False)
            self.download_speed_label.setText("")

    # ---------- 下载监控与自动导入 ----------
    def _setup_download_monitor(self):
        self.observed_files: Dict[str, Dict] = {}
        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(self._scan_download_dir)
        self.monitor_timer.start(2000)

    def _scan_download_dir(self):
        """周期检测 download_cache 目录中文件，稳定后自动导入"""
        try:
            if not os.path.exists(self.download_cache_dir):
                os.makedirs(self.download_cache_dir, exist_ok=True)

            current_paths = set()
            for entry in os.scandir(self.download_cache_dir):
                if not entry.is_file() or not entry.name.lower().endswith(".txt"):
                    continue
                current_paths.add(entry.path)
                stat = entry.stat()
                signature = (stat.st_size, stat.st_mtime)
                prev = self.observed_files.get(entry.path)
                if prev and prev["signature"] == signature:
                    prev["stable_cycles"] += 1
                else:
                    self.observed_files[entry.path] = {
                        "signature": signature,
                        "stable_cycles": 0,
                    }
                    continue

                if prev["stable_cycles"] >= 1:
                    if not self.manager.is_download_processed(
                        entry.path, stat.st_size, stat.st_mtime
                    ):
                        self._import_novel_file(entry.path, stat.st_size, stat.st_mtime)

            # 清理不存在的文件
            for tracked in list(self.observed_files.keys()):
                if tracked not in current_paths:
                    self.observed_files.pop(tracked, None)
        except Exception as exc:
            print(f"扫描下载目录出错: {exc}")

    def _import_novel_file(self, file_path: str, size: int, mtime: float):
        if not os.path.exists(file_path):
            return
        try:
            info = self.fetcher.get_novel_info(file_path)
            if not info:
                info = {
                    "title": os.path.basename(file_path),
                    "author": "下载文件",
                    "description": "",
                    "url": file_path,
                    "source": "download_cache",
                }
            else:
                info["url"] = file_path
                info["source"] = "download_cache"
            novel_id = self.manager.add_novel(info)
            self.manager.mark_download_processed(file_path, size, mtime)
            # 让主窗口刷新列表
            parent = self.parent()
            if parent and hasattr(parent, "on_novel_imported"):
                parent.on_novel_imported(novel_id, info)
        except Exception as exc:
            QMessageBox.critical(self, "错误", f"自动导入小说失败：{exc}")


class NovelListTab(QWidget):
    """小说列表 + 阅读页（简化版）"""

    tts_highlight_signal = pyqtSignal(int, int)
    tts_status_signal = pyqtSignal(str)
    tts_finish_signal = pyqtSignal(bool, str)
    test_finish_signal = pyqtSignal(bool, str)

    def __init__(self, manager: NovelManager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.fetcher = create_fetcher("local")
        self.tts_manager = TTSManager()
        self.tts_manager.set_word_callback(self.on_tts_word)

        self.current_novel: Dict | None = None
        self.current_chapters: List[Dict] = []
        self.current_chapter_index: int = 0
        self.tts_active = False
        self.search_results: List[Dict] = []
        self.current_search_index = -1
        self._tts_extra: List = []

        self._build_ui()
        self.refresh_novel_list()

        self.tts_highlight_signal.connect(self.highlight_tts_range)
        self.tts_status_signal.connect(self.update_status_label)
        self.tts_finish_signal.connect(self.handle_tts_finished)
        self.test_finish_signal.connect(self.handle_test_voice_finished)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # 左侧列表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        top_btn_row = QHBoxLayout()
        self.add_button = QPushButton("添加小说")
        self.delete_button = QPushButton("删除小说")
        top_btn_row.addWidget(self.add_button)
        top_btn_row.addWidget(self.delete_button)
        top_btn_row.addStretch()
        left_layout.addLayout(top_btn_row)

        self.list_widget = QListWidget()
        left_layout.addWidget(self.list_widget)

        splitter.addWidget(left_widget)

        # 右侧阅读区
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        self.title_label = QLabel("请选择一本小说")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        right_layout.addWidget(self.title_label)

        chapter_row = QHBoxLayout()
        chapter_row.addWidget(QLabel("章节："))
        self.chapter_combo = QComboBox()
        chapter_row.addWidget(self.chapter_combo, stretch=1)
        self.prev_button = QPushButton("上一章")
        self.next_button = QPushButton("下一章")
        chapter_row.addWidget(self.prev_button)
        chapter_row.addWidget(self.next_button)
        right_layout.addLayout(chapter_row)

        self.content_edit = QTextEdit()
        self.content_edit.setReadOnly(True)
        right_layout.addWidget(self.content_edit, stretch=1)

        # 搜索区域
        search_group = QGroupBox("搜索")
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_button = QPushButton("搜索")
        self.prev_result_button = QPushButton("上一个")
        self.next_result_button = QPushButton("下一个")
        self.search_status_label = QLabel("")
        search_layout.addWidget(QLabel("关键词："))
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_button)
        search_layout.addWidget(self.prev_result_button)
        search_layout.addWidget(self.next_result_button)
        search_layout.addWidget(self.search_status_label)
        search_group.setLayout(search_layout)
        right_layout.addWidget(search_group)

        # 朗读区域
        tts_group = QGroupBox("语音朗读")
        tts_layout = QHBoxLayout()
        self.voice_combo = QComboBox()
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(50, 300)
        self.speed_slider.setValue(150)
        self.speed_value_label = QLabel("150")
        self.tts_test_button = QPushButton("试听声音")
        self.tts_start_button = QPushButton("开始朗读")
        self.tts_stop_button = QPushButton("停止")
        tts_layout.addWidget(QLabel("语音："))
        tts_layout.addWidget(self.voice_combo, stretch=1)
        tts_layout.addWidget(QLabel("语速："))
        tts_layout.addWidget(self.speed_slider)
        tts_layout.addWidget(self.speed_value_label)
        tts_layout.addWidget(self.tts_test_button)
        tts_layout.addWidget(self.tts_start_button)
        tts_layout.addWidget(self.tts_stop_button)
        tts_group.setLayout(tts_layout)
        right_layout.addWidget(tts_group)

        self.status_label = QLabel("就绪")
        right_layout.addWidget(self.status_label)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(1, 2)

        # 信号
        self.add_button.clicked.connect(self.on_add_novel)
        self.delete_button.clicked.connect(self.on_delete_novel)
        self.list_widget.itemDoubleClicked.connect(self.on_open_novel)
        self.chapter_combo.currentIndexChanged.connect(self.on_chapter_changed)
        self.prev_button.clicked.connect(self.on_prev_chapter)
        self.next_button.clicked.connect(self.on_next_chapter)
        self.search_button.clicked.connect(self.on_search_clicked)
        self.prev_result_button.clicked.connect(self.on_prev_result)
        self.next_result_button.clicked.connect(self.on_next_result)
        self.search_input.returnPressed.connect(self.on_search_clicked)
        self.search_input.textChanged.connect(self.clear_search_highlight)
        self.speed_slider.valueChanged.connect(self.on_speed_changed)
        self.tts_test_button.clicked.connect(self.on_test_voice)
        self.tts_start_button.clicked.connect(self.on_start_tts)
        self.tts_stop_button.clicked.connect(self.on_stop_tts)
        self.voice_combo.currentIndexChanged.connect(self.on_voice_changed)

        self._populate_voices()
        self.update_tts_controls()

    # ---------- 列表与基本操作 ----------
    def refresh_novel_list(self):
        self.list_widget.clear()
        for novel in self.manager.get_all_novels():
            title = novel.get("title", "未知标题")
            author = novel.get("author", "未知作者")
            item = QListWidgetItem(f"{title} - {author}")
            item.setData(Qt.ItemDataRole.UserRole, novel.get("id"))
            self.list_widget.addItem(item)

    @pyqtSlot()
    def on_add_novel(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择小说文件", "", "文本文件 (*.txt);;所有文件 (*)"
        )
        if not file_path:
            return
        try:
            info = self.fetcher.get_novel_info(file_path)
            if not info:
                info = {
                    "title": os.path.basename(file_path),
                    "author": "本地文件",
                    "description": "",
                    "url": file_path,
                    "source": "local",
                }
            novel_id = self.manager.add_novel(info)
            self.refresh_novel_list()
            self._select_novel_by_id(novel_id)
            QMessageBox.information(self, "成功", f"已添加小说：{info['title']}")
        except Exception as exc:
            QMessageBox.critical(self, "错误", f"添加小说失败：{exc}")

    @pyqtSlot()
    def on_delete_novel(self):
        item = self.list_widget.currentItem()
        if not item:
            QMessageBox.warning(self, "提示", "请先选择要删除的小说")
            return
        if QMessageBox.question(self, "确认", "确定删除选中的小说吗？") != QMessageBox.StandardButton.Yes:
            return
        novel_id = item.data(Qt.ItemDataRole.UserRole)
        self.manager.delete_novel(novel_id)
        self.refresh_novel_list()
        if self.current_novel and self.current_novel.get("id") == novel_id:
            self.current_novel = None
            self.current_chapters = []
            self.content_edit.clear()
            self.title_label.setText("请选择一本小说")

    def _select_novel_by_id(self, novel_id: str):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == novel_id:
                self.list_widget.setCurrentRow(i)
                self.on_open_novel(item)
                break

    @pyqtSlot(QListWidgetItem)
    def on_open_novel(self, item: QListWidgetItem):
        novel_id = item.data(Qt.ItemDataRole.UserRole)
        novel = self.manager.get_novel(novel_id)
        if not novel:
            return
        self.load_novel(novel)

    # ---------- 阅读逻辑 ----------
    def load_novel(self, novel: Dict):
        self.current_novel = novel
        self.title_label.setText(novel.get("title", "未知标题"))

        url = novel.get("url", "")
        self.current_chapters = self.fetcher.get_chapter_list(url)
        self.chapter_combo.blockSignals(True)
        self.chapter_combo.clear()
        for ch in self.current_chapters:
            self.chapter_combo.addItem(ch.get("title", "无标题"))
        self.chapter_combo.blockSignals(False)

        idx = novel.get("current_chapter", 0)
        if 0 <= idx < len(self.current_chapters):
            self.current_chapter_index = idx
        else:
            self.current_chapter_index = 0

        if self.current_chapters:
            self.chapter_combo.setCurrentIndex(self.current_chapter_index)
            self.load_chapter_content()

    @pyqtSlot(int)
    def on_chapter_changed(self, index: int):
        if index < 0 or index >= len(self.current_chapters):
            return
        self.current_chapter_index = index
        self.load_chapter_content()

    def load_chapter_content(self):
        if not self.current_novel or not self.current_chapters:
            return
        chapter = self.current_chapters[self.current_chapter_index]
        content = self.fetcher.get_chapter_content(chapter.get("url", ""))
        self.content_edit.setPlainText(content)
        self.clear_search_highlight()
        self.stop_tts_internal()
        # 更新阅读进度
        self.manager.update_reading_progress(
            self.current_novel.get("id"), self.current_chapter_index
        )

    @pyqtSlot()
    def on_prev_chapter(self):
        if self.current_chapter_index > 0:
            self.current_chapter_index -= 1
            self.chapter_combo.setCurrentIndex(self.current_chapter_index)

    @pyqtSlot()
    def on_next_chapter(self):
        if self.current_chapter_index + 1 < len(self.current_chapters):
            self.current_chapter_index += 1
            self.chapter_combo.setCurrentIndex(self.current_chapter_index)

    # ---------- 搜索功能 ----------
    @pyqtSlot()
    def on_search_clicked(self):
        keyword = self.search_input.text().strip()
        if not keyword:
            QMessageBox.warning(self, "提示", "请输入搜索关键词")
            return
        text = self.content_edit.toPlainText()
        self.search_results = []
        start = 0
        lower_text = text.lower()
        lower_keyword = keyword.lower()
        while True:
            idx = lower_text.find(lower_keyword, start)
            if idx == -1:
                break
            self.search_results.append({"start": idx, "end": idx + len(keyword)})
            start = idx + len(keyword)
        if not self.search_results:
            self.current_search_index = -1
            self.apply_search_highlight()
            QMessageBox.information(self, "提示", "未找到匹配项")
            self.search_status_label.setText("0/0")
            return
        self.current_search_index = 0
        self.apply_search_highlight()
        self.search_status_label.setText(f"{self.current_search_index + 1}/{len(self.search_results)}")

    @pyqtSlot()
    def on_prev_result(self):
        if not self.search_results:
            self.on_search_clicked()
            return
        self.current_search_index = (self.current_search_index - 1) % len(self.search_results)
        self.apply_search_highlight()
        self.search_status_label.setText(f"{self.current_search_index + 1}/{len(self.search_results)}")

    @pyqtSlot()
    def on_next_result(self):
        if not self.search_results:
            self.on_search_clicked()
            return
        self.current_search_index = (self.current_search_index + 1) % len(self.search_results)
        self.apply_search_highlight()
        self.search_status_label.setText(f"{self.current_search_index + 1}/{len(self.search_results)}")

    def apply_search_highlight(self):
        extra = []
        format_search = QTextEdit.ExtraSelection()
        fmt = QTextCharFormat()
        fmt.setBackground(Qt.GlobalColor.yellow)
        format_search.format = fmt
        if self.search_results and 0 <= self.current_search_index < len(self.search_results):
            sel = self.search_results[self.current_search_index]
            tmp_cursor = self.content_edit.textCursor()
            tmp_cursor.setPosition(sel["start"])
            tmp_cursor.setPosition(sel["end"], QTextCursor.MoveMode.KeepAnchor)
            format_search.cursor = tmp_cursor
            extra.append(format_search)
            self.content_edit.setTextCursor(tmp_cursor)
            self.content_edit.centerCursor()
        # 合并朗读高亮
        extra.extend(getattr(self, "_tts_extra", []))
        self.content_edit.setExtraSelections(extra)

    @pyqtSlot(str)
    def update_status_label(self, text: str):
        self.status_label.setText(text)

    def clear_search_highlight(self):
        self.search_results = []
        self.current_search_index = -1
        self.search_status_label.setText("")
        self.apply_search_highlight()

    # ---------- 朗读功能 ----------
    def _populate_voices(self):
        try:
            voices = self.tts_manager.get_available_voice_names()
        except Exception:
            voices = []
        self.voice_combo.clear()
        if voices:
            self.voice_combo.addItems(voices)
            self.voice_combo.setCurrentIndex(0)
        else:
            self.voice_combo.addItem("无可用语音")

    def update_tts_controls(self):
        available = self.tts_manager.is_available()
        self.tts_test_button.setEnabled(available)
        self.tts_start_button.setEnabled(available and not self.tts_active)
        self.tts_stop_button.setEnabled(available and self.tts_active)

    @pyqtSlot()
    def on_speed_changed(self):
        value = self.speed_slider.value()
        self.speed_value_label.setText(str(value))
        self.tts_manager.set_rate(value)

    @pyqtSlot(int)
    def on_voice_changed(self, index: int):
        voice_name = self.voice_combo.itemText(index)
        try:
            self.tts_manager.set_voice_by_name(voice_name)
        except Exception:
            pass

    @pyqtSlot()
    def on_test_voice(self):
        if not self.tts_manager.is_available():
            QMessageBox.warning(self, "提示", "当前环境不支持语音朗读")
            return
        self.tts_test_button.setEnabled(False)
        self.tts_status_signal.emit("正在试听...")
        self.tts_manager.test_voice(callback=self.on_test_voice_callback)

    @pyqtSlot()
    def on_start_tts(self):
        if not self.current_novel:
            QMessageBox.warning(self, "提示", "请先选择小说")
            return
        if not self.tts_manager.is_available():
            QMessageBox.warning(self, "提示", "当前环境不支持语音朗读，请先安装 pyttsx3")
            return
        text = self.content_edit.toPlainText()
        if not text.strip():
            QMessageBox.warning(self, "提示", "当前章节没有内容")
            return
        selected_voice = self.voice_combo.currentText()
        if selected_voice and "无可用语音" not in selected_voice:
            try:
                self.tts_manager.set_voice_by_name(selected_voice)
            except Exception:
                pass
        self.tts_manager.set_rate(self.speed_slider.value())
        self.tts_active = True
        self.update_tts_controls()
        self.tts_status_signal.emit("正在朗读...")
        self.tts_manager.speak(text, callback=self.on_tts_finished_callback)

    @pyqtSlot()
    def on_stop_tts(self):
        self.stop_tts_internal()

    def stop_tts_internal(self):
        if self.tts_active:
            self.tts_manager.stop()
            self.tts_active = False
            self.tts_status_signal.emit("朗读已停止")
            self.apply_search_highlight()
            self.update_tts_controls()

    def on_tts_word(self, start: int, end: int):
        self.tts_highlight_signal.emit(start, end)

    def on_tts_finished_callback(self, success: bool, message: str):
        self.tts_finish_signal.emit(success, message or "")

    def on_test_voice_callback(self, success: bool, message: str):
        self.test_finish_signal.emit(success, message or "")

    @pyqtSlot(int, int)
    def highlight_tts_range(self, start: int, end: int):
        tmp_cursor = self.content_edit.textCursor()
        tmp_cursor.setPosition(start)
        tmp_cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        highlight = QTextEdit.ExtraSelection()
        fmt = QTextCharFormat()
        fmt.setBackground(Qt.GlobalColor.cyan)
        highlight.cursor = tmp_cursor
        highlight.format = fmt
        self._tts_extra = [highlight]
        self.apply_search_highlight()

    @pyqtSlot(bool, str)
    def handle_tts_finished(self, success: bool, message: str):
        self.tts_active = False
        self.update_tts_controls()
        if success:
            self.tts_status_signal.emit("朗读完成")
        else:
            self.tts_status_signal.emit(f"朗读失败: {message}")
            if message:
                QMessageBox.warning(self, "朗读失败", message)
        self._tts_extra = []
        self.apply_search_highlight()

    @pyqtSlot(bool, str)
    def handle_test_voice_finished(self, success: bool, message: str):
        self.tts_test_button.setEnabled(True)
        if success:
            self.tts_status_signal.emit("试听完成")
        else:
            self.tts_status_signal.emit(f"试听失败: {message}")
            if message:
                QMessageBox.warning(self, "试听失败", message)


class AlarmDialog(QDialog):
    """新建/编辑闹钟对话框"""
    
    def __init__(self, parent=None, alarm_data: Optional[Dict] = None, default_group: Optional[str] = None):
        super().__init__(parent)
        self.alarm_data = alarm_data
        self.default_group = default_group  # 默认选中的分组
        self.sound_file = ""
        self.is_playing_audio = False  # 标记是否正在播放音频
        self.sound_file_map = {}  # 存储文件名到完整路径的映射
        self.setWindowTitle("新建闹钟" if not alarm_data else "修改闹钟")
        self.setModal(True)
        self.resize(500, 600)
        self._build_ui()
        if alarm_data:
            self._load_alarm_data()
        elif default_group:
            # 如果是新建且指定了默认分组，设置选中该分组
            index = self.group_combo.findText(default_group)
            if index >= 0:
                self.group_combo.setCurrentIndex(index)
            else:
                # 如果分组不存在，设置为默认
                self.group_combo.setCurrentText("默认")
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # 应用样式表
        self.setStyleSheet("""
            QDialog {
                background-color: #f5f5f5;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #ddd;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #2196F3;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton#cancel_button {
                background-color: #f44336;
            }
            QPushButton#cancel_button:hover {
                background-color: #da190b;
            }
            QLineEdit, QComboBox, QTimeEdit, QDateEdit, QSpinBox {
                padding: 6px;
                border: 2px solid #ddd;
                border-radius: 4px;
                background-color: white;
            }
            QLineEdit:focus, QComboBox:focus, QTimeEdit:focus, QDateEdit:focus {
                border-color: #4CAF50;
            }
            QRadioButton {
                padding: 4px;
            }
            QRadioButton::indicator {
                width: 18px;
                height: 18px;
            }
            QCheckBox {
                padding: 4px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
        """)
        
        # 循环方式
        loop_group = QGroupBox("循环方式")
        loop_layout = QVBoxLayout()
        self.loop_button_group = QButtonGroup(self)
        self.loop_once = QRadioButton("一次")
        self.loop_daily = QRadioButton("每天")
        self.loop_weekly = QRadioButton("每周")
        self.loop_monthly = QRadioButton("每月")
        self.loop_yearly = QRadioButton("每年")
        self.loop_interval = QRadioButton("间隔")
        
        for i, btn in enumerate([self.loop_once, self.loop_daily, self.loop_weekly, 
                                self.loop_monthly, self.loop_yearly, self.loop_interval]):
            self.loop_button_group.addButton(btn, i)
            loop_layout.addWidget(btn)
        
        self.loop_once.setChecked(True)
        loop_group.setLayout(loop_layout)
        layout.addWidget(loop_group)
        
        # 循环设置
        date_group = QGroupBox("循环设置")
        date_layout = QVBoxLayout()
        
        # 开始日期
        start_date_layout = QHBoxLayout()
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(datetime.now().date())
        start_date_layout.addWidget(QLabel("开始日期："))
        start_date_layout.addWidget(self.date_edit)
        start_date_layout.addStretch()
        date_layout.addLayout(start_date_layout)
        
        # 结束日期（初始隐藏）
        end_date_layout = QHBoxLayout()
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDate(datetime.now().date())
        self.end_date_label = QLabel("结束日期：")
        end_date_layout.addWidget(self.end_date_label)
        end_date_layout.addWidget(self.end_date_edit)
        end_date_layout.addStretch()
        date_layout.addLayout(end_date_layout)
        # 初始隐藏结束日期
        self.end_date_label.hide()
        self.end_date_edit.hide()
        
        date_group.setLayout(date_layout)
        layout.addWidget(date_group)
        
        # 连接循环方式改变事件
        self.loop_button_group.buttonClicked.connect(self.on_loop_type_changed)
        
        # 提醒时间
        time_group = QGroupBox("提醒时间")
        time_layout = QHBoxLayout()
        self.time_edit = QTimeEdit()
        self.time_edit.setTime(datetime.now().time())
        time_layout.addWidget(QLabel("时间："))
        time_layout.addWidget(self.time_edit)
        time_layout.addStretch()
        time_group.setLayout(time_layout)
        layout.addWidget(time_group)
        
        # 提醒声音
        sound_group = QGroupBox("提醒声音")
        sound_layout = QVBoxLayout()
        
        sound_row1 = QHBoxLayout()
        self.sound_combo = QComboBox()
        self.sound_combo.addItems(["铃声1", "铃声2", "铃声3", "默认"])
        self.sound_combo.setCurrentText("铃声1")
        self.open_sound_button = QPushButton("打开本地")
        self.test_sound_button = QPushButton("试听")
        sound_row1.addWidget(QLabel("铃声："))
        sound_row1.addWidget(self.sound_combo)
        sound_row1.addWidget(self.open_sound_button)
        sound_row1.addWidget(self.test_sound_button)
        sound_layout.addLayout(sound_row1)
        
        self.ring_checkbox = QCheckBox("响铃")
        self.ring_checkbox.setChecked(True)
        sound_layout.addWidget(self.ring_checkbox)
        
        sound_behavior_group = QButtonGroup(self)
        self.sound_continuous = QRadioButton("不间断")
        self.sound_once = QRadioButton("响一次")
        self.sound_mute = QRadioButton("静音")
        self.sound_custom = QRadioButton("自定义")
        self.sound_once.setChecked(True)
        
        sound_behavior_layout = QHBoxLayout()
        for btn in [self.sound_continuous, self.sound_once, self.sound_mute, self.sound_custom]:
            sound_behavior_group.addButton(btn)
            sound_behavior_layout.addWidget(btn)
        sound_layout.addLayout(sound_behavior_layout)
        
        custom_duration_layout = QHBoxLayout()
        self.custom_duration_spin = QSpinBox()
        self.custom_duration_spin.setRange(1, 60)
        self.custom_duration_spin.setValue(1)
        self.custom_duration_spin.setEnabled(False)
        custom_duration_layout.addWidget(QLabel("自定义时长："))
        custom_duration_layout.addWidget(self.custom_duration_spin)
        custom_duration_layout.addWidget(QLabel("分钟"))
        custom_duration_layout.addStretch()
        sound_layout.addLayout(custom_duration_layout)
        
        self.sound_custom.toggled.connect(lambda checked: self.custom_duration_spin.setEnabled(checked))
        
        sound_group.setLayout(sound_layout)
        layout.addWidget(sound_group)
        
        # 任务标签
        label_group = QGroupBox("任务标签")
        label_layout = QHBoxLayout()
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("闹钟任务")
        label_layout.addWidget(QLabel("标签："))
        label_layout.addWidget(self.label_edit)
        label_group.setLayout(label_layout)
        layout.addWidget(label_group)
        
        # 选择分组（下拉选择框，不可编辑）
        group_group = QGroupBox("选择分组")
        group_layout = QVBoxLayout()
        
        # 分组选择/输入
        group_input_layout = QHBoxLayout()
        self.group_combo = QComboBox()
        self.group_combo.setEditable(False)  # 默认不可编辑，只能从下拉列表选择
        # 从父窗口获取所有分组（包括groups_list和alarms中的分组）
        groups = set(["默认"])
        parent_widget = self.parent()
        if parent_widget:
            # 从groups_list获取保存的分组
            if hasattr(parent_widget, 'groups_list'):
                groups.update(parent_widget.groups_list)
            # 从alarms中提取分组
            if hasattr(parent_widget, 'alarms'):
                for alarm in parent_widget.alarms:
                    groups.add(alarm.get("group", "默认"))
        # 排序分组，保持"默认"在第一位
        sorted_groups = sorted([g for g in groups if g != "默认"])
        if "默认" in groups:
            sorted_groups.insert(0, "默认")
        self.group_combo.addItems(sorted_groups)
        group_input_layout.addWidget(QLabel("分组："))
        group_input_layout.addWidget(self.group_combo, stretch=1)
        
        # 添加"添加分组"按钮
        self.add_group_button = QPushButton("添加分组")
        self.add_group_button.setStyleSheet("background-color: #2196F3;")
        self.add_group_button.clicked.connect(self.on_add_group_in_dialog)
        group_input_layout.addWidget(self.add_group_button)
        
        group_layout.addLayout(group_input_layout)
        
        # 提示标签
        tip_label = QLabel("💡 提示：从下拉列表选择已有分组，或点击\"添加分组\"按钮新建分组")
        tip_label.setStyleSheet("color: #666; font-size: 9pt;")
        group_layout.addWidget(tip_label)
        
        group_group.setLayout(group_layout)
        layout.addWidget(group_group)
        
        # 按钮
        button_layout = QHBoxLayout()
        self.apply_button = QPushButton("应用")
        self.save_button = QPushButton("保存")
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setObjectName("cancel_button")
        button_layout.addWidget(self.apply_button)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
        
        # 信号连接
        self.open_sound_button.clicked.connect(self.on_open_sound)
        self.test_sound_button.clicked.connect(self.on_test_sound)
        self.apply_button.clicked.connect(self.on_apply)
        self.save_button.clicked.connect(self.on_save)
        self.cancel_button.clicked.connect(self.reject)
        
        # 初始化日期选择器状态
        self.on_loop_type_changed()
    
    def on_loop_type_changed(self):
        """循环方式改变时的处理"""
        # 获取当前选中的循环方式
        checked_button = self.loop_button_group.checkedButton()
        
        # 如果选择"一次"或"间隔"，显示两个日期选择器并启用
        if checked_button in [self.loop_once, self.loop_interval]:
            self.end_date_label.show()
            self.end_date_edit.show()
            self.date_edit.setEnabled(True)
            self.end_date_edit.setEnabled(True)
            # 如果选择"一次"，结束日期默认为开始日期
            if checked_button == self.loop_once:
                self.end_date_edit.setDate(self.date_edit.date())
        else:
            # 其他模式（每天、每周、每月、每年），隐藏结束日期并禁用日期选择器
            self.end_date_label.hide()
            self.end_date_edit.hide()
            self.date_edit.setEnabled(False)
            self.end_date_edit.setEnabled(False)
    
    def on_add_group_in_dialog(self):
        """在对话框中添加新分组"""
        new_name, ok = QInputDialog.getText(self, "添加分组", "分组名称：")
        if ok and new_name.strip():
            # 检查是否已存在
            for i in range(self.group_combo.count()):
                if self.group_combo.itemText(i) == new_name.strip():
                    QMessageBox.warning(self, "提示", "该分组已存在")
                    return
            # 添加到下拉列表
            self.group_combo.addItem(new_name.strip())
            self.group_combo.setCurrentText(new_name.strip())
            QMessageBox.information(self, "成功", f"已添加分组：{new_name.strip()}\n保存闹钟后，该分组将永久保存")
    
    def on_open_sound(self):
        """打开本地声音文件或文件夹"""
        # 让用户选择文件或文件夹
        choice, ok = QInputDialog.getItem(
            self, "选择操作", "请选择：", ["选择单个文件", "选择文件夹（自动添加所有音频）"], 0, False
        )
        if not ok:
            return
        
        if choice == "选择单个文件":
            file_path, _ = QFileDialog.getOpenFileName(
                self, "选择声音文件", "", "音频文件 (*.mp3 *.wav *.ogg *.m4a *.flac);;所有文件 (*)"
            )
            if file_path:
                self.sound_file = file_path
                filename = os.path.basename(file_path)
                # 存储文件路径映射
                self.sound_file_map[filename] = file_path
                # 如果列表中不存在，添加
                if filename not in [self.sound_combo.itemText(i) for i in range(self.sound_combo.count())]:
                    self.sound_combo.addItem(filename)
                self.sound_combo.setCurrentText(filename)
        else:
            # 选择文件夹
            folder_path = QFileDialog.getExistingDirectory(self, "选择音频文件夹")
            if folder_path:
                # 扫描文件夹中的所有音频文件
                audio_extensions = ['.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac', '.wma']
                found_files = []
                for root, dirs, files in os.walk(folder_path):
                    for file in files:
                        if any(file.lower().endswith(ext) for ext in audio_extensions):
                            full_path = os.path.join(root, file)
                            found_files.append(full_path)
                
                if found_files:
                    # 添加到铃声列表
                    for file_path in found_files:
                        filename = os.path.basename(file_path)
                        # 存储文件路径映射
                        self.sound_file_map[filename] = file_path
                        if filename not in [self.sound_combo.itemText(i) for i in range(self.sound_combo.count())]:
                            self.sound_combo.addItem(filename)
                    QMessageBox.information(self, "成功", f"已从文件夹添加 {len(found_files)} 个音频文件到铃声列表")
                else:
                    QMessageBox.warning(self, "提示", "该文件夹中未找到音频文件")
    
    def _stop_audio(self):
        """停止正在播放的音频"""
        try:
            import pygame
            if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
        except:
            pass
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_FILENAME)
        except:
            pass
        self.is_playing_audio = False
    
    def _play_audio_file(self, file_path: str, duration: float = None):
        """使用程序内置播放器播放音频文件（不调用系统播放器）"""
        # 先停止之前播放的音频
        self._stop_audio()
        
        if not file_path or not os.path.exists(file_path):
            return False
        
        file_lower = file_path.lower()
        
        # 优先使用pygame（支持更多格式，且不会调用系统播放器）
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(file_path)
            pygame.mixer.music.play()
            self.is_playing_audio = True
            
            # 如果指定了时长，设置定时器停止
            if duration:
                def stop_audio():
                    try:
                        if pygame.mixer.music.get_busy():
                            pygame.mixer.music.stop()
                        self.is_playing_audio = False
                    except:
                        pass
                QTimer.singleShot(int(duration * 1000), stop_audio)
            return True
        except ImportError:
            # pygame不可用，对于WAV文件使用winsound（不调用系统播放器）
            if file_lower.endswith('.wav'):
                try:
                    import winsound
                    winsound.PlaySound(file_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                    self.is_playing_audio = True
                    # 如果指定了时长，设置定时器停止
                    if duration:
                        def stop_audio():
                            try:
                                winsound.PlaySound(None, winsound.SND_FILENAME)
                            except:
                                pass
                            self.is_playing_audio = False
                        QTimer.singleShot(int(duration * 1000), stop_audio)
                    return True
                except:
                    pass
            return False
        except Exception:
            return False
    
    def on_test_sound(self):
        """试听声音"""
        # 根据当前选中的铃声来决定播放什么
        current_sound = self.sound_combo.currentText()
        
        # 从文件路径映射中查找，或使用sound_file
        file_to_play = None
        if current_sound in self.sound_file_map:
            file_to_play = self.sound_file_map[current_sound]
        elif self.sound_file and os.path.exists(self.sound_file) and os.path.basename(self.sound_file) == current_sound:
            file_to_play = self.sound_file
        
        if file_to_play and os.path.exists(file_to_play):
            # 播放本地文件
            success = self._play_audio_file(file_to_play, duration=None)
            if success:
                QMessageBox.information(self, "提示", "正在播放声音...")
            else:
                try:
                    import winsound
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                    QMessageBox.warning(self, "提示", "无法播放此音频格式。\n建议安装pygame库：pip install pygame")
                except:
                    QMessageBox.warning(self, "提示", "无法播放声音，请安装pygame库：pip install pygame")
        else:
            # 播放默认提示音（铃声1、铃声2、铃声3或默认）
            try:
                import winsound
                # 先停止之前播放的音频
                self._stop_audio()
                winsound.MessageBeep(winsound.MB_ICONASTERISK)  # 系统提示音
                time.sleep(0.2)
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
                QMessageBox.information(self, "提示", "正在播放默认提示音...")
            except:
                QMessageBox.information(self, "提示", "使用默认提示音")
    
    def _load_alarm_data(self):
        """加载闹钟数据到界面"""
        if not self.alarm_data:
            return
        # 加载循环方式
        loop_type = self.alarm_data.get("loop_type", "once")
        loop_map = {
            "once": self.loop_once,
            "daily": self.loop_daily,
            "weekly": self.loop_weekly,
            "monthly": self.loop_monthly,
            "yearly": self.loop_yearly,
            "interval": self.loop_interval,
        }
        if loop_type in loop_map:
            loop_map[loop_type].setChecked(True)
        
        # 加载日期和时间
        if "date" in self.alarm_data:
            try:
                date = datetime.fromisoformat(self.alarm_data["date"]).date()
                self.date_edit.setDate(date)
            except:
                pass
        
        # 加载结束日期
        if "end_date" in self.alarm_data:
            try:
                end_date = datetime.fromisoformat(self.alarm_data["end_date"]).date()
                self.end_date_edit.setDate(end_date)
            except:
                pass
        else:
            # 如果没有结束日期，默认与开始日期相同
            self.end_date_edit.setDate(self.date_edit.date())
        
        # 更新日期选择器状态（根据循环方式）
        self.on_loop_type_changed()
        
        if "time" in self.alarm_data:
            try:
                time_obj = datetime.strptime(self.alarm_data["time"], "%H:%M:%S").time()
                self.time_edit.setTime(time_obj)
            except:
                pass
        
        # 加载其他设置
        self.label_edit.setText(self.alarm_data.get("label", ""))
        self.group_combo.setCurrentText(self.alarm_data.get("group", "默认"))
        self.sound_file = self.alarm_data.get("sound_file", "")
        sound_combo_text = self.alarm_data.get("sound_combo", "铃声1")
        if self.sound_file and os.path.exists(self.sound_file):
            filename = os.path.basename(self.sound_file)
            # 存储文件路径映射
            self.sound_file_map[filename] = self.sound_file
            if filename not in [self.sound_combo.itemText(i) for i in range(self.sound_combo.count())]:
                self.sound_combo.addItem(filename)
            self.sound_combo.setCurrentText(filename)
        else:
            if sound_combo_text in [self.sound_combo.itemText(i) for i in range(self.sound_combo.count())]:
                self.sound_combo.setCurrentText(sound_combo_text)
        
        self.ring_checkbox.setChecked(self.alarm_data.get("ring", True))
        
        sound_behavior = self.alarm_data.get("sound_behavior", "once")
        behavior_map = {
            "continuous": self.sound_continuous,
            "once": self.sound_once,
            "mute": self.sound_mute,
            "custom": self.sound_custom,
        }
        if sound_behavior in behavior_map:
            behavior_map[sound_behavior].setChecked(True)
        
        if "custom_duration" in self.alarm_data:
            self.custom_duration_spin.setValue(self.alarm_data["custom_duration"])
    
    def get_alarm_data(self) -> Dict:
        """获取闹钟数据"""
        # 确定循环方式
        loop_type = "once"
        if self.loop_daily.isChecked():
            loop_type = "daily"
        elif self.loop_weekly.isChecked():
            loop_type = "weekly"
        elif self.loop_monthly.isChecked():
            loop_type = "monthly"
        elif self.loop_yearly.isChecked():
            loop_type = "yearly"
        elif self.loop_interval.isChecked():
            loop_type = "interval"
        
        # 确定声音行为
        sound_behavior = "once"
        if self.sound_continuous.isChecked():
            sound_behavior = "continuous"
        elif self.sound_mute.isChecked():
            sound_behavior = "mute"
        elif self.sound_custom.isChecked():
            sound_behavior = "custom"
        
        # 确定要保存的sound_file（从文件映射或sound_file获取）
        current_sound = self.sound_combo.currentText()
        final_sound_file = ""
        if current_sound in self.sound_file_map:
            final_sound_file = self.sound_file_map[current_sound]
        elif self.sound_file and os.path.exists(self.sound_file) and os.path.basename(self.sound_file) == current_sound:
            final_sound_file = self.sound_file
        elif self.sound_file and os.path.exists(self.sound_file):
            final_sound_file = self.sound_file
        
        data = {
            "id": self.alarm_data.get("id") if self.alarm_data else f"alarm_{int(time.time())}",
            "loop_type": loop_type,
            "date": self.date_edit.date().toString(Qt.DateFormat.ISODate),
            "time": self.time_edit.time().toString("HH:mm:ss"),
            "label": self.label_edit.text().strip() or "闹钟任务",
            "group": self.group_combo.currentText(),
            "sound_file": final_sound_file,  # 保存完整路径
            "sound_combo": self.sound_combo.currentText(),  # 保存选择的铃声类型
            "ring": self.ring_checkbox.isChecked(),
            "sound_behavior": sound_behavior,
            "custom_duration": self.custom_duration_spin.value() if sound_behavior == "custom" else 1,
            "enabled": self.alarm_data.get("enabled", True) if self.alarm_data else True,
            "created_time": self.alarm_data.get("created_time", time.time()) if self.alarm_data else time.time(),
        }
        
        # 如果是"一次"或"间隔"模式，保存结束日期
        if loop_type in ["once", "interval"]:
            data["end_date"] = self.end_date_edit.date().toString(Qt.DateFormat.ISODate)
        
        return data
    
    def on_apply(self):
        """应用（不关闭对话框）"""
        if not self.label_edit.text().strip():
            QMessageBox.warning(self, "提示", "请输入任务标签")
            return
        # 可以在这里添加保存逻辑，但不关闭对话框
        QMessageBox.information(self, "提示", "设置已应用")
    
    def accept(self):
        """接受对话框（保存）"""
        # 停止播放音频
        self._stop_audio()
        super().accept()
    
    def reject(self):
        """拒绝对话框（取消）"""
        # 停止播放音频
        self._stop_audio()
        super().reject()
    
    def on_save(self):
        """保存并关闭"""
        if not self.label_edit.text().strip():
            QMessageBox.warning(self, "提示", "请输入任务标签")
            return
        
        # 获取当前选择的分组
        selected_group = self.group_combo.currentText().strip()
        if selected_group:
            # 如果分组不在父窗口的groups_list中，添加到groups_list
            parent_widget = self.parent()
            if parent_widget and hasattr(parent_widget, 'groups_list'):
                if selected_group not in parent_widget.groups_list:
                    parent_widget.groups_list.append(selected_group)
                    # 排序，保持"默认"在第一位
                    parent_widget.groups_list = sorted([g for g in parent_widget.groups_list if g != "默认"])
                    if "默认" not in parent_widget.groups_list:
                        parent_widget.groups_list.insert(0, "默认")
                    else:
                        parent_widget.groups_list.insert(0, "默认")
                    # 保存到文件
                    if hasattr(parent_widget, '_save_alarms'):
                        parent_widget._save_alarms()
                    if hasattr(parent_widget, '_refresh_groups'):
                        parent_widget._refresh_groups()
        
        self.accept()


class AlarmNotificationDialog(QDialog):
    """闹钟提醒通知对话框（自定义样式）"""
    
    def __init__(self, alarm: Dict, parent=None):
        super().__init__(parent)
        self.alarm = alarm
        self.alarm_tab = parent
        self.sound_player_thread = None
        self._should_stop_sound = False  # 初始化停止标志
        self.setWindowTitle("闹钟提醒")
        self.setModal(True)
        self.resize(400, 300)
        self._build_ui()
        self._start_sound()
    
    def showEvent(self, event):
        """显示事件，设置对话框位置到桌面右上角"""
        super().showEvent(event)
        self._set_position_top_right()
    
    def _set_position_top_right(self):
        """设置对话框位置到桌面右上角"""
        try:
            # 获取屏幕尺寸
            screen = QApplication.primaryScreen()
            if screen:
                screen_geometry = screen.geometry()
                
                # 计算右上角位置（留出一些边距）
                margin = 20
                x = screen_geometry.width() - self.width() - margin
                y = margin
                
                self.move(x, y)
        except:
            # 如果失败，使用默认位置
            pass
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)
        
        # 样式
        self.setStyleSheet("""
            QDialog {
                background-color: white;
            }
            QLabel {
                color: #333;
            }
            QPushButton {
                padding: 10px 20px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 11pt;
            }
            QPushButton#snooze_button {
                background-color: #87CEEB;
                color: white;
            }
            QPushButton#snooze_button:hover {
                background-color: #6BB6FF;
            }
            QPushButton#modify_button {
                background-color: #FFD700;
                color: #333;
            }
            QPushButton#modify_button:hover {
                background-color: #FFC700;
            }
            QPushButton#complete_button {
                background-color: #FFB6C1;
                color: white;
            }
            QPushButton#complete_button:hover {
                background-color: #FFA0B0;
            }
        """)
        
        # 图标和标题区域
        icon_layout = QHBoxLayout()
        icon_layout.addStretch()
        
        # 创建一个带图标的标签（使用emoji或文本）
        icon_label = QLabel("🔔")
        icon_label.setStyleSheet("font-size: 60pt;")
        icon_layout.addWidget(icon_label)
        icon_layout.addStretch()
        layout.addLayout(icon_layout)
        
        # 时间显示
        time_label = QLabel(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        time_label.setStyleSheet("color: #666; font-size: 10pt;")
        layout.addWidget(time_label)
        
        # 任务标签
        label = self.alarm.get("label", "闹钟任务")
        title_label = QLabel(label)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 18pt; font-weight: bold; color: #333;")
        layout.addWidget(title_label)
        
        layout.addStretch()
        
        # 按钮
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        self.snooze_button = QPushButton("延时5分钟")
        self.snooze_button.setObjectName("snooze_button")
        self.snooze_button.clicked.connect(self.on_snooze)
        
        self.modify_button = QPushButton("修改")
        self.modify_button.setObjectName("modify_button")
        self.modify_button.clicked.connect(self.on_modify)
        
        self.complete_button = QPushButton("完成")
        self.complete_button.setObjectName("complete_button")
        self.complete_button.clicked.connect(self.on_complete)
        
        button_layout.addWidget(self.snooze_button)
        button_layout.addWidget(self.modify_button)
        button_layout.addWidget(self.complete_button)
        layout.addLayout(button_layout)
    
    def _start_sound(self):
        """开始播放声音"""
        sound_file = self.alarm.get("sound_file", "")
        ring = self.alarm.get("ring", True)
        sound_behavior = self.alarm.get("sound_behavior", "once")
        
        if not ring:
            return
        
        # 在后台线程播放声音
        def play_sound_thread():
            try:
                import winsound
                
                # 如果没有自定义文件，使用系统默认提示音
                if not sound_file or not os.path.exists(sound_file):
                    if sound_behavior == "once":
                        winsound.MessageBeep(winsound.MB_ICONASTERISK)
                        time.sleep(0.2)
                        winsound.MessageBeep(winsound.MB_ICONASTERISK)
                    elif sound_behavior == "continuous":
                        while not self._should_stop_sound:
                            winsound.MessageBeep(winsound.MB_ICONASTERISK)
                            time.sleep(0.5)
                else:
                    # 播放自定义文件
                    file_lower = sound_file.lower()
                    try:
                        if file_lower.endswith('.wav'):
                            if sound_behavior == "once":
                                winsound.PlaySound(sound_file, winsound.SND_FILENAME)
                            elif sound_behavior == "continuous":
                                winsound.PlaySound(sound_file, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP)
                            elif sound_behavior == "custom":
                                duration = self.alarm.get("custom_duration", 1) * 60
                                winsound.PlaySound(sound_file, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP)
                                time.sleep(duration)
                                winsound.PlaySound(None, winsound.SND_FILENAME)
                        else:
                            # 使用pygame播放mp3等格式
                            try:
                                import pygame
                                if not pygame.mixer.get_init():
                                    pygame.mixer.init()
                                pygame.mixer.music.load(sound_file)
                                if sound_behavior == "once":
                                    pygame.mixer.music.play()
                                    while pygame.mixer.music.get_busy() and not self._should_stop_sound:
                                        time.sleep(0.1)
                                elif sound_behavior == "continuous":
                                    pygame.mixer.music.play(-1)
                                    while not self._should_stop_sound:
                                        time.sleep(0.1)
                                elif sound_behavior == "custom":
                                    duration = self.alarm.get("custom_duration", 1) * 60
                                    pygame.mixer.music.play(-1)
                                    time.sleep(duration)
                                if self._should_stop_sound:
                                    pygame.mixer.music.stop()
                            except ImportError:
                                winsound.MessageBeep(winsound.MB_ICONASTERISK)
                    except Exception:
                        winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass
        
        self.sound_player_thread = threading.Thread(target=play_sound_thread, daemon=True)
        self.sound_player_thread.start()
    
    def _stop_sound(self):
        """停止播放声音"""
        self._should_stop_sound = True
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_FILENAME)
        except:
            pass
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except:
            pass
    
    def stop_sound(self):
        """公共方法：停止播放声音"""
        self._stop_sound()
    
    def on_snooze(self):
        """延时5分钟"""
        self.stop_sound()
        # 修改闹钟时间，增加5分钟
        current_time = self.alarm.get("time", "")
        if current_time:
            try:
                time_obj = datetime.strptime(current_time, "%H:%M:%S").time()
                new_time = (datetime.combine(datetime.today(), time_obj) + timedelta(minutes=5)).time()
                self.alarm["time"] = new_time.strftime("%H:%M:%S")
                # 清除触发时间，允许新的时间再次触发
                if "last_trigger_time" in self.alarm:
                    del self.alarm["last_trigger_time"]
                if self.alarm_tab and hasattr(self.alarm_tab, '_save_alarms'):
                    self.alarm_tab._save_alarms()
                    self.alarm_tab._refresh_table()
            except:
                pass
        self.accept()
    
    def on_modify(self):
        """修改闹钟"""
        self.stop_sound()
        if self.alarm_tab:
            dialog = AlarmDialog(self.alarm_tab, self.alarm)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                updated_data = dialog.get_alarm_data()
                self.alarm.update(updated_data)
                # 清除触发时间，允许新的设置再次触发
                if "last_trigger_time" in self.alarm:
                    del self.alarm["last_trigger_time"]
                if hasattr(self.alarm_tab, '_save_alarms'):
                    self.alarm_tab._save_alarms()
                    self.alarm_tab._refresh_table()
        self.accept()
    
    def on_complete(self):
        """完成"""
        self.stop_sound()
        # 确保更新 last_trigger_time，防止立即再次触发
        # 使用完整时间字符串（包含秒），确保在当前分钟内不会再次触发
        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")
        self.alarm["last_trigger_time"] = current_time
        if self.alarm_tab and hasattr(self.alarm_tab, '_save_alarms'):
            self.alarm_tab._save_alarms()
        self.accept()
    
    def closeEvent(self, event):
        """关闭事件"""
        self.stop_sound()
        # 确保更新 last_trigger_time，防止立即再次触发
        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")
        self.alarm["last_trigger_time"] = current_time
        if self.alarm_tab and hasattr(self.alarm_tab, '_save_alarms'):
            self.alarm_tab._save_alarms()
        super().closeEvent(event)


class RecycleBinDialog(QDialog):
    """回收站对话框"""
    
    def __init__(self, deleted_alarms: List[Dict], parent=None):
        super().__init__(parent)
        self.deleted_alarms = deleted_alarms
        self.restored_ids = []
        self.deleted_ids = []
        self.setWindowTitle("回收站")
        self.setModal(True)
        self.resize(700, 500)
        self._build_ui()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # 提示标签
        info_label = QLabel(f"共有 {len(self.deleted_alarms)} 个已删除的闹钟")
        info_label.setStyleSheet("font-size: 11pt; font-weight: bold; color: #666;")
        layout.addWidget(info_label)
        
        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["", "频率", "日期", "时间", "任务标签", "删除时间"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        
        # 填充数据
        self.table.setRowCount(len(self.deleted_alarms))
        for row, alarm in enumerate(self.deleted_alarms):
            checkbox = QTableWidgetItem()
            checkbox.setCheckState(Qt.CheckState.Unchecked)
            self.table.setItem(row, 0, checkbox)
            
            loop_type = alarm.get("loop_type", "once")
            loop_map = {
                "once": "一次", "daily": "每天", "weekly": "每周",
                "monthly": "每月", "yearly": "每年", "interval": "间隔"
            }
            self.table.setItem(row, 1, QTableWidgetItem(loop_map.get(loop_type, "一次")))
            
            date_str = alarm.get("date", "")
            if loop_type == "daily":
                date_str = "每天"
            self.table.setItem(row, 2, QTableWidgetItem(date_str))
            
            self.table.setItem(row, 3, QTableWidgetItem(alarm.get("time", "")))
            self.table.setItem(row, 4, QTableWidgetItem(alarm.get("label", "闹钟任务")))
            
            deleted_time = alarm.get("deleted_time", time.time())
            deleted_str = datetime.fromtimestamp(deleted_time).strftime("%Y-%m-%d %H:%M:%S")
            self.table.setItem(row, 5, QTableWidgetItem(deleted_str))
            
            # 保存ID
            id_item = QTableWidgetItem()
            id_item.setData(Qt.ItemDataRole.UserRole, alarm.get("id"))
            self.table.setItem(row, 0, id_item)
            self.table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)
        
        layout.addWidget(self.table)
        
        # 按钮
        button_layout = QHBoxLayout()
        self.restore_button = QPushButton("恢复选中")
        self.restore_button.setStyleSheet("background-color: #4CAF50;")
        self.delete_button = QPushButton("永久删除")
        self.delete_button.setStyleSheet("background-color: #f44336;")
        self.close_button = QPushButton("关闭")
        self.close_button.setStyleSheet("background-color: #9E9E9E;")
        
        self.restore_button.clicked.connect(self.on_restore)
        self.delete_button.clicked.connect(self.on_delete)
        self.close_button.clicked.connect(self.accept)
        
        button_layout.addWidget(self.restore_button)
        button_layout.addWidget(self.delete_button)
        button_layout.addStretch()
        button_layout.addWidget(self.close_button)
        layout.addLayout(button_layout)
    
    def on_restore(self):
        """恢复选中的闹钟"""
        selected_ids = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                alarm_id = item.data(Qt.ItemDataRole.UserRole)
                if alarm_id:
                    selected_ids.append(alarm_id)
        
        if not selected_ids:
            QMessageBox.warning(self, "提示", "请先选择要恢复的闹钟")
            return
        
        self.restored_ids = selected_ids
        QMessageBox.information(self, "提示", f"已选择恢复 {len(selected_ids)} 个闹钟")
        self.accept()
    
    def on_delete(self):
        """永久删除选中的闹钟"""
        selected_ids = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                alarm_id = item.data(Qt.ItemDataRole.UserRole)
                if alarm_id:
                    selected_ids.append(alarm_id)
        
        if not selected_ids:
            QMessageBox.warning(self, "提示", "请先选择要永久删除的闹钟")
            return
        
        if QMessageBox.question(self, "确认", f"确定要永久删除 {len(selected_ids)} 个闹钟吗？\n此操作不可恢复！") != QMessageBox.StandardButton.Yes:
            return
        
        self.deleted_ids = selected_ids
        self.accept()
    
    def get_restored_ids(self):
        return self.restored_ids
    
    def get_deleted_ids(self):
        return self.deleted_ids


class GroupEditDialog(QDialog):
    """分组编辑对话框"""
    
    def __init__(self, alarms: List[Dict], parent=None, groups_list: List[str] = None):
        super().__init__(parent)
        self.alarms = alarms
        self.groups_list = groups_list or ["默认"]
        self.group_changes = {}
        self.deleted_groups = []
        self.setWindowTitle("编辑分组")
        self.setModal(True)
        self.resize(500, 400)
        self._build_ui()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # 获取所有分组（包括groups_list和alarms中的分组）
        groups = set(["默认"])
        # 从groups_list获取保存的分组
        groups.update(self.groups_list)
        # 从alarms中提取分组
        for alarm in self.alarms:
            groups.add(alarm.get("group", "默认"))
        self.groups = sorted(groups)
        
        # 分组列表
        list_label = QLabel("分组列表（双击编辑名称）：")
        list_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(list_label)
        
        self.group_list = QListWidget()
        self.group_list.addItems(self.groups)
        self.group_list.itemDoubleClicked.connect(self.on_item_double_clicked)
        layout.addWidget(self.group_list)
        
        # 按钮布局
        button_layout1 = QHBoxLayout()
        self.add_button = QPushButton("添加分组")
        self.add_button.setStyleSheet("background-color: #4CAF50;")
        self.delete_button = QPushButton("删除分组")
        self.delete_button.setStyleSheet("background-color: #f44336;")
        
        self.add_button.clicked.connect(self.on_add_group)
        self.delete_button.clicked.connect(self.on_delete_group)
        
        button_layout1.addWidget(self.add_button)
        button_layout1.addWidget(self.delete_button)
        button_layout1.addStretch()
        layout.addLayout(button_layout1)
        
        # 关闭按钮
        button_layout2 = QHBoxLayout()
        self.save_button = QPushButton("保存")
        self.save_button.setStyleSheet("background-color: #2196F3;")
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setStyleSheet("background-color: #9E9E9E;")
        
        self.save_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout2.addStretch()
        button_layout2.addWidget(self.save_button)
        button_layout2.addWidget(self.cancel_button)
        layout.addLayout(button_layout2)
    
    def on_item_double_clicked(self, item: QListWidgetItem):
        """双击编辑分组名称"""
        old_name = item.text()
        if old_name == "默认":
            QMessageBox.warning(self, "提示", "不能修改默认分组")
            return
        
        new_name, ok = QInputDialog.getText(self, "重命名分组", "新名称：", text=old_name)
        if ok and new_name.strip() and new_name != old_name:
            if new_name in self.groups:
                QMessageBox.warning(self, "提示", "该分组已存在")
                return
            self.group_changes[old_name] = new_name.strip()
            item.setText(new_name.strip())
            self.groups = [new_name.strip() if g == old_name else g for g in self.groups]
    
    def on_add_group(self):
        """添加新分组"""
        new_name, ok = QInputDialog.getText(self, "添加分组", "分组名称：")
        if ok and new_name.strip():
            if new_name.strip() in self.groups:
                QMessageBox.warning(self, "提示", "该分组已存在")
                return
            self.group_list.addItem(new_name.strip())
            self.groups.append(new_name.strip())
            # 排序分组列表，保持"默认"在第一位
            self.groups = sorted([g for g in self.groups if g != "默认"])
            if "默认" not in self.groups:
                self.groups.insert(0, "默认")
            QMessageBox.information(self, "成功", f"已添加分组：{new_name.strip()}")
    
    def on_delete_group(self):
        """删除分组"""
        current_item = self.group_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "提示", "请先选择要删除的分组")
            return
        
        group_name = current_item.text()
        if group_name == "默认":
            QMessageBox.warning(self, "提示", "不能删除默认分组")
            return
        
        count = sum(1 for a in self.alarms if a.get("group") == group_name)
        if count > 0:
            msg = f"分组 '{group_name}' 中有 {count} 个闹钟，删除后这些闹钟将移到默认分组。\n确定要删除吗？"
        else:
            msg = f"确定要删除分组 '{group_name}' 吗？"
        
        if QMessageBox.question(self, "确认", msg) != QMessageBox.StandardButton.Yes:
            return
        
        self.deleted_groups.append(group_name)
        self.group_list.takeItem(self.group_list.row(current_item))
        self.groups.remove(group_name)
    
    def get_group_changes(self):
        return self.group_changes
    
    def get_deleted_groups(self):
        return self.deleted_groups
    
    def get_all_groups(self):
        """获取所有分组（包括新添加的）"""
        return self.groups


class BatchAlarmDialog(QDialog):
    """批量添加闹钟"""

    def __init__(self, groups: List[str], default_group: str = "默认", parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量添加闹钟")
        self.setModal(True)
        self.resize(420, 360)
        self.created_alarms: List[Dict] = []
        self.groups = ["默认"]
        for g in groups:
            if g and g not in self.groups:
                self.groups.append(g)
        self.sound_file_map: Dict[str, str] = {}
        self.sound_file = ""
        self.is_playing_audio = False
        self._build_ui(default_group if default_group in self.groups else "默认")

    def _build_ui(self, default_group: str):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        range_box = QGroupBox("时间范围")
        range_layout = QGridLayout()
        self.start_hour = QSpinBox()
        self.start_hour.setRange(0, 23)
        self.start_hour.setValue(8)
        self.end_hour = QSpinBox()
        self.end_hour.setRange(0, 23)
        self.end_hour.setValue(17)
        self.minute_spin = QSpinBox()
        self.minute_spin.setRange(0, 59)
        self.minute_spin.setValue(5)
        self.step_spin = QSpinBox()
        self.step_spin.setRange(1, 24)
        self.step_spin.setValue(1)

        range_layout.addWidget(QLabel("开始小时："), 0, 0)
        range_layout.addWidget(self.start_hour, 0, 1)
        range_layout.addWidget(QLabel("结束小时："), 0, 2)
        range_layout.addWidget(self.end_hour, 0, 3)
        range_layout.addWidget(QLabel("分钟："), 1, 0)
        range_layout.addWidget(self.minute_spin, 1, 1)
        range_layout.addWidget(QLabel("间隔（小时）："), 1, 2)
        range_layout.addWidget(self.step_spin, 1, 3)
        range_box.setLayout(range_layout)
        layout.addWidget(range_box)

        option_box = QGroupBox("闹钟选项")
        option_layout = QGridLayout()

        self.label_edit = QLineEdit("整点提醒")
        self.group_combo = QComboBox()
        self.group_combo.addItems(self.groups)
        self.group_combo.setCurrentText(default_group)
        self.loop_combo = QComboBox()
        self.loop_combo.addItems(["每天重复", "仅一次（指定日期）"])
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setEnabled(False)
        self.loop_combo.currentIndexChanged.connect(
            lambda idx: self.date_edit.setEnabled(idx == 1)
        )

        option_layout.addWidget(QLabel("标签前缀："), 0, 0)
        option_layout.addWidget(self.label_edit, 0, 1, 1, 3)
        option_layout.addWidget(QLabel("归属分组："), 1, 0)
        option_layout.addWidget(self.group_combo, 1, 1)
        option_layout.addWidget(QLabel("重复方式："), 1, 2)
        option_layout.addWidget(self.loop_combo, 1, 3)
        option_layout.addWidget(QLabel("生效日期："), 2, 0)
        option_layout.addWidget(self.date_edit, 2, 1)
        option_box.setLayout(option_layout)
        layout.addWidget(option_box)

        sound_box = QGroupBox("提醒方式")
        sound_layout = QGridLayout()
        self.sound_combo = QComboBox()
        self.sound_combo.addItems(["铃声1", "铃声2", "铃声3", "默认"])
        self.open_sound_button = QPushButton("打开本地")
        self.test_sound_button = QPushButton("试听")
        self.ring_checkbox = QCheckBox("响铃")
        self.ring_checkbox.setChecked(True)
        sound_layout.addWidget(QLabel("铃声："), 0, 0)
        sound_layout.addWidget(self.sound_combo, 0, 1)
        sound_layout.addWidget(self.open_sound_button, 0, 2)
        sound_layout.addWidget(self.test_sound_button, 0, 3)
        sound_layout.addWidget(self.ring_checkbox, 1, 0, 1, 2)
        sound_box.setLayout(sound_layout)
        layout.addWidget(sound_box)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.open_sound_button.clicked.connect(self.on_open_sound)
        self.test_sound_button.clicked.connect(self.on_test_sound)

    def on_accept(self):
        alarms = self._generate_alarms()
        if not alarms:
            QMessageBox.warning(self, "提示", "未生成任何闹钟，请检查输入范围")
            return
        self.created_alarms = alarms
        self.accept()

    def _generate_alarms(self) -> List[Dict]:
        start = self.start_hour.value()
        end = self.end_hour.value()
        minute = self.minute_spin.value()
        step = max(1, self.step_spin.value())
        if start > end:
            start, end = end, start
        hours = list(range(start, end + 1, step))
        if len(hours) > 48:
            QMessageBox.warning(self, "提示", "一次最多生成 48 个闹钟，请缩小范围")
            return []

        label_prefix = self.label_edit.text().strip() or "整点提醒"
        group = self.group_combo.currentText() or "默认"
        loop_type = "daily" if self.loop_combo.currentIndex() == 0 else "once"
        date_str = self.date_edit.date().toString(Qt.DateFormat.ISODate)
        created_base = time.time()
        sound_choice = self.sound_combo.currentText()
        sound_file_path = ""
        if sound_choice in self.sound_file_map:
            sound_file_path = self.sound_file_map[sound_choice]
        elif self.sound_file and os.path.exists(self.sound_file) and os.path.basename(self.sound_file) == sound_choice:
            sound_file_path = self.sound_file
        ring = self.ring_checkbox.isChecked()

        alarms: List[Dict] = []
        for idx, hour in enumerate(hours):
            time_str = f"{hour:02d}:{minute:02d}:00"
            alarm = {
                "id": f"alarm_batch_{int(created_base * 1000) + idx}",
                "loop_type": loop_type,
                "date": date_str,
                "time": time_str,
                "label": f"{label_prefix} {hour:02d}:{minute:02d}",
                "group": group,
                "sound_file": sound_file_path,
                "sound_combo": sound_choice,
                "ring": ring,
                "sound_behavior": "once",
                "custom_duration": 1,
                "enabled": True,
                "created_time": created_base + idx * 0.01,
            }
            if loop_type == "once":
                alarm["end_date"] = date_str
            alarms.append(alarm)
        return alarms

    def get_created_alarms(self) -> List[Dict]:
        return self.created_alarms

    def accept(self):
        self._stop_audio()
        super().accept()

    def reject(self):
        self._stop_audio()
        super().reject()

    def _stop_audio(self):
        """停止正在播放的音频"""
        try:
            import pygame
            if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
                pygame.mixer.music.stop()
        except:
            pass
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_FILENAME)
        except:
            pass
        self.is_playing_audio = False

    def _play_audio_file(self, file_path: str):
        if not file_path or not os.path.exists(file_path):
            return False
        self._stop_audio()
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(file_path)
            pygame.mixer.music.play()
            self.is_playing_audio = True
            return True
        except Exception:
            file_lower = file_path.lower()
            if file_lower.endswith(".wav"):
                try:
                    import winsound
                    winsound.PlaySound(file_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                    self.is_playing_audio = True
                    return True
                except:
                    return False
            return False

    def on_test_sound(self):
        current_sound = self.sound_combo.currentText()
        file_path = ""
        if current_sound in self.sound_file_map:
            file_path = self.sound_file_map[current_sound]
        elif self.sound_file and os.path.exists(self.sound_file) and os.path.basename(self.sound_file) == current_sound:
            file_path = self.sound_file

        if file_path:
            success = self._play_audio_file(file_path)
            if success:
                QMessageBox.information(self, "提示", "正在播放声音...")
            else:
                QMessageBox.warning(self, "提示", "无法播放此音频，请安装 pygame 或选择 WAV 文件")
        else:
            try:
                import winsound
                self._stop_audio()
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
                time.sleep(0.2)
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except:
                pass
            QMessageBox.information(self, "提示", "已播放默认提示音")

    def on_open_sound(self):
        choice, ok = QInputDialog.getItem(
            self,
            "选择操作",
            "请选择：",
            ["选择单个文件", "选择文件夹（自动添加所有音频）"],
            0,
            False,
        )
        if not ok:
            return

        if choice == "选择单个文件":
            file_path, _ = QFileDialog.getOpenFileName(
                self, "选择声音文件", "", "音频文件 (*.mp3 *.wav *.ogg *.m4a *.flac);;所有文件 (*)"
            )
            if file_path:
                filename = os.path.basename(file_path)
                self.sound_file_map[filename] = file_path
                if filename not in [self.sound_combo.itemText(i) for i in range(self.sound_combo.count())]:
                    self.sound_combo.addItem(filename)
                self.sound_combo.setCurrentText(filename)
                self.sound_file = file_path
        else:
            folder_path = QFileDialog.getExistingDirectory(self, "选择音频文件夹")
            if not folder_path:
                return
            audio_extensions = [".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac", ".wma"]
            found_files = []
            for root, _, files in os.walk(folder_path):
                for file in files:
                    if any(file.lower().endswith(ext) for ext in audio_extensions):
                        full_path = os.path.join(root, file)
                        found_files.append(full_path)
                        filename = os.path.basename(full_path)
                        self.sound_file_map[filename] = full_path
                        if filename not in [self.sound_combo.itemText(i) for i in range(self.sound_combo.count())]:
                            self.sound_combo.addItem(filename)
            if found_files:
                QMessageBox.information(self, "成功", f"已添加 {len(found_files)} 个音频文件")
            else:
                QMessageBox.warning(self, "提示", "未找到音频文件")


class AlarmTab(QWidget):
    """闹钟提醒管理标签页"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.alarms: List[Dict] = []
        self.deleted_alarms: List[Dict] = []
        self.groups_list: List[str] = ["默认"]  # 保存的分组列表
        self._load_alarms()
        self._build_ui()
        self._refresh_table()
        self._setup_alarm_checker()
        self._setup_refresh_timer()
    
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 应用样式表
        self.setStyleSheet("""
            QWidget {
                font-family: "Microsoft YaHei", "微软雅黑", Arial, sans-serif;
                font-size: 10pt;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton#recycle_button {
                background-color: #FF9800;
            }
            QPushButton#recycle_button:hover {
                background-color: #F57C00;
            }
            QComboBox {
                padding: 6px;
                border: 2px solid #ddd;
                border-radius: 4px;
                background-color: white;
            }
            QComboBox:hover {
                border-color: #4CAF50;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QTableWidget {
                border: 2px solid #ddd;
                border-radius: 4px;
                background-color: white;
                gridline-color: #e0e0e0;
                selection-background-color: #E3F2FD;
            }
            QTableWidget::item {
                padding: 6px;
            }
            QTableWidget::item:selected {
                background-color: #E3F2FD;
                color: #1976D2;
            }
            QHeaderView::section {
                background-color: #2196F3;
                color: white;
                padding: 8px;
                border: none;
                font-weight: bold;
            }
        """)
        
        # 控制栏
        control_layout = QHBoxLayout()
        control_layout.setSpacing(8)
        
        self.group_combo = QComboBox()
        self._refresh_groups()
        self.group_combo.currentTextChanged.connect(self._refresh_table)
        
        self.group_edit_button = QPushButton("编辑分组")
        self.group_edit_button.setStyleSheet("background-color: #2196F3;")
        self.group_edit_button.clicked.connect(self.on_edit_groups)
        
        self.new_button = QPushButton("新建")
        self.batch_button = QPushButton("批量添加")
        self.modify_button = QPushButton("修改")
        self.delete_button = QPushButton("删除")
        self.clear_button = QPushButton("清空")
        self.recycle_button = QPushButton("回收站")
        self.recycle_button.setObjectName("recycle_button")
        
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["按创建日期↓", "按创建日期↑", "按时间↓", "按时间↑"])
        self.sort_combo.currentTextChanged.connect(self._refresh_table)
        
        control_layout.addWidget(QLabel("分组："))
        control_layout.addWidget(self.group_combo)
        control_layout.addWidget(self.group_edit_button)
        control_layout.addWidget(self.new_button)
        control_layout.addWidget(self.batch_button)
        control_layout.addWidget(self.modify_button)
        control_layout.addWidget(self.delete_button)
        control_layout.addWidget(self.clear_button)
        control_layout.addWidget(self.recycle_button)
        control_layout.addStretch()
        control_layout.addWidget(QLabel("排序："))
        control_layout.addWidget(self.sort_combo)
        layout.addLayout(control_layout)
        
        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["", "频率", "日期", "时间", "任务标签", "剩余", "状态"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)
        
        # 信号连接
        self.new_button.clicked.connect(self.on_new_alarm)
        self.batch_button.clicked.connect(self.on_batch_add_alarm)
        self.modify_button.clicked.connect(self.on_modify_alarm)
        self.delete_button.clicked.connect(self.on_delete_alarm)
        self.clear_button.clicked.connect(self.on_clear_alarms)
        self.recycle_button.clicked.connect(self.on_recycle_bin)
        self.table.itemDoubleClicked.connect(self.on_table_double_clicked)
        self.table.cellClicked.connect(self.on_table_cell_clicked)
    
    def _load_alarms(self):
        """加载闹钟数据"""
        if not os.path.exists(ALARM_DATA_FILE):
            self.alarms = []
            self.deleted_alarms = []
            self.groups_list = ["默认"]
            return
        try:
            with open(ALARM_DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.alarms = data.get("alarms", [])
            self.deleted_alarms = data.get("deleted_alarms", [])
            self.groups_list = data.get("groups_list", ["默认"])
            # 确保"默认"分组存在
            if "默认" not in self.groups_list:
                self.groups_list.insert(0, "默认")
        except Exception:
            self.alarms = []
            self.deleted_alarms = []
            self.groups_list = ["默认"]
    
    def _save_alarms(self):
        """保存闹钟数据"""
        try:
            os.makedirs(os.path.dirname(ALARM_DATA_FILE), exist_ok=True)
            data = {
                "alarms": self.alarms,
                "deleted_alarms": getattr(self, 'deleted_alarms', []),
                "groups_list": getattr(self, 'groups_list', ["默认"])
            }
            with open(ALARM_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    def _refresh_groups(self):
        """刷新分组列表"""
        current_text = self.group_combo.currentText()
        # 合并保存的分组列表和从alarms中提取的分组
        groups = set(self.groups_list)
        for alarm in self.alarms:
            group = alarm.get("group", "默认")
            groups.add(group)
        
        # 更新保存的分组列表（添加新发现的分组）
        self.groups_list = sorted(groups)
        if "默认" in self.groups_list:
            self.groups_list.remove("默认")
            self.groups_list.insert(0, "默认")
        
        self.group_combo.clear()
        self.group_combo.addItem("全部分组")
        self.group_combo.addItems(self.groups_list)
        
        if current_text and current_text in [self.group_combo.itemText(i) for i in range(self.group_combo.count())]:
            self.group_combo.setCurrentText(current_text)
    
    def _refresh_table(self):
        """刷新表格"""
        # 过滤分组
        selected_group = self.group_combo.currentText()
        filtered_alarms = self.alarms
        if selected_group != "全部分组":
            filtered_alarms = [a for a in self.alarms if a.get("group", "默认") == selected_group]
        
        # 排序
        sort_text = self.sort_combo.currentText()
        if "创建日期" in sort_text:
            reverse = "↓" in sort_text
            filtered_alarms = sorted(filtered_alarms, key=lambda x: x.get("created_time", 0), reverse=reverse)
        elif "时间" in sort_text:
            reverse = "↓" in sort_text
            filtered_alarms = sorted(filtered_alarms, key=lambda x: x.get("time", ""), reverse=reverse)
        
        self.table.setRowCount(len(filtered_alarms))
        
        for row, alarm in enumerate(filtered_alarms):
            # 复选框
            checkbox = QTableWidgetItem()
            checkbox.setCheckState(Qt.CheckState.Unchecked)
            self.table.setItem(row, 0, checkbox)
            
            # 频率
            loop_type = alarm.get("loop_type", "once")
            loop_map = {
                "once": "一次",
                "daily": "每天",
                "weekly": "每周",
                "monthly": "每月",
                "yearly": "每年",
                "interval": "间隔",
            }
            self.table.setItem(row, 1, QTableWidgetItem(loop_map.get(loop_type, "一次")))
            
            # 日期
            date_str = alarm.get("date", "")
            if loop_type == "daily":
                date_str = "每天"
            elif loop_type == "weekly":
                # 计算星期几
                try:
                    date_obj = datetime.fromisoformat(date_str)
                    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
                    weekday = date_obj.weekday()
                    date_str = weekdays[weekday]
                except:
                    pass
            self.table.setItem(row, 2, QTableWidgetItem(date_str))
            
            # 时间
            time_str = alarm.get("time", "")
            self.table.setItem(row, 3, QTableWidgetItem(time_str))
            
            # 任务标签
            label = alarm.get("label", "闹钟任务")
            self.table.setItem(row, 4, QTableWidgetItem(label))
            
            # 剩余时间
            remaining = self._calculate_remaining(alarm)
            self.table.setItem(row, 5, QTableWidgetItem(remaining))
            
            # 状态（开关）
            status_item = QTableWidgetItem("开启" if alarm.get("enabled", True) else "关闭")
            status_item.setData(Qt.ItemDataRole.UserRole, alarm.get("id"))
            self.table.setItem(row, 6, status_item)
        
        self.table.resizeColumnsToContents()
    
    def _calculate_remaining(self, alarm: Dict) -> str:
        """计算剩余时间"""
        try:
            time_str = alarm.get("time", "")
            if not time_str:
                return ""
            
            now = datetime.now()
            alarm_time = datetime.strptime(time_str, "%H:%M:%S").time()
            alarm_datetime = datetime.combine(now.date(), alarm_time)
            
            loop_type = alarm.get("loop_type", "once")
            
            if loop_type == "daily":
                if alarm_datetime <= now:
                    alarm_datetime += timedelta(days=1)
            elif loop_type == "once":
                date_str = alarm.get("date", "")
                if date_str:
                    try:
                        alarm_date = datetime.fromisoformat(date_str).date()
                        alarm_datetime = datetime.combine(alarm_date, alarm_time)
                    except:
                        pass
            
            if alarm_datetime > now:
                delta = alarm_datetime - now
                total_seconds = int(delta.total_seconds())
                if total_seconds < 3600:
                    minutes = total_seconds // 60
                    return f"{minutes}分钟"
                elif total_seconds < 86400:
                    hours = total_seconds // 3600
                    return f"{hours}小时"
                else:
                    days = total_seconds // 86400
                    return f"{days}天"
            else:
                return "已过期"
        except Exception:
            return ""
    
    def _setup_alarm_checker(self):
        """设置闹钟检查定时器"""
        self.check_timer = QTimer(self)
        self.check_timer.timeout.connect(self._check_alarms)
        self.check_timer.start(1000)  # 每秒检查一次
    
    def _setup_refresh_timer(self):
        """设置剩余时间刷新定时器"""
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._refresh_remaining_time)
        self.refresh_timer.start(60000)  # 每分钟刷新一次剩余时间
    
    def _refresh_remaining_time(self):
        """只刷新剩余时间列"""
        for row in range(self.table.rowCount()):
            alarm_id = self.table.item(row, 6).data(Qt.ItemDataRole.UserRole)
            if alarm_id:
                alarm = next((a for a in self.alarms if a.get("id") == alarm_id), None)
                if alarm:
                    remaining = self._calculate_remaining(alarm)
                    self.table.setItem(row, 5, QTableWidgetItem(remaining))
    
    def _check_alarms(self):
        """检查并触发闹钟"""
        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")
        current_date = now.date()
        
        for alarm in self.alarms:
            if not alarm.get("enabled", True):
                continue
            
            alarm_time = alarm.get("time", "")
            if not alarm_time:
                continue
            
            loop_type = alarm.get("loop_type", "once")
            
            should_trigger = False
            
            if loop_type == "daily":
                # 每天：只要时间匹配就触发
                if alarm_time[:5] == current_time[:5]:  # 只比较时和分
                    should_trigger = True
            elif loop_type == "once":
                # 一次：日期和时间都要匹配
                date_str = alarm.get("date", "")
                if date_str:
                    try:
                        alarm_date = datetime.fromisoformat(date_str).date()
                        if alarm_date == current_date and alarm_time[:5] == current_time[:5]:
                            should_trigger = True
                    except:
                        pass
            elif loop_type == "weekly":
                # 每周：检查星期几
                date_str = alarm.get("date", "")
                if date_str:
                    try:
                        alarm_date = datetime.fromisoformat(date_str).date()
                        if alarm_date.weekday() == current_date.weekday() and alarm_time[:5] == current_time[:5]:
                            should_trigger = True
                    except:
                        pass
            
            if should_trigger:
                # 检查是否已经触发过（避免重复触发）
                # 使用 HH:MM 格式进行比较，避免秒级重复触发
                current_time_minute = current_time[:5]  # HH:MM
                last_trigger = alarm.get("last_trigger_time", "")
                last_trigger_minute = last_trigger[:5] if last_trigger else ""
                
                if last_trigger_minute != current_time_minute:
                    # 在触发前先更新 last_trigger_time，防止重复触发
                    # 使用完整时间（包含秒），确保在这一分钟内不会再次触发
                    alarm["last_trigger_time"] = current_time
                    self._save_alarms()
                    # 触发闹钟
                    self._trigger_alarm(alarm)
    
    def _trigger_alarm(self, alarm: Dict):
        """触发闹钟"""
        # 使用新的闹钟提醒对话框（对话框内部会处理声音播放）
        dialog = AlarmNotificationDialog(alarm, self)
        dialog.exec()
    
    def on_new_alarm(self):
        """新建闹钟"""
        # 获取当前选中的分组
        current_group = self.group_combo.currentText() if hasattr(self, 'group_combo') else None
        dialog = AlarmDialog(self, default_group=current_group)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            alarm_data = dialog.get_alarm_data()
            self.alarms.append(alarm_data)
            self._save_alarms()
            self._refresh_groups()
            self._refresh_table()

    def on_batch_add_alarm(self):
        """批量添加闹钟"""
        current_group = self.group_combo.currentText()
        if not current_group or current_group == "全部分组":
            current_group = "默认"
        dialog = BatchAlarmDialog(self.groups_list, current_group, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_alarms = dialog.get_created_alarms()
            if new_alarms:
                self.alarms.extend(new_alarms)
                self._save_alarms()
                self._refresh_groups()
                self._refresh_table()
                QMessageBox.information(self, "成功", f"已添加 {len(new_alarms)} 个闹钟")
    
    def on_modify_alarm(self):
        """修改闹钟"""
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(self, "提示", "请先选择要修改的闹钟")
            return
        
        row = selected_rows[0].row()
        alarm_id = self.table.item(row, 6).data(Qt.ItemDataRole.UserRole)
        alarm = next((a for a in self.alarms if a.get("id") == alarm_id), None)
        
        if not alarm:
            return
        
        dialog = AlarmDialog(self, alarm)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            updated_data = dialog.get_alarm_data()
            alarm.update(updated_data)
            self._save_alarms()
            self._refresh_groups()
            self._refresh_table()
    
    def on_delete_alarm(self):
        """删除闹钟到回收站（支持复选框和行选择）"""
        # 先检查复选框选择的项
        ids_to_delete = []
        alarms_to_move = []
        
        for row in range(self.table.rowCount()):
            checkbox_item = self.table.item(row, 0)
            if checkbox_item and checkbox_item.checkState() == Qt.CheckState.Checked:
                alarm_id = self.table.item(row, 6).data(Qt.ItemDataRole.UserRole)
                if alarm_id:
                    ids_to_delete.append(alarm_id)
                    alarm = next((a for a in self.alarms if a.get("id") == alarm_id), None)
                    if alarm:
                        alarm["deleted_time"] = time.time()
                        alarms_to_move.append(alarm)
        
        # 如果没有复选框选择，检查行选择
        if not ids_to_delete:
            selected_rows = self.table.selectionModel().selectedRows()
            if not selected_rows:
                QMessageBox.warning(self, "提示", "请先勾选或选择要删除的闹钟")
                return
            
            for row_index in [r.row() for r in selected_rows]:
                alarm_id = self.table.item(row_index, 6).data(Qt.ItemDataRole.UserRole)
                if alarm_id and alarm_id not in ids_to_delete:
                    ids_to_delete.append(alarm_id)
                    alarm = next((a for a in self.alarms if a.get("id") == alarm_id), None)
                    if alarm:
                        alarm["deleted_time"] = time.time()
                        alarms_to_move.append(alarm)
        
        if not ids_to_delete:
            QMessageBox.warning(self, "提示", "请先勾选或选择要删除的闹钟")
            return
        
        if QMessageBox.question(self, "确认", f"确定要删除 {len(ids_to_delete)} 个闹钟吗？\n（可到回收站恢复）") != QMessageBox.StandardButton.Yes:
            return
        
        # 移到回收站
        self.deleted_alarms.extend(alarms_to_move)
        self.alarms = [a for a in self.alarms if a.get("id") not in ids_to_delete]
        self._save_alarms()
        self._refresh_table()
    
    def on_clear_alarms(self):
        """清空所有闹钟"""
        if QMessageBox.question(self, "确认", "确定要清空所有闹钟吗？") != QMessageBox.StandardButton.Yes:
            return
        self.alarms = []
        self._save_alarms()
        self._refresh_table()
    
    def on_table_double_clicked(self, item: QTableWidgetItem):
        """双击表格项，修改闹钟"""
        if item.column() != 6:  # 不是状态列
            self.on_modify_alarm()
    
    def on_table_cell_clicked(self, row: int, col: int):
        """点击表格单元格"""
        if col == 6:  # 状态列
            alarm_id = self.table.item(row, 6).data(Qt.ItemDataRole.UserRole)
            alarm = next((a for a in self.alarms if a.get("id") == alarm_id), None)
            if alarm:
                # 切换状态
                alarm["enabled"] = not alarm.get("enabled", True)
                self._save_alarms()
                self._refresh_table()
    
    def on_recycle_bin(self):
        """打开回收站"""
        dialog = RecycleBinDialog(self.deleted_alarms, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 恢复的闹钟
            restored_ids = dialog.get_restored_ids()
            if restored_ids:
                restored = [a for a in self.deleted_alarms if a.get("id") in restored_ids]
                self.alarms.extend(restored)
                self.deleted_alarms = [a for a in self.deleted_alarms if a.get("id") not in restored_ids]
            
            # 永久删除的闹钟
            deleted_ids = dialog.get_deleted_ids()
            if deleted_ids:
                self.deleted_alarms = [a for a in self.deleted_alarms if a.get("id") not in deleted_ids]
            
            if restored_ids or deleted_ids:
                self._save_alarms()
                self._refresh_table()
    
    def on_edit_groups(self):
        """编辑分组"""
        dialog = GroupEditDialog(self.alarms, self, self.groups_list)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 更新所有闹钟的分组信息
            group_changes = dialog.get_group_changes()
            for alarm in self.alarms:
                old_group = alarm.get("group", "默认")
                if old_group in group_changes:
                    alarm["group"] = group_changes[old_group]
            
            # 删除已删除的分组
            deleted_groups = dialog.get_deleted_groups()
            if deleted_groups:
                default_group = "默认"
                for alarm in self.alarms:
                    if alarm.get("group") in deleted_groups:
                        alarm["group"] = default_group
                # 从保存的分组列表中删除
                self.groups_list = [g for g in self.groups_list if g not in deleted_groups]
            
            # 保存新添加的分组列表
            new_groups = dialog.get_all_groups()
            self.groups_list = new_groups.copy()
            # 确保"默认"分组在第一位
            if "默认" in self.groups_list:
                self.groups_list.remove("默认")
                self.groups_list.insert(0, "默认")
            else:
                self.groups_list.insert(0, "默认")
            
            self._save_alarms()
            self._refresh_groups()
            self._refresh_table()
            QMessageBox.information(self, "成功", "分组已保存")


class ItemValueDialog(QDialog):
    """物品收益录入对话框"""

    def __init__(self, item_info: Dict, parent=None):
        super().__init__(parent)
        self.item_info = item_info
        self.setWindowTitle(f"记录物品收益 - {item_info['name']}")
        self.setModal(True)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(1, 9999)
        self.qty_spin.setValue(1)

        self.price_spin = QDoubleSpinBox()
        self.price_spin.setRange(0.0, 999999.0)
        self.price_spin.setDecimals(2)
        self.price_spin.setSingleStep(0.5)
        default_price = item_info.get("default_price")
        if default_price is not None:
            self.price_spin.setValue(default_price)
        form.addRow("数量：", self.qty_spin)
        form.addRow("单价（万）：", self.price_spin)

        self.remark_edit = QLineEdit()
        self.remark_edit.setPlaceholderText("可填写掉落说明或买家信息")
        form.addRow("备注：", self.remark_edit)

        layout.addLayout(form)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_result(self) -> Dict:
        return {
            "name": self.item_info["name"],
            "quantity": self.qty_spin.value(),
            "unit_price": round(self.price_spin.value(), 2),
            "remark": self.remark_edit.text().strip(),
        }


class ProfitLedgerTab(QWidget):
    """梦幻西游收益记账本"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.records: List[Dict] = []
        self.base_info_fields: Dict[str, QLineEdit] = {}
        self.stat_labels: Dict[str, QLabel] = {}
        self.elapsed_seconds = 0
        self.timer_start_time: Optional[float] = None

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._update_duration)

        self._build_ui()
        self._load_ledger_data()

    # ----- UI 构建 -----
    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        top_layout = QHBoxLayout()
        top_layout.addWidget(self._build_base_info_box())
        top_layout.addWidget(self._build_stat_box())
        top_layout.setStretch(0, 3)
        top_layout.setStretch(1, 2)
        main_layout.addLayout(top_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_item_panel())
        splitter.addWidget(self._build_record_panel())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        main_layout.addWidget(splitter, stretch=1)

    def _build_base_info_box(self) -> QGroupBox:
        group = QGroupBox("基础信息")
        form = QFormLayout()

        field_configs = [
            ("online_role", "在线角色"),
            ("start_fund", "启动资金（万）"),
            ("end_fund", "结束资金（万）"),
            ("server_rate", "本区比例"),
            ("point_price", "点卡单价（万）"),
            ("card_count", "购买点数"),
        ]

        for key, label in field_configs:
            edit = QLineEdit()
            edit.setPlaceholderText("可选")
            edit.editingFinished.connect(self._on_base_info_changed)
            form.addRow(f"{label}：", edit)
            self.base_info_fields[key] = edit

        group.setLayout(form)
        return group

    def _build_stat_box(self) -> QGroupBox:
        group = QGroupBox("收益统计")
        layout = QVBoxLayout()

        duration_layout = QHBoxLayout()
        self.duration_value_label = QLabel("00时00分00秒")
        duration_layout.addWidget(QLabel("在线时长："))
        duration_layout.addWidget(self.duration_value_label)
        duration_layout.addStretch()
        layout.addLayout(duration_layout)

        button_row = QHBoxLayout()
        self.start_timer_button = QPushButton("开始计时")
        self.reset_timer_button = QPushButton("重新计时")
        self.start_timer_button.clicked.connect(self._on_start_timer_clicked)
        self.reset_timer_button.clicked.connect(self._on_reset_timer_clicked)
        button_row.addWidget(self.start_timer_button)
        button_row.addWidget(self.reset_timer_button)
        button_row.addStretch()
        layout.addLayout(button_row)

        stats = [
            ("card_cost", "消耗点卡"),
            ("gain_gold", "获得金钱"),
            ("item_profit", "物品收益"),
            ("net_profit", "扣除点卡后收益"),
            ("ratio_profit", "比例转化后收益"),
        ]

        for key, label in stats:
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{label}："))
            value_label = QLabel("0 万")
            value_label.setStyleSheet("font-weight: bold;")
            row.addWidget(value_label)
            row.addStretch()
            layout.addLayout(row)
            self.stat_labels[key] = value_label

        group.setLayout(layout)
        return group

    def _build_item_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(8)

        for group_info in PROFIT_ITEM_GROUPS:
            box = QGroupBox(group_info["name"])
            grid = QGridLayout()
            grid.setSpacing(6)
            for idx, item in enumerate(group_info["items"]):
                button = QPushButton(item["name"])
                button.setMinimumWidth(90)
                button.clicked.connect(partial(self._on_item_clicked, item))
                row = idx // 4
                col = idx % 4
                grid.addWidget(button, row, col)
            box.setLayout(grid)
            layout.addWidget(box)

        self.custom_add_button = QPushButton("添加自定义物品")
        self.custom_add_button.clicked.connect(self._on_custom_add_clicked)
        layout.addWidget(self.custom_add_button)
        layout.addStretch()

        return widget

    def _build_record_panel(self) -> QWidget:
        widget = QWidget()
        vbox = QVBoxLayout(widget)

        header_layout = QHBoxLayout()
        header_label = QLabel("今日战绩")
        header_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()

        self.clear_button = QPushButton("清零")
        self.clear_button.clicked.connect(self._clear_all_records)
        header_layout.addWidget(self.clear_button)
        vbox.addLayout(header_layout)

        self.records_table = QTableWidget(0, 5)
        self.records_table.setHorizontalHeaderLabels(["物品", "数量", "单价（万）", "总计（万）", "备注"])
        self.records_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.records_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.records_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.records_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.records_table.customContextMenuRequested.connect(self._on_records_menu)
        vbox.addWidget(self.records_table, stretch=1)

        summary_layout = QHBoxLayout()
        self.record_count_label = QLabel("共 0 条记录")
        summary_layout.addWidget(self.record_count_label)
        summary_layout.addStretch()
        self.total_value_label = QLabel("今日收益：0 万")
        self.total_value_label.setStyleSheet("font-weight: bold;")
        summary_layout.addWidget(self.total_value_label)
        vbox.addLayout(summary_layout)

        return widget

    # ----- 数据操作 -----
    def _load_ledger_data(self):
        if os.path.exists(LEDGER_DATA_FILE):
            try:
                with open(LEDGER_DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        else:
            data = {}

        base_info = data.get("base_info", {})
        for key, field in self.base_info_fields.items():
            field.setText(base_info.get(key, ""))

        self.records = data.get("records", [])
        self.elapsed_seconds = data.get("elapsed_seconds", 0)
        self._refresh_records_table()
        self._update_duration_label()
        self._update_summary()

    def _save_ledger_data(self):
        data = {
            "base_info": self._collect_base_info(),
            "records": self.records,
            "elapsed_seconds": self.elapsed_seconds,
        }
        try:
            os.makedirs(os.path.dirname(LEDGER_DATA_FILE), exist_ok=True)
            with open(LEDGER_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            print(f"保存收益记录失败: {exc}")

    def _collect_base_info(self) -> Dict[str, str]:
        return {key: field.text().strip() for key, field in self.base_info_fields.items()}

    def _refresh_records_table(self):
        self.records_table.setRowCount(0)
        for record in self.records:
            self._append_record_row(record)

    def _append_record_row(self, record: Dict):
        row = self.records_table.rowCount()
        self.records_table.insertRow(row)
        self.records_table.setItem(row, 0, QTableWidgetItem(record["name"]))
        self.records_table.setItem(row, 1, QTableWidgetItem(str(record["quantity"])))
        self.records_table.setItem(row, 2, QTableWidgetItem(f"{record['unit_price']:.2f}"))
        self.records_table.setItem(row, 3, QTableWidgetItem(f"{record['total']:.2f}"))
        self.records_table.setItem(row, 4, QTableWidgetItem(record.get("remark", "")))

    def _update_summary(self):
        total_value = sum(record.get("total", 0) for record in self.records)
        record_count = len(self.records)
        self.total_value_label.setText(f"今日收益：{total_value:.2f} 万")
        self.record_count_label.setText(f"共 {record_count} 条记录")

        card_cost = self._calculate_card_cost()
        server_rate = self._safe_float(self.base_info_fields["server_rate"].text() or "1", default=1.0)
        net_profit = total_value - card_cost
        ratio_profit = net_profit * server_rate

        self.stat_labels["card_cost"].setText(f"{card_cost:.2f} 万")
        self.stat_labels["gain_gold"].setText(f"{total_value:.2f} 万")
        self.stat_labels["item_profit"].setText(f"{total_value:.2f} 万")
        self.stat_labels["net_profit"].setText(f"{net_profit:.2f} 万")
        self.stat_labels["ratio_profit"].setText(f"{ratio_profit:.2f} 万")

    def _calculate_card_cost(self) -> float:
        price = self._safe_float(self.base_info_fields["point_price"].text())
        count = self._safe_float(self.base_info_fields["card_count"].text())
        return price * count

    @staticmethod
    def _safe_float(text: str, default: float = 0.0) -> float:
        try:
            return float(text or 0)
        except ValueError:
            return default

    # ----- 事件处理 -----
    def _on_item_clicked(self, item_data: Dict):
        dialog = ItemValueDialog(item_data, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = dialog.get_result()
            record = {
                **result,
                "total": round(result["quantity"] * result["unit_price"], 2),
            }
            self.records.append(record)
            self._append_record_row(record)
            self._update_summary()
            self._save_ledger_data()

    def _on_custom_add_clicked(self):
        name, ok = QInputDialog.getText(self, "自定义物品", "请输入物品名称：")
        if not ok:
            return
        name = name.strip()
        if not name:
            QMessageBox.warning(self, "提示", "物品名称不能为空")
            return
        item = {"name": name, "default_price": 0}
        self._on_item_clicked(item)

    def _on_records_menu(self, pos):
        selected_rows = {index.row() for index in self.records_table.selectedIndexes()}
        if not selected_rows:
            return
        menu = QMenu(self)
        delete_action = menu.addAction("删除选中")
        action = menu.exec(self.records_table.viewport().mapToGlobal(pos))
        if action == delete_action:
            self._remove_selected_records()

    def _remove_selected_records(self):
        rows = sorted({index.row() for index in self.records_table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        for row in rows:
            if 0 <= row < len(self.records):
                self.records.pop(row)
                self.records_table.removeRow(row)
        self._update_summary()
        self._save_ledger_data()

    def _clear_all_records(self):
        if QMessageBox.question(self, "确认", "确定要清空今日战绩吗？") != QMessageBox.StandardButton.Yes:
            return
        self.records = []
        self.records_table.setRowCount(0)
        self._update_summary()
        self._save_ledger_data()

    def _on_base_info_changed(self):
        self._update_summary()
        self._save_ledger_data()

    def _on_start_timer_clicked(self):
        if self.timer.isActive():
            self.timer.stop()
            self.elapsed_seconds = max(int(time.time() - self.timer_start_time), 0)
            self.start_timer_button.setText("开始计时")
            self._save_ledger_data()
            return

        self.timer_start_time = time.time() - self.elapsed_seconds
        self.timer.start()
        self.start_timer_button.setText("暂停计时")

    def _on_reset_timer_clicked(self):
        self.timer.stop()
        self.elapsed_seconds = 0
        self.timer_start_time = None
        self.start_timer_button.setText("开始计时")
        self._update_duration_label()
        self._save_ledger_data()

    def _update_duration(self):
        if self.timer_start_time is None:
            return
        self.elapsed_seconds = int(time.time() - self.timer_start_time)
        self._update_duration_label()

    def _update_duration_label(self):
        hours = self.elapsed_seconds // 3600
        minutes = (self.elapsed_seconds % 3600) // 60
        seconds = self.elapsed_seconds % 60
        self.duration_value_label.setText(f"{hours:02d}时{minutes:02d}分{seconds:02d}秒")


class VideoPlayerTab(QWidget):
    """本地视频播放器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.playlist: List[str] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        top_controls = QHBoxLayout()
        self.add_button = QPushButton("添加视频")
        self.remove_button = QPushButton("移除选中")
        self.clear_button = QPushButton("清空列表")
        self.play_button = QPushButton("播放")
        self.pause_button = QPushButton("暂停")
        self.stop_button = QPushButton("停止")
        top_controls.addWidget(self.add_button)
        top_controls.addWidget(self.remove_button)
        top_controls.addWidget(self.clear_button)
        top_controls.addStretch()
        top_controls.addWidget(self.play_button)
        top_controls.addWidget(self.pause_button)
        top_controls.addWidget(self.stop_button)
        layout.addLayout(top_controls)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.playlist_widget = QListWidget()
        splitter.addWidget(self.playlist_widget)

        video_container = QWidget()
        video_layout = QVBoxLayout(video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        self.video_widget = QVideoWidget()
        self.video_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        video_layout.addWidget(self.video_widget, stretch=1)

        slider_layout = QHBoxLayout()
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderMoved.connect(self._on_slider_moved)
        self.position_label = QLabel("00:00 / 00:00")
        slider_layout.addWidget(self.position_slider)
        slider_layout.addWidget(self.position_label)
        video_layout.addLayout(slider_layout)

        volume_layout = QHBoxLayout()
        volume_layout.addWidget(QLabel("音量："))
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        volume_layout.addWidget(self.volume_slider)
        video_layout.addLayout(volume_layout)

        splitter.addWidget(video_container)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, stretch=1)

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        self.player.setVideoOutput(self.video_widget)
        self.audio_output.setVolume(self.volume_slider.value() / 100)

        self.add_button.clicked.connect(self.on_add_files)
        self.remove_button.clicked.connect(self.on_remove_selected)
        self.clear_button.clicked.connect(self.on_clear_list)
        self.play_button.clicked.connect(self.on_play)
        self.pause_button.clicked.connect(self.player.pause)
        self.stop_button.clicked.connect(self.player.stop)
        self.playlist_widget.itemDoubleClicked.connect(lambda _: self.on_play())
        self.video_widget.installEventFilter(self)
        self.volume_slider.valueChanged.connect(lambda v: self.audio_output.setVolume(v / 100))
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.player.errorOccurred.connect(self._on_media_error)

    def on_add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择视频文件",
            "",
            "视频文件 (*.mp4 *.mkv *.avi *.mov *.flv *.ts *.m3u8 *.webm);;所有文件 (*)",
        )
        for path in files:
            if path not in self.playlist:
                self.playlist.append(path)
                self.playlist_widget.addItem(path)

    def on_remove_selected(self):
        for item in self.playlist_widget.selectedItems():
            row = self.playlist_widget.row(item)
            self.playlist_widget.takeItem(row)
            if 0 <= row < len(self.playlist):
                self.playlist.pop(row)

    def on_clear_list(self):
        self.playlist.clear()
        self.playlist_widget.clear()

    def _current_path(self) -> Optional[str]:
        item = self.playlist_widget.currentItem()
        if not item and self.playlist_widget.count() > 0:
            item = self.playlist_widget.item(0)
            self.playlist_widget.setCurrentRow(0)
        if item:
            return item.text()
        return None

    def on_play(self):
        path = self._current_path()
        if not path:
            QMessageBox.information(self, "提示", "请先添加并选中一个视频文件")
            return
        path_lower = path.lower()
        if path_lower.endswith(".m3u8") or path_lower.startswith("http"):
            target_url = QUrl(path)
        else:
            target_url = QUrl.fromLocalFile(path)

        current_source = self.player.source()
        playback_state = self.player.playbackState()

        if current_source == target_url and playback_state == QMediaPlayer.PlaybackState.PausedState:
            self.player.play()
            return

        self.player.setSource(target_url)
        self.player.play()

    def toggle_play_pause(self):
        state = self.player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.player.play()
        else:
            self.on_play()

    def seek_by_offset(self, delta_ms: int):
        duration = self.player.duration()
        if duration <= 0:
            return
        target = self.player.position() + delta_ms
        target = max(0, min(duration, target))
        self.player.setPosition(target)

    def _on_slider_moved(self, position: int):
        self.player.setPosition(position)

    def _format_ms(self, ms: int) -> str:
        seconds = ms // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        hours = minutes // 60
        minutes = minutes % 60
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _on_position_changed(self, position: int):
        if not self.position_slider.isSliderDown():
            self.position_slider.setValue(position)
        duration = self.player.duration()
        self.position_label.setText(f"{self._format_ms(position)} / {self._format_ms(duration or 0)}")

    def _on_duration_changed(self, duration: int):
        self.position_slider.setRange(0, duration)
        self.position_label.setText(f"00:00 / {self._format_ms(duration or 0)}")

    def _on_media_status(self, status: QMediaPlayer.MediaStatus):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            current_row = self.playlist_widget.currentRow()
            if current_row + 1 < self.playlist_widget.count():
                self.playlist_widget.setCurrentRow(current_row + 1)
                self.on_play()

    def _on_media_error(self, error: QMediaPlayer.Error, message: str):
        if error != QMediaPlayer.Error.NoError:
            QMessageBox.warning(self, "播放错误", message or "无法播放该视频文件")

    def eventFilter(self, source, event):
        if source is self.video_widget:
            if event.type() == event.Type.MouseButtonPress:
                self.toggle_play_pause()
                return True
            if event.type() == event.Type.KeyPress:
                if event.key() == Qt.Key.Key_Space:
                    self.toggle_play_pause()
                    return True
                if event.key() == Qt.Key.Key_Left:
                    self.seek_by_offset(-5000)
                    return True
                if event.key() == Qt.Key.Key_Right:
                    self.seek_by_offset(5000)
                    return True
        return super().eventFilter(source, event)


class TransferContext:
    def __init__(self, root_dir: str, log_callback=None, text_callback=None, client_callback=None):
        self.root_dir = root_dir
        self.log_callback = log_callback
        self.text_callback = text_callback
        self.client_callback = client_callback
        self.text_message = ""
        self.connected_clients = set()

    def log(self, message: str):
        if self.log_callback:
            self.log_callback(message)

    def update_text(self, message: str):
        self.text_message = message
        if self.text_callback:
            self.text_callback(message)

    def register_client(self, ip: str):
        if ip not in self.connected_clients:
            self.connected_clients.add(ip)
            if self.client_callback:
                self.client_callback(len(self.connected_clients))


class TransferRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, request, client_address, server, directory=None):
        self.context = getattr(server, "context", None)
        directory = directory or (self.context.root_dir if self.context else None)
        super().__init__(request, client_address, server, directory=directory)

    def log_message(self, format, *args):
        if self.context:
            self.context.log(format % args)
            # 记录客户端IP
            if hasattr(self, 'client_address'):
                self.context.register_client(self.client_address[0])

    def _render_home(self):
        context = self.context
        files = []
        try:
            files = os.listdir(context.root_dir)
        except Exception as exc:
            context.log(f"读取目录失败: {exc}")
        file_rows = ""
        for name in sorted(files):
            path = os.path.join(context.root_dir, name)
            if os.path.isfile(path):
                size_kb = os.path.getsize(path) / 1024
                file_rows += f"<tr><td>{name}</td><td>{size_kb:.1f} KB</td><td><a href='/download?name={name}'>下载</a></td></tr>"
        html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>互传文件</title>
  <style>
    body {{ font-family: Arial, sans-serif; padding: 20px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    th {{ background:#f4f4f4; }}
    textarea {{ width: 100%; height: 120px; }}
  </style>
</head>
<body>
  <h2>上传文件</h2>
  <form method="POST" action="/upload" enctype="multipart/form-data">
    <input type="file" name="file" />
    <button type="submit">上传</button>
  </form>
  <h2>文字便签</h2>
  <form method="POST" action="/text">
    <textarea name="content" placeholder="可在此粘贴文字">{context.text_message}</textarea>
    <button type="submit">提交</button>
  </form>
  <h2>文件列表</h2>
  <table>
    <tr><th>文件名</th><th>大小</th><th>操作</th></tr>
    {file_rows or "<tr><td colspan='3'>目录为空</td></tr>"}
  </table>
</body>
</html>
"""
        html_bytes = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html_bytes)))
        self.end_headers()
        self.wfile.write(html_bytes)

    def do_GET(self):
        if self.path.startswith("/download"):
            query = parse_qs(urlparse(self.path).query)
            name = query.get("name", [""])[0]
            safe_name = os.path.basename(name)
            file_path = os.path.join(self.context.root_dir, safe_name)
            if os.path.isfile(file_path):
                try:
                    with open(file_path, "rb") as f:
                        data = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Content-Disposition", f'attachment; filename="{safe_name}"')
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                except Exception as exc:
                    self.server.context.log(f"读取文件失败: {exc}")
            self.send_error(404, "文件不存在")
        else:
            self.directory = self.context.root_dir
            self._render_home()

    def do_POST(self):
        if self.path == "/upload":
            self._handle_upload()
        elif self.path == "/text":
            self._handle_text()
        else:
            self.send_error(404)

    def _handle_upload(self):
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self.send_error(400, "仅支持 multipart/form-data")
            return
        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": content_type},
        )
        file_item = form["file"] if "file" in form else None
        if file_item and file_item.filename:
            filename = os.path.basename(file_item.filename)
            target = os.path.join(self.context.root_dir, filename)
            with open(target, "wb") as f:
                f.write(file_item.file.read())
            self.context.log(f"上传文件：{filename}")
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

    def _handle_text(self):
        length = int(self.headers.get("Content-Length", "0"))
        data = self.rfile.read(length)
        message = data.decode("utf-8", errors="ignore")
        value = ""
        if "=" in message:
            value = unquote(message.split("=", 1)[1])
        self.context.update_text(value)
        self.context.log("更新便签内容")
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()


class FileTransferServer(threading.Thread):
    def __init__(self, host: str, port: int, root_dir: str, log_callback=None, text_callback=None, client_callback=None):
        super().__init__(daemon=True)
        self.context = TransferContext(root_dir, log_callback, text_callback, client_callback)
        handler = TransferRequestHandler
        self.httpd = ThreadingHTTPServer((host, port), handler)
        self.httpd.context = self.context

    def run(self):
        try:
            self.httpd.serve_forever()
        except Exception as exc:
            self.context.log(f"服务器异常：{exc}")

    def stop(self):
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except Exception:
            pass

    def update_root_dir(self, root_dir: str):
        self.context.root_dir = root_dir


class DailyBriefTab(QWidget):
    """每日简报界面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = DailyBriefManager()
        self.generator = DailyBriefGenerator()
        self.current_date = QDate.currentDate()

        self._build_ui()
        self._load_brief_for_date(self.current_date)

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        control_row = QHBoxLayout()
        control_row.addWidget(QLabel("查看日期："))
        self.date_edit = QDateEdit(self.current_date)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setCalendarPopup(True)
        self.date_edit.dateChanged.connect(self._on_date_changed)
        control_row.addWidget(self.date_edit)

        self.load_button = QPushButton("加载简报")
        self.load_button.clicked.connect(lambda: self._load_brief_for_date(self.date_edit.date()))
        control_row.addWidget(self.load_button)

        control_row.addStretch()

        self.generate_button = QPushButton("生成今日简报")
        self.generate_button.clicked.connect(self._on_generate_clicked)
        control_row.addWidget(self.generate_button)

        main_layout.addLayout(control_row)

        self.summary_label = QLabel("今日尚未生成简报")
        main_layout.addWidget(self.summary_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.brief_tree = QTreeWidget()
        self.brief_tree.setColumnCount(4)
        self.brief_tree.setHeaderLabels(["标题", "主题分类", "来源", "发布时间"])
        self.brief_tree.setRootIsDecorated(False)
        self.brief_tree.setAlternatingRowColors(True)
        self.brief_tree.itemSelectionChanged.connect(self._on_item_selected)
        self.brief_tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        splitter.addWidget(self.brief_tree)

        self.detail_tabs = QTabWidget()

        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.addWidget(QLabel("摘要详情："))
        self.detail_text = QPlainTextEdit()
        self.detail_text.setReadOnly(True)
        detail_layout.addWidget(self.detail_text)

        self.open_link_button = QPushButton("打开原帖链接")
        self.open_link_button.setEnabled(False)
        self.open_link_button.clicked.connect(self._on_open_link)
        detail_layout.addWidget(self.open_link_button)

        self.detail_tabs.addTab(detail_widget, "摘要")

        video_widget = QWidget()
        video_layout = QVBoxLayout(video_widget)
        video_layout.addWidget(QLabel("视频播放（可粘贴视频地址或文章链接）"))
        video_control = QHBoxLayout()
        self.video_url_edit = QLineEdit("https://")
        self.video_load_button = QPushButton("加载视频")
        self.video_from_record_button = QPushButton("用选中链接播放")
        self.video_from_record_button.setEnabled(False)
        video_control.addWidget(self.video_url_edit)
        video_control.addWidget(self.video_load_button)
        video_control.addWidget(self.video_from_record_button)
        video_layout.addLayout(video_control)
        self.video_status_label = QLabel("")
        video_layout.addWidget(self.video_status_label)
        self.video_view = QWebEngineView()
        video_layout.addWidget(self.video_view, stretch=1)
        self.detail_tabs.addTab(video_widget, "视频播放")

        splitter.addWidget(self.detail_tabs)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        self.video_load_button.clicked.connect(self._on_video_load_clicked)
        self.video_from_record_button.clicked.connect(self._on_load_record_video)

        main_layout.addWidget(splitter, stretch=1)

    # ----- 数据加载与显示 -----
    def _load_brief_for_date(self, qdate: QDate):
        date_str = qdate.toString("yyyy-MM-dd")
        brief = self.manager.get_brief(date_str)
        if not brief:
            self.summary_label.setText(f"{date_str} 暂无简报数据")
            self.brief_tree.clear()
            self.detail_text.clear()
            self.open_link_button.setEnabled(False)
            return
        self._apply_brief_to_ui(date_str, brief)

    def _apply_brief_to_ui(self, date_str: str, brief: Dict):
        items = brief.get("items", [])
        self.brief_tree.clear()
        for record in items:
            row = QTreeWidgetItem(
                [
                    record.get("title", ""),
                    record.get("category", ""),
                    record.get("source", ""),
                    self._format_time(record.get("published_at", "")),
                ]
            )
            row.setData(0, Qt.ItemDataRole.UserRole, record)
            self.brief_tree.addTopLevelItem(row)
        self.summary_label.setText(f"{date_str} 已生成 {len(items)} 条简报")
        self.detail_text.clear()
        self.open_link_button.setEnabled(False)
        self.brief_tree.resizeColumnToContents(0)

    def _format_time(self, text: str) -> str:
        if not text:
            return ""
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return dt.strftime("%m-%d %H:%M")
        except Exception:
            return text

    # ----- 交互 -----
    def _on_date_changed(self, qdate: QDate):
        self._load_brief_for_date(qdate)

    def _on_item_selected(self):
        selected = self.brief_tree.selectedItems()
        if not selected:
            self.detail_text.clear()
            self.open_link_button.setEnabled(False)
            self.video_from_record_button.setEnabled(False)
            return
        record = selected[0].data(0, Qt.ItemDataRole.UserRole)
        summary = record.get("summary", "")
        category = record.get("category", "未知主题")
        source = record.get("source", "未知来源")
        self.detail_text.setPlainText(f"[{category}] {summary}\n\n来源：{source}")
        self.open_link_button.setEnabled(bool(record.get("url")))
        self.video_from_record_button.setEnabled(bool(record.get("url")))

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        record = item.data(0, Qt.ItemDataRole.UserRole)
        url = record.get("url")
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _on_open_link(self):
        selected = self.brief_tree.selectedItems()
        if not selected:
            return
        record = selected[0].data(0, Qt.ItemDataRole.UserRole)
        url = record.get("url")
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _on_generate_clicked(self):
        self.generate_button.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
        try:
            brief = self.generator.generate_brief(min_items=30)
            date_str = QDate.currentDate().toString("yyyy-MM-dd")
            self.manager.save_brief(date_str, brief)
            self.date_edit.setDate(QDate.currentDate())
            self._apply_brief_to_ui(date_str, brief)
            QMessageBox.information(self, "完成", f"已生成 {brief.get('item_count', 0)} 条简报")
        finally:
            QApplication.restoreOverrideCursor()
            self.generate_button.setEnabled(True)

    def _on_video_load_clicked(self):
        url = self.video_url_edit.text().strip()
        self._load_video_url(url)

    def _on_load_record_video(self):
        selected = self.brief_tree.selectedItems()
        if not selected:
            QMessageBox.information(self, "提示", "请先选择一条资讯")
            return
        record = selected[0].data(0, Qt.ItemDataRole.UserRole)
        url = record.get("url", "")
        if not url:
            QMessageBox.information(self, "提示", "该条目没有可用链接")
            return
        self.video_url_edit.setText(url)
        self._load_video_url(url)

    def _load_video_url(self, url: str):
        if not url:
            self.video_status_label.setText("请输入视频地址")
            return
        if not (url.startswith("http://") or url.startswith("https://")):
            url = "https://" + url
            self.video_url_edit.setText(url)
        lower = url.lower()
        if lower.endswith((".mp4", ".webm", ".ogg")):
            mime = "video/mp4"
            if lower.endswith(".webm"):
                mime = "video/webm"
            elif lower.endswith(".ogg"):
                mime = "video/ogg"
            html = f"""
<!DOCTYPE html>
<html>
<body style="margin:0;background:#000;">
  <video controls autoplay style="width:100%;height:100%;" src="{url}" type="{mime}">
    您的浏览器不支持 HTML5 视频播放
  </video>
</body>
</html>
"""
            self.video_view.setHtml(html, QUrl(url))
            self.video_status_label.setText("正在播放本地/直链视频")
        elif lower.endswith(".m3u8"):
            html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <script src="https://cdn.jsdelivr.net/npm/hls.js@1.5.7"></script>
</head>
<body style="margin:0;background:#000;">
  <video id="player" controls autoplay style="width:100%;height:100%;"></video>
  <script>
    var video = document.getElementById('player');
    if (Hls.isSupported()) {{
      var hls = new Hls();
      hls.loadSource('{url}');
      hls.attachMedia(video);
    }} else if (video.canPlayType('application/vnd.apple.mpegurl')) {{
      video.src = '{url}';
    }} else {{
      document.body.innerHTML = '<div style="color:#fff;text-align:center;padding-top:20px;">当前环境不支持 m3u8 播放</div>';
    }}
  </script>
</body>
</html>
"""
            self.video_view.setHtml(html, QUrl(url))
            self.video_status_label.setText("正在通过 HLS 播放 m3u8 流")
        else:
            self.video_view.load(QUrl(url))
            self.video_status_label.setText(f"正在加载：{url}")


class FileTransferTab(QWidget):
    log_signal = pyqtSignal(str)
    text_signal = pyqtSignal(str)
    client_signal = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.server: Optional[FileTransferServer] = None
        self.shared_dir = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.exists(self.shared_dir):
            self.shared_dir = os.path.expanduser("~")
        self._build_ui()
        self.log_signal.connect(self._append_log)
        self.text_signal.connect(self._update_text_display)
        self.client_signal.connect(self._update_client_count)
        self._update_status()

    def _update_client_count(self, count: int):
        self.client_count_label.setText(f"在线设备：{count}")

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("共享目录："))
        self.dir_edit = QLineEdit(self.shared_dir)
        self.dir_edit.setReadOnly(True)
        self.choose_dir_button = QPushButton("选择目录")
        self.open_dir_button = QPushButton("打开目录")
        dir_layout.addWidget(self.dir_edit, stretch=1)
        dir_layout.addWidget(self.choose_dir_button)
        dir_layout.addWidget(self.open_dir_button)
        layout.addLayout(dir_layout)

        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel("端口："))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(9876)
        self.start_button = QPushButton("启动服务器")
        self.stop_button = QPushButton("停止")
        self.stop_button.setEnabled(False)
        
        self.qr_button = QPushButton("显示二维码")
        self.qr_button.clicked.connect(self.show_qr_code)
        self.qr_button.setEnabled(False)
        
        self.client_count_label = QLabel("在线设备：0")
        self.client_count_label.setStyleSheet("color: green; font-weight: bold;")

        control_layout.addWidget(self.port_spin)
        control_layout.addStretch()
        control_layout.addWidget(self.client_count_label)
        control_layout.addSpacing(20)
        control_layout.addWidget(self.start_button)
        control_layout.addWidget(self.stop_button)
        control_layout.addWidget(self.qr_button)
        layout.addLayout(control_layout)

        info_layout = QHBoxLayout()
        self.status_browser = QTextBrowser()
        self.status_browser.setMaximumHeight(140)
        info_layout.addWidget(self.status_browser, stretch=2)

        right_box = QGroupBox("手机操作提示")
        right_layout = QVBoxLayout(right_box)
        right_layout.addWidget(QLabel("1. 手机连接与电脑同一 Wi-Fi\n2. 浏览器输入上方提供的地址\n3. 可直接上传文件或粘贴文字"))
        layout.addLayout(info_layout)
        info_layout.addWidget(right_box, stretch=1)

        text_group = QGroupBox("最新文字便签")
        text_layout = QVBoxLayout(text_group)
        self.text_display = QPlainTextEdit()
        self.text_display.setReadOnly(True)
        self.copy_text_button = QPushButton("复制到剪贴板")
        text_layout.addWidget(self.text_display)
        text_layout.addWidget(self.copy_text_button, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addWidget(text_group)

        log_group = QGroupBox("传输日志")
        log_layout = QVBoxLayout(log_group)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        log_layout.addWidget(self.log_view)
        layout.addWidget(log_group, stretch=1)

        self.choose_dir_button.clicked.connect(self._choose_directory)
        self.open_dir_button.clicked.connect(self._open_directory)
        self.start_button.clicked.connect(self.start_server)
        self.stop_button.clicked.connect(self.stop_server)
        self.copy_text_button.clicked.connect(self._copy_text)

    def _choose_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "选择共享目录", self.shared_dir)
        if directory:
            self.shared_dir = directory
            self.dir_edit.setText(directory)
            if self.server:
                self.server.update_root_dir(directory)
            self._update_status()

    def _open_directory(self):
        if os.path.exists(self.shared_dir):
            os.startfile(self.shared_dir)

    def _append_log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{timestamp}] {message}")

    def _update_text_display(self, text: str):
        self.text_display.setPlainText(text)

    def _copy_text(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.text_display.toPlainText())
        QMessageBox.information(self, "提示", "已复制到剪贴板")

    def show_qr_code(self):
        """显示二维码"""
        if not self.server:
            return
            
        port = self.port_spin.value()
        urls = self._access_urls(port)
        if not urls:
            QMessageBox.warning(self, "提示", "未找到可用地址")
            return
            
        # 优先选择 192.168.x.x 的地址
        target_url = urls[0]
        for url in urls:
            if "192.168." in url and not url.endswith(".1"):
                 target_url = url
                 break
        
        try:
            # Check if qrcode and ImageQt are available
            try:
                import qrcode
                from PIL import ImageQt
                QRCODE_AVAILABLE = True
            except ImportError:
                QRCODE_AVAILABLE = False

            if not QRCODE_AVAILABLE:
                QMessageBox.warning(self, "提示", "未安装 qrcode 库，无法生成二维码")
                return
                
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(target_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            
            # 显示二维码对话框
            dialog = QDialog(self)
            dialog.setWindowTitle("扫码访问")
            dialog.resize(400, 450)
            vbox = QVBoxLayout(dialog)
            
            lbl = QLabel(f"请使用手机扫描下方二维码：\n{target_url}")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vbox.addWidget(lbl)
            
            img_lbl = QLabel()
            img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # Convert PIL image to QPixmap
            if img.mode == "1":
                img = img.convert("L")
            qim = ImageQt.ImageQt(img)
            pix = QPixmap.fromImage(qim)
            img_lbl.setPixmap(pix.scaled(300, 300, Qt.AspectRatioMode.KeepAspectRatio))
            vbox.addWidget(img_lbl)
            
            # 添加下拉框选择其他IP
            if len(urls) > 1:
                combo = QComboBox()
                combo.addItems(urls)
                combo.setCurrentText(target_url)
                def on_url_change(text):
                    qr = qrcode.QRCode(version=1, box_size=10, border=5)
                    qr.add_data(text)
                    qr.make(fit=True)
                    img = qr.make_image(fill_color="black", back_color="white")
                    if img.mode == "1":
                        img = img.convert("L")
                    qim = ImageQt.ImageQt(img)
                    pix = QPixmap.fromImage(qim)
                    img_lbl.setPixmap(pix.scaled(300, 300, Qt.AspectRatioMode.KeepAspectRatio))
                    lbl.setText(f"请使用手机扫描下方二维码：\n{text}")
                
                combo.currentTextChanged.connect(on_url_change)
                vbox.addWidget(QLabel("切换地址："))
                vbox.addWidget(combo)
            
            dialog.exec()
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "错误", f"生成二维码失败: {e}")

    def _update_status(self):
        status_lines = [
            f"共享目录：{self.shared_dir}",
        ]
        if self.server:
            status_lines.append(f"服务器运行中：端口 {self.port_spin.value()}")
            urls = self._access_urls(self.port_spin.value())
            if urls:
                status_lines.append("可在手机浏览器访问以下地址：")
                status_lines.extend(urls)
            self.qr_button.setEnabled(True)
        else:
            status_lines.append("服务器未启动")
            self.qr_button.setEnabled(False)
        self.status_browser.setText("\n".join(status_lines))

    def _access_urls(self, port: int) -> List[str]:
        urls = []
        try:
            hostname = socket.gethostname()
            hosts = socket.gethostbyname_ex(hostname)[2]
            for ip in hosts:
                if ip.startswith("127."):
                    continue
                urls.append(f"http://{ip}:{port}")
        except Exception:
            pass
        if not urls:
            urls.append(f"http://127.0.0.1:{port}")
        return urls

    def start_server(self):
        if self.server:
            QMessageBox.information(self, "提示", "服务器已在运行")
            return
        port = self.port_spin.value()
        try:
            self.server = FileTransferServer(
                "0.0.0.0",
                port,
                self.shared_dir,
                log_callback=self.log_signal.emit,
                text_callback=self.text_signal.emit,
                client_callback=self.client_signal.emit,
            )
            self.server.start()
            self.log_signal.emit(f"服务器已启动，端口 {port}")
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self._update_status()
        except OSError as exc:
            self.server = None
            QMessageBox.critical(self, "启动失败", f"无法启动服务器：{exc}")

    def stop_server(self):
        if self.server:
            self.server.stop()
            self.server = None
            self.log_signal.emit("服务器已停止")
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self._update_status()

    def _update_log_from_context(self, message: str):
        self.log_signal.emit(message)

    def closeEvent(self, event):
        self.stop_server()
        super().closeEvent(event)


class RegionSelector(QDialog):
    """区域选择器 - 全屏透明窗口，允许用户拖拽选择矩形区域"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_region = None  # (x, y, width, height)
        self.start_pos = None
        self.end_pos = None
        self.is_selecting = False
        
        # 设置窗口属性 - 全屏透明窗口，始终在最前面
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Dialog
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)
        # 使用 paintEvent 绘制背景
        
        # 获取屏幕尺寸并设置窗口大小
        screen = QApplication.primaryScreen()
        if screen:
            geometry = screen.geometry()
        else:
            # 备用方案：默认尺寸
            geometry = QRect(0, 0, 1920, 1080)
        self.setGeometry(geometry)
        
        # 添加提示标签
        self.hint_label = QLabel("拖拽鼠标选择识别区域，按 ESC 取消，按 Enter 确认", self)
        self.hint_label.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 180);
                color: white;
                padding: 10px;
                border-radius: 5px;
                font-size: 14px;
            }
        """)
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_label.setGeometry(geometry.x() + 20, geometry.y() + 20, 400, 40)
        self.hint_label.show()
    
    def showEvent(self, event):
        """窗口显示时确保在最前面"""
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        self.setFocus()
    
    def paintEvent(self, event):
        """绘制选择区域"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 始终绘制半透明遮罩
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
        
        if self.start_pos and self.end_pos:
            # 计算选择区域
            x1, y1 = self.start_pos.x(), self.start_pos.y()
            x2, y2 = self.end_pos.x(), self.end_pos.y()
            x = min(x1, x2)
            y = min(y1, y2)
            w = abs(x2 - x1)
            h = abs(y2 - y1)
            
            # 清除选择区域（显示原图）
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(x, y, w, h, Qt.GlobalColor.transparent)
            
            # 绘制选择框边框
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            pen = QPen(QColor(0, 150, 255), 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.drawRect(x, y, w, h)
            
            # 绘制四个角的标记
            corner_size = 10
            painter.fillRect(x - 1, y - 1, corner_size, 3, QColor(0, 150, 255))
            painter.fillRect(x - 1, y - 1, 3, corner_size, QColor(0, 150, 255))
            painter.fillRect(x + w - corner_size + 1, y - 1, corner_size, 3, QColor(0, 150, 255))
            painter.fillRect(x + w - 1, y - 1, 3, corner_size, QColor(0, 150, 255))
            painter.fillRect(x - 1, y + h - 1, corner_size, 3, QColor(0, 150, 255))
            painter.fillRect(x - 1, y + h - corner_size + 1, 3, corner_size, QColor(0, 150, 255))
            painter.fillRect(x + w - corner_size + 1, y + h - 1, corner_size, 3, QColor(0, 150, 255))
            painter.fillRect(x + w - 1, y + h - corner_size + 1, 3, corner_size, QColor(0, 150, 255))
    
    def mousePressEvent(self, event):
        """鼠标按下"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_pos = event.position().toPoint()
            self.end_pos = self.start_pos
            self.is_selecting = True
    
    def mouseMoveEvent(self, event):
        """鼠标移动"""
        if self.is_selecting:
            self.end_pos = event.position().toPoint()
            self.update()
    
    def mouseReleaseEvent(self, event):
        """鼠标释放"""
        if event.button() == Qt.MouseButton.LeftButton and self.is_selecting:
            self.end_pos = event.position().toPoint()
            self.is_selecting = False
            self.update()
    
    def keyPressEvent(self, event):
        """键盘事件"""
        if event.key() == Qt.Key.Key_Escape:
            # ESC 取消
            self.selected_region = None
            self.reject()
        elif event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            # Enter 确认
            if self.start_pos and self.end_pos:
                x1, y1 = self.start_pos.x(), self.start_pos.y()
                x2, y2 = self.end_pos.x(), self.end_pos.y()
                x = min(x1, x2)
                y = min(y1, y2)
                w = abs(x2 - x1)
                h = abs(y2 - y1)
                
                # 确保区域有效（至少 10x10 像素）
                if w >= 10 and h >= 10:
                    self.selected_region = (x, y, w, h)
                    self.accept()
                else:
                    QMessageBox.warning(self, "区域太小", "请选择一个至少 10x10 像素的区域")
            else:
                # 没有选择区域，使用全屏
                self.selected_region = None
                self.accept()
        else:
            super().keyPressEvent(event)


# 全局 OCR 锁（PaddleOCR 可能不支持多线程并发）
_ocr_global_lock = threading.Lock()

class OCRWorker(QThread):
    """OCR 处理工作线程"""
    finished_signal = pyqtSignal(list)  # 传递识别结果
    error_signal = pyqtSignal(str)  # 传递错误信息
    
    def __init__(self, ocr_engine, img_array):
        super().__init__()
        self.ocr_engine = ocr_engine
        self.img_array = img_array
        self._stop_flag = False  # 停止标志
    
    def stop(self):
        """请求停止（不强制终止）"""
        self._stop_flag = True
    
    def run(self):
        """在线程中执行 OCR 识别"""
        try:
            print(f"[OCRWorker] 开始 OCR 识别，图像尺寸: {self.img_array.shape}")
            
            # 检查停止标志
            if self._stop_flag:
                print("[OCRWorker] 收到停止请求，退出")
                return
            
            # 优化图像大小（如果太大，缩小以提高速度）
            img_to_process = self.img_array
            original_shape = img_to_process.shape
            # 缩小图像以大幅提高识别速度
            max_size = 800  # 最大尺寸（800px足够识别聊天文字，速度快）
            
            if img_to_process.shape[0] > max_size or img_to_process.shape[1] > max_size:
                # 缩小图像（减少日志输出）
                from PIL import Image
                pil_img = Image.fromarray(img_to_process)
                scale = min(max_size / img_to_process.shape[1], max_size / img_to_process.shape[0])
                new_width = int(img_to_process.shape[1] * scale)
                new_height = int(img_to_process.shape[0] * scale)
                # 使用BILINEAR而不是LANCZOS，速度更快
                pil_img = pil_img.resize((new_width, new_height), Image.Resampling.BILINEAR)
                img_to_process = np.array(pil_img)
            
            # 再次检查停止标志
            if self._stop_flag:
                print("[OCRWorker] 收到停止请求，退出")
                return
            
            print("[OCRWorker] 调用 OCR 引擎...")
            
            # 确保图像数组是连续的（PaddleOCR 要求）
            if not img_to_process.flags['C_CONTIGUOUS']:
                print("[OCRWorker] 图像数组不连续，转换为连续数组...")
                img_to_process = np.ascontiguousarray(img_to_process)
            
            # 确保数据类型正确（uint8）
            if img_to_process.dtype != np.uint8:
                print(f"[OCRWorker] 图像数据类型为 {img_to_process.dtype}，转换为 uint8...")
                if img_to_process.max() <= 1.0:
                    img_to_process = (img_to_process * 255).astype(np.uint8)
                else:
                    img_to_process = img_to_process.astype(np.uint8)
            
            print(f"[OCRWorker] 图像信息: shape={img_to_process.shape}, dtype={img_to_process.dtype}, contiguous={img_to_process.flags['C_CONTIGUOUS']}")
            
            # 使用 ocr 方法（在后台线程中执行，不会阻塞 UI）
            # 注意：虽然新版本推荐使用 predict，但 ocr 方法仍然可用
            # 如果遇到弃用警告，可以忽略，因为我们在后台线程中执行
            # 注意：PaddleOCR 可能不支持多线程并发，使用全局锁保护
            print("[OCRWorker] 获取 OCR 锁...")
            ocr_start_time = time.time()
            result = None
            try:
                with _ocr_global_lock:
                    print("[OCRWorker] OCR 锁已获取，开始调用 OCR 引擎...")
                    try:
                        # 优先使用 ocr 方法（更稳定，避免多线程问题）
                        # predict 方法在多线程环境下可能不稳定
                        print("[OCRWorker] 使用 ocr 方法（稳定版本）...")
                        result = self.ocr_engine.ocr(img_to_process)
                        
                        ocr_elapsed = time.time() - ocr_start_time
                        print(f"[OCRWorker] OCR 调用完成，耗时: {ocr_elapsed:.2f}秒")
                    except RuntimeError as e:
                        ocr_elapsed = time.time() - ocr_start_time
                        print(f"[OCRWorker] RuntimeError 发生，耗时: {ocr_elapsed:.2f}秒，错误: {e}")
                        # 如果是 RuntimeError，可能是多线程问题，尝试使用文件路径方式
                        if "Unknown exception" in str(e):
                            print("[OCRWorker] 检测到 RuntimeError，尝试使用临时文件方式...")
                            import tempfile
                            import os
                            # 保存为临时文件
                            temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
                            try:
                                from PIL import Image
                                pil_img = Image.fromarray(img_to_process)
                                pil_img.save(temp_file.name, 'JPEG', quality=95)
                                temp_file.close()
                                
                                print("[OCRWorker] 使用临时文件调用 OCR（ocr 方法）...")
                                # 使用文件路径调用 OCR（使用 ocr 方法，更稳定）
                                result = self.ocr_engine.ocr(temp_file.name)
                                
                                print("[OCRWorker] 临时文件方式调用成功")
                                
                                # 清理临时文件
                                try:
                                    os.unlink(temp_file.name)
                                except:
                                    pass
                            except Exception as e2:
                                print(f"[OCRWorker] 临时文件方式也失败: {e2}")
                                # 清理临时文件
                                try:
                                    os.unlink(temp_file.name)
                                except:
                                    pass
                                raise e  # 抛出原始异常
                        else:
                            # 不是 Unknown exception，直接抛出
                            raise
                    except Exception as e:
                        ocr_elapsed = time.time() - ocr_start_time
                        print(f"[OCRWorker] 其他异常发生，耗时: {ocr_elapsed:.2f}秒，错误: {e}")
                        import traceback
                        print(f"[OCRWorker] 异常详情:\n{traceback.format_exc()}")
                        raise
                    finally:
                        print("[OCRWorker] OCR 锁已释放")
            except Exception as outer_e:
                import traceback
                print(f"[OCRWorker] 外层异常（获取锁或调用OCR时）: {outer_e}\n{traceback.format_exc()}")
                raise
            
            if result is None:
                print("[OCRWorker] 警告：OCR 返回结果为 None")
                self.error_signal.emit("OCR 返回结果为 None")
                return
            
            print(f"[OCRWorker] OCR 调用返回，结果类型: {type(result)}")
            
            # 再次检查停止标志
            if self._stop_flag:
                print("[OCRWorker] 识别完成但收到停止请求，退出")
                return
            
            print(f"[OCRWorker] OCR 识别完成，结果: {result}")
            print(f"[OCRWorker] 结果是否为 None: {result is None}")
            if result:
                print(f"[OCRWorker] 结果长度: {len(result)}")
                if len(result) > 0:
                    print(f"[OCRWorker] result[0] 类型: {type(result[0])}, 内容: {result[0]}")
                    if result[0]:
                        print(f"[OCRWorker] result[0] 长度: {len(result[0])}")
            
            # 解析文本
            texts = []
            if result:
                print(f"[OCRWorker] 开始解析结果...")
                print(f"[OCRWorker] 结果类型: {type(result)}")
                
                # 处理 OCRResult 对象 (PaddleOCR 新版返回格式)
                # 检查是否是 OCRResult 对象或具有 rec_texts 属性的对象
                # 注意：result 可能是一个列表，其中包含 OCRResult 对象
                
                # 辅助函数：尝试从对象中提取文本
                def extract_from_object(obj):
                    # 检查是否有 rec_texts 属性 (PaddleX/PaddleOCR 新版)
                    if hasattr(obj, 'rec_texts') and obj.rec_texts:
                        print(f"[OCRWorker] 检测到 rec_texts 属性，直接提取文本")
                        return list(obj.rec_texts)
                    
                    # 检查是否是字典且有 rec_texts 键
                    if isinstance(obj, dict) and 'rec_texts' in obj:
                        print(f"[OCRWorker] 检测到字典包含 rec_texts 键，直接提取文本")
                        return list(obj['rec_texts'])
                        
                    return None

                # 尝试直接从 result 提取
                extracted = extract_from_object(result)
                if extracted:
                    texts.extend(extracted)
                
                # 如果 result 是列表，尝试从列表项提取
                elif isinstance(result, list):
                    for item in result:
                        extracted = extract_from_object(item)
                        if extracted:
                            texts.extend(extracted)
                        else:
                            # 尝试旧版格式解析: [[[坐标], (文本, 置信度)], ...]
                            # 或者可能是嵌套列表: [[[[坐标], (文本, 置信度)], ...]]
                            def extract_from_entry(entry):
                                """从单个 entry 中提取文本"""
                                if not entry:
                                    return
                                # entry 形如 [[坐标...], (文本, 置信度)]
                                if (
                                    isinstance(entry, (list, tuple))
                                    and len(entry) >= 2
                                    and isinstance(entry[1], (list, tuple))
                                    and len(entry[1]) >= 1
                                ):
                                    candidate = entry[1][0]
                                    texts.append(str(candidate))
                                elif isinstance(entry, str):
                                    texts.append(entry)
                                elif isinstance(entry, (list, tuple)):
                                    # 可能是嵌套列表，再次递归
                                    for sub in entry:
                                        extract_from_entry(sub)
                            
                            extract_from_entry(item)

                    print(f"[OCRWorker] 从 ocr() 结果提取到 {len(texts)} 条文本")
                    if texts:
                        print(f"[OCRWorker] 前5条文本: {texts[:5]}")
            
            print(f"[OCRWorker] 解析到 {len(texts)} 条文本")
            if texts:
                print(f"[OCRWorker] 前5条文本: {texts[:5]}")
            
            # 最后检查停止标志
            if not self._stop_flag:
                self.finished_signal.emit(texts)
                print("[OCRWorker] 结果已发送")
            else:
                print("[OCRWorker] 发送结果前收到停止请求，取消发送")
        except Exception as exc:
            import traceback
            error_detail = traceback.format_exc()
            print(f"[OCRWorker] 错误: {exc}\n{error_detail}")
            if not self._stop_flag:
                self.error_signal.emit(str(exc))


class MarketAnalysisTab(QWidget):
    """市场分析界面 - 通过屏幕识别世界频道喊话，分析物品价格"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ocr_engine = None
        self.is_capturing = False
        self.is_processing = False  # OCR 处理中标志
        self.ocr_worker = None  # OCR 工作线程
        self.capture_timer = QTimer(self)
        self.capture_timer.timeout.connect(self._capture_and_analyze)
        
        # OCR 线程锁（PaddleOCR 可能不支持多线程并发）
        self.ocr_lock = threading.Lock()
        
        # 市场数据存储：{物品名: {'buy': [价格列表], 'sell': [价格列表], 'latest_time': 时间戳}}
        self.market_data: Dict[str, Dict] = {}
        self.raw_messages: List[Dict] = []  # 原始消息记录
        # 物品仓库（统计出现次数、价格历史等）
        self.item_repository: Dict[str, Dict] = {}
        # 物品同义词规则
        self.alias_config: Dict[str, Dict[str, object]] = self._load_item_aliases()
        self.item_alias_exact, self.item_alias_contains = self._build_item_alias_rules()
        self.item_matcher = SmartItemMatcher(self.alias_config)
        self._ocr_resetting = False
        
        self._init_ocr()
        self._build_ui()
        self._load_market_data()

    def _init_ocr(self):
        """初始化 OCR 引擎"""
        print("[_init_ocr] 开始初始化 OCR 引擎")
        if not PADDLEOCR_AVAILABLE:
            print("[_init_ocr] PaddleOCR 未安装")
            QMessageBox.warning(
                self,
                "OCR 未安装",
                "请安装 PaddleOCR：\npip install paddlepaddle paddleocr\n\n"
                "或使用其他 OCR 方案。"
            )
            return
        try:
            print("[_init_ocr] 正在创建 PaddleOCR 实例...")
            # 关闭角度分类以提高速度
            # 新版PaddleOCR会自动检测GPU
            self.ocr_engine = PaddleOCR(
                use_angle_cls=False,  # 关闭角度分类以提高速度
                lang='ch',
                det_db_box_thresh=0.5,  # 降低检测阈值
                rec_batch_num=6  # 批处理数量
            )
            print("[_init_ocr] OCR 引擎初始化成功")
            
            # 测试 OCR 是否正常工作（10秒超时）
            print("[_init_ocr] 开始测试 OCR 功能...")
            if not self._test_ocr():
                # 测试失败，但不退出程序，只显示警告
                QMessageBox.warning(
                    self,
                    "OCR 测试失败",
                    "OCR 引擎测试失败：10秒内无法完成识别。\n\n"
                    "可能的原因：\n"
                    "1. PaddleOCR 模型加载失败\n"
                    "2. 系统资源不足\n"
                    "3. PaddleOCR 版本不兼容\n\n"
                    "请检查环境配置或重新安装 PaddleOCR。\n\n"
                    "程序将继续运行，但 OCR 功能可能无法正常工作。"
                )
                print("[_init_ocr] OCR 测试失败，但程序继续运行")
                return
            print("[_init_ocr] OCR 测试通过，可以正常使用")
        except Exception as exc:
            import traceback
            error_detail = traceback.format_exc()
            print(f"[_init_ocr] OCR 初始化失败: {exc}\n{error_detail}")
            QMessageBox.warning(self, "OCR 初始化失败", f"无法初始化 OCR 引擎：{exc}\n\n详细信息：\n{error_detail}")
    
    def _test_ocr(self):
        """测试 OCR 是否正常工作（10秒超时）"""
        try:
            if not self.ocr_engine:
                return False
            
            if not NUMPY_AVAILABLE:
                print("[_test_ocr] numpy 未安装，无法测试")
                return False
            
            # 创建一个简单的测试图像（白色背景，黑色文字）
            print("[_test_ocr] 创建测试图像...")
            test_img = np.ones((100, 200, 3), dtype=np.uint8) * 255  # 白色图像
            
            # 使用线程测试，设置超时
            test_result = [None]
            test_error = [None]
            test_completed = threading.Event()
            
            def test_ocr_in_thread():
                try:
                    print("[_test_ocr] 在线程中调用 OCR...")
                    start_time = time.time()
                    
                    # 获取锁
                    with _ocr_global_lock:
                        print("[_test_ocr] 获取锁，开始测试...")
                        # 使用 ocr 方法（更稳定）
                        result = self.ocr_engine.ocr(test_img)
                        
                        elapsed = time.time() - start_time
                        print(f"[_test_ocr] OCR 测试完成，耗时: {elapsed:.2f}秒")
                        test_result[0] = result
                        test_completed.set()
                except Exception as e:
                    import traceback
                    error_detail = traceback.format_exc()
                    print(f"[_test_ocr] 测试出错: {e}\n{error_detail}")
                    test_error[0] = str(e)
                    test_completed.set()
            
            # 启动测试线程
            test_thread = threading.Thread(target=test_ocr_in_thread, daemon=True)
            test_thread.start()
            
            # 等待最多10秒
            print("[_test_ocr] 等待测试完成（最多10秒）...")
            if test_completed.wait(timeout=10):
                if test_error[0]:
                    print(f"[_test_ocr] 测试失败: {test_error[0]}")
                    return False
                else:
                    print("[_test_ocr] 测试成功")
                    return True
            else:
                print("[_test_ocr] 测试超时（10秒）")
                return False
                
        except Exception as e:
            import traceback
            print(f"[_test_ocr] 测试异常: {e}\n{traceback.format_exc()}")
            return False

    def _build_ui(self):
        """构建界面"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # 控制区域
        control_layout = QHBoxLayout()
        
        self.capture_button = QPushButton("开始识别")
        self.capture_button.clicked.connect(self._toggle_capture)
        control_layout.addWidget(self.capture_button)
        
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 60)
        self.interval_spin.setValue(1)  # 默认1秒，提高识别频率
        self.interval_spin.setSuffix(" 秒")
        self.interval_spin.setToolTip("识别间隔：建议1-3秒，过快可能影响性能")
        control_layout.addWidget(QLabel("识别间隔："))
        control_layout.addWidget(self.interval_spin)
        
        self.region_button = QPushButton("选择识别区域")
        self.region_button.clicked.connect(self._select_region)
        control_layout.addWidget(self.region_button)
        
        self.clear_button = QPushButton("清空数据")
        self.clear_button.clicked.connect(self._clear_data)
        control_layout.addWidget(self.clear_button)
        
        self.alias_button = QPushButton("物品名管理")
        self.alias_button.clicked.connect(self._open_alias_manager)
        control_layout.addWidget(self.alias_button)

        self.learning_button = QPushButton("学习面板")
        self.learning_button.clicked.connect(self._open_learning_center)
        control_layout.addWidget(self.learning_button)

        self.export_button = QPushButton("导出配置")
        self.export_button.clicked.connect(self._export_learning_data)
        control_layout.addWidget(self.export_button)

        self.import_button = QPushButton("导入配置")
        self.import_button.clicked.connect(self._import_learning_data)
        control_layout.addWidget(self.import_button)
        
        control_layout.addStretch()
        
        self.status_label = QLabel("状态：未开始")
        control_layout.addWidget(self.status_label)
        
        main_layout.addLayout(control_layout)

        # 分类筛选区域
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("分类筛选："))
        self.category_filter_combo = QComboBox()
        self.category_filter_combo.addItem("全部", None)
        for cat in ITEM_CATEGORY_CHOICES:
            self.category_filter_combo.addItem(cat, cat)
        self.category_filter_combo.currentIndexChanged.connect(self._on_category_filter_changed)
        filter_layout.addWidget(self.category_filter_combo)

        self.subcategory_filter_combo = QComboBox()
        self._refresh_subcategory_filter()
        self.subcategory_filter_combo.currentIndexChanged.connect(self._on_filter_control_changed)
        filter_layout.addWidget(self.subcategory_filter_combo)

        filter_layout.addWidget(QLabel("利润≥"))
        self.min_profit_spin = QDoubleSpinBox()
        self.min_profit_spin.setRange(0, 9999)
        self.min_profit_spin.setDecimals(1)
        self.min_profit_spin.setSuffix(" 万")
        self.min_profit_spin.valueChanged.connect(lambda _: self._update_ui())
        filter_layout.addWidget(self.min_profit_spin)
        filter_layout.addStretch()
        main_layout.addLayout(filter_layout)

        # 主分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧：原始消息列表
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("识别到的消息（最近100条）："))
        self.message_list = QListWidget()
        self.message_list.setMaximumWidth(400)
        left_layout.addWidget(self.message_list)
        splitter.addWidget(left_panel)
        
        # 右侧：市场分析表格
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("分类分组结果："))
        self.result_tree = QTreeWidget()
        self.result_tree.setHeaderLabels(["分类/物品", "统计"])
        self.result_tree.setAlternatingRowColors(True)
        right_layout.addWidget(self.result_tree)
        self.category_stats_label = QLabel("分类统计：暂无数据")
        right_layout.addWidget(self.category_stats_label)

        right_layout.addWidget(QLabel("市场价格汇总（按利润排序）："))
        self.market_table = QTableWidget()
        self.market_table.setColumnCount(6)
        self.market_table.setHorizontalHeaderLabels(["物品名", "最低收价", "最高收价", "最低卖价", "最高卖价", "利润空间"])
        self.market_table.horizontalHeader().setStretchLastSection(True)
        self.market_table.setAlternatingRowColors(True)
        self.market_table.setSortingEnabled(True)
        right_layout.addWidget(self.market_table)
        right_layout.addWidget(QLabel("物品趋势分析："))
        self.item_table = QTableWidget()
        self.item_table.setColumnCount(7)
        self.item_table.setHorizontalHeaderLabels([
            "物品名",
            "出现次数",
            "最新价格(万)",
            "今日均价(万)",
            "昨日均价(万)",
            "7日均价(万)",
            "趋势"
        ])
        self.item_table.horizontalHeader().setStretchLastSection(True)
        self.item_table.setAlternatingRowColors(True)
        self.item_table.setSortingEnabled(True)
        right_layout.addWidget(self.item_table)
        splitter.addWidget(right_panel)
        
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        main_layout.addWidget(splitter, stretch=1)
        
        # 识别区域（默认全屏）
        self.capture_region = None

    def _select_region(self):
        """选择识别区域"""
        # 创建区域选择窗口
        selector = RegionSelector(self)
        selector.setModal(True)
        
        # 先显示窗口，确保可见
        selector.show()
        QApplication.processEvents()
        
        # 确保窗口在最前面并获取焦点
        selector.raise_()
        selector.activateWindow()
        selector.setFocus()
        QApplication.processEvents()
        
        # 执行对话框
        result = selector.exec()
        
        if result == QDialog.DialogCode.Accepted:
            self.capture_region = selector.selected_region
            if self.capture_region:
                x, y, w, h = self.capture_region
                self.status_label.setText(f"状态：已选择区域 ({x}, {y}, {w}x{h})")
            else:
                self.capture_region = None
                self.status_label.setText("状态：使用全屏识别")
        else:
            # 用户取消，保持原设置
            pass

    def _toggle_capture(self):
        """切换识别状态"""
        print(f"[_toggle_capture] 点击切换，is_capturing={self.is_capturing}, ocr_engine={self.ocr_engine is not None}")
        if not self.ocr_engine:
            print("[_toggle_capture] OCR 引擎未初始化")
            QMessageBox.warning(self, "错误", "OCR 引擎未初始化，请先安装 PaddleOCR")
            return
        
        if self.is_capturing:
            print("[_toggle_capture] 停止识别")
            self._stop_capture()
        else:
            print("[_toggle_capture] 开始识别")
            self._start_capture()

    def _start_capture(self):
        """开始识别"""
        print("[_start_capture] 开始识别")
        self.is_capturing = True
        self.capture_button.setText("停止识别")
        self.status_label.setText("状态：正在识别...")
        # 不再使用定时器，改为在识别完成后手动触发下一次
        # interval_ms = self.interval_spin.value() * 1000
        # self.capture_timer.start(interval_ms)
        # 立即执行一次
        print(f"[_start_capture] 开始第一次识别（识别完成后将自动继续）")
        self._capture_and_analyze()

    def _stop_capture(self):
        """停止识别"""
        try:
            print("[_stop_capture] 开始停止识别")
            self.is_capturing = False
            self.capture_timer.stop()
            
            # 立即重置状态，不等待线程完成
            self.is_processing = False
            self.capture_button.setText("开始识别")
            self.status_label.setText("状态：已停止")
            
            # 停止 OCR 线程（使用标志而不是强制终止）
            if self.ocr_worker:
                print(f"[_stop_capture] 请求停止 OCR 线程，运行状态: {self.ocr_worker.isRunning()}")
                try:
                    # 设置停止标志
                    if hasattr(self.ocr_worker, 'stop'):
                        self.ocr_worker.stop()
                    
                    # 断开信号连接，防止回调函数被调用（在等待之前断开）
                    try:
                        try:
                            self.ocr_worker.finished_signal.disconnect()
                        except TypeError:
                            pass
                        try:
                            self.ocr_worker.error_signal.disconnect()
                        except TypeError:
                            pass
                        try:
                            self.ocr_worker.finished.disconnect()
                        except TypeError:
                            pass
                    except Exception as e:
                        print(f"[_stop_capture] 断开信号时出错（可忽略）: {e}")
                    
                    # 如果线程还在运行，使用 requestInterruption 而不是 terminate
                    if self.ocr_worker.isRunning():
                        print("[_stop_capture] 请求线程中断...")
                        self.ocr_worker.requestInterruption()
                        
                        # 使用定时器异步等待，避免阻塞
                        def check_and_cleanup():
                            if self.ocr_worker and not self.ocr_worker.isRunning():
                                print("[_stop_capture] 线程已停止，清理中...")
                                self._cleanup_worker()
                            elif self.ocr_worker and self.ocr_worker.isRunning():
                                # 如果还在运行，再等一会儿
                                QTimer.singleShot(500, check_and_cleanup)
                            else:
                                self._cleanup_worker()
                        
                        # 延迟检查，给线程时间响应中断请求
                        QTimer.singleShot(100, check_and_cleanup)
                    else:
                        # 线程已经停止，直接清理
                        print("[_stop_capture] 线程已停止，直接清理")
                        QTimer.singleShot(100, lambda: self._cleanup_worker())
                except Exception as e:
                    import traceback
                    print(f"[_stop_capture] 停止线程时出错: {e}\n{traceback.format_exc()}")
                    # 即使出错也尝试清理
                    try:
                        self.ocr_worker = None
                    except:
                        pass
            
            self._save_market_data()
            print("[_stop_capture] 停止识别完成")
        except Exception as e:
            import traceback
            print(f"[_stop_capture] 严重错误: {e}\n{traceback.format_exc()}")
            # 确保状态被重置
            try:
                self.is_capturing = False
                self.is_processing = False
                self.capture_button.setText("开始识别")
                self.status_label.setText("状态：已停止")
            except:
                pass
    
    def _cleanup_worker(self):
        """清理工作线程"""
        try:
            if self.ocr_worker:
                # 确保线程已停止
                if self.ocr_worker.isRunning():
                    print("[_cleanup_worker] 警告：线程仍在运行，跳过清理")
                    return
                
                # 安全删除
                try:
                    self.ocr_worker.deleteLater()
                except Exception as e:
                    print(f"[_cleanup_worker] deleteLater 出错（可忽略）: {e}")
                
                self.ocr_worker = None
                print("[_cleanup_worker] 线程清理完成")
        except Exception as e:
            import traceback
            print(f"[_cleanup_worker] 清理时出错: {e}\n{traceback.format_exc()}")
            # 即使出错也重置引用
            try:
                self.ocr_worker = None
            except:
                pass

    def _capture_and_analyze(self):
        """截图并分析"""
        print(f"[_capture_and_analyze] 开始，is_processing={self.is_processing}, is_capturing={self.is_capturing}")
        if not self.is_capturing:
            print("[_capture_and_analyze] 当前未处于识别状态，跳过")
            self.is_processing = False
            return
        # 如果正在处理中，跳过本次
        if self.is_processing:
            print("[_capture_and_analyze] 正在处理中，跳过")
            return
        
        try:
            # 截图
            print("[_capture_and_analyze] 开始截图")
            screenshot = self._take_screenshot()
            if screenshot is None:
                print("[_capture_and_analyze] 截图失败，返回 None")
                self.status_label.setText("状态：截图失败")
                return
            print(f"[_capture_and_analyze] 截图成功，类型: {type(screenshot)}")
            
            # OCR 识别
            if not self.ocr_engine:
                return
            
            # 转换为 numpy.ndarray（PaddleOCR 需要）
            if isinstance(screenshot, QPixmap):
                qimage = screenshot.toImage()
                width = qimage.width()
                height = qimage.height()
                ptr = qimage.bits()
                ptr.setsize(qimage.sizeInBytes())
                arr = QByteArray(ptr.asstring())
                pil_image = Image.frombytes("RGB", (width, height), arr.data())
            elif isinstance(screenshot, Image.Image):
                pil_image = screenshot
            else:
                self.status_label.setText(f"状态：不支持的截图格式")
                return
            
            # 将 PIL.Image 转换为 numpy.ndarray
            if not NUMPY_AVAILABLE:
                self.status_label.setText(f"状态：需要安装 numpy 库")
                return
            
            # PIL.Image 转 numpy.ndarray
            img_array = np.array(pil_image)
            
            # 如果之前的线程还在运行，检查是否超时
            if self.ocr_worker and self.ocr_worker.isRunning():
                # 检查线程运行时间
                if hasattr(self.ocr_worker, 'start_time'):
                    elapsed = time.time() - self.ocr_worker.start_time
                    if elapsed > 60:  # 60秒超时（第一次可能很慢，因为要加载模型）
                        print(f"[_capture_and_analyze] OCR 线程运行超时 ({elapsed:.1f}秒)，强制清理")
                        try:
                            if hasattr(self.ocr_worker, 'stop'):
                                self.ocr_worker.stop()
                            self.ocr_worker.finished_signal.disconnect()
                            self.ocr_worker.error_signal.disconnect()
                            self.ocr_worker.finished.disconnect()
                        except Exception as e:
                            print(f"[_capture_and_analyze] 清理线程时出错: {e}")
                        self.ocr_worker.terminate()
                        self.ocr_worker.wait(1000)
                        self.ocr_worker.deleteLater()
                        self.ocr_worker = None
                        self.is_processing = False
                        self.status_label.setText(f"状态：上次识别超时({elapsed:.0f}秒)，已重置")
                        print("[_capture_and_analyze] 等待下次定时器触发")
                        return
                    else:
                        # 显示进度
                        if elapsed > 10:
                            self.status_label.setText(f"状态：识别中... ({elapsed:.0f}秒)")
                        print(f"[_capture_and_analyze] 之前的线程还在运行中 ({elapsed:.1f}秒)，等待完成")
                        return
                else:
                    print("[_capture_and_analyze] 之前的线程还在运行，等待完成")
                    return
            
            # 创建新的 OCR 工作线程
            self.is_processing = True
            self.status_label.setText("状态：正在识别中...")
            print(f"[_capture_and_analyze] 创建 OCR 线程，图像尺寸: {img_array.shape}")
            
            self.ocr_worker = OCRWorker(self.ocr_engine, img_array)
            self.ocr_worker.start_time = time.time()  # 记录启动时间
            self.ocr_worker.finished_signal.connect(self._on_ocr_finished)
            self.ocr_worker.error_signal.connect(self._on_ocr_error)
            self.ocr_worker.finished.connect(self._on_ocr_thread_finished)
            
            print(f"[_capture_and_analyze] 启动 OCR 线程")
            self.ocr_worker.start()
            print(f"[_capture_and_analyze] OCR 线程已启动，运行状态: {self.ocr_worker.isRunning()}")
            
        except Exception as exc:
            import traceback
            print(f"[_capture_and_analyze] 异常: {exc}\n{traceback.format_exc()}")
            self.status_label.setText(f"状态：识别出错 - {exc}")
            self.is_processing = False
            # 如果还在识别中，等待一段时间后继续下一次识别
            if self.is_capturing:
                interval_ms = self.interval_spin.value() * 1000
                QTimer.singleShot(interval_ms, self._capture_and_analyze)
                print(f"[_capture_and_analyze] 已安排下一次识别，延迟 {interval_ms}ms")
    
    def _on_ocr_finished(self, texts: List[str]):
        """OCR 识别完成回调"""
        print(f"[_on_ocr_finished] 收到 {len(texts)} 条文本")
        
        # 如果已经停止识别，不处理结果
        if not self.is_capturing:
            self.is_processing = False
            return
        
        try:
            # 分析文本，提取价格信息
            old_item_count = len(self.market_data)
            old_message_count = len(self.raw_messages)
            
            print(f"[_on_ocr_finished] 开始分析文本...")
            self._analyze_texts(texts)
            print(f"[_on_ocr_finished] 文本分析完成")
            
            new_item_count = len(self.market_data)
            new_message_count = len(self.raw_messages)
            added_items = new_item_count - old_item_count
            added_messages = new_message_count - old_message_count
            
            print(f"[_on_ocr_finished] 提取结果: {added_messages}条消息, {added_items}个新物品")
            
            # 更新UI显示
            self._update_ui()
            
            self.status_label.setText(f"状态：识别完成，{len(texts)}条文本，提取{added_messages}条价格信息，{added_items}个新物品")
            
            # 如果还在识别中，等待一段时间后继续下一次识别（而不是立即触发）
            if self.is_capturing:
                interval_ms = self.interval_spin.value() * 1000
                # 使用 QTimer 延迟触发下一次识别，避免立即触发导致的问题
                QTimer.singleShot(interval_ms, self._capture_and_analyze)
        except Exception as exc:
            import traceback
            print(f"[_on_ocr_finished] 分析出错: {exc}\n{traceback.format_exc()}")
            self.status_label.setText(f"状态：分析出错 - {exc}")
            # 即使出错也安排下一次识别
            if self.is_capturing:
                interval_ms = self.interval_spin.value() * 1000
                QTimer.singleShot(interval_ms, self._capture_and_analyze)
        finally:
            self.is_processing = False
    
    def _on_ocr_error(self, error_msg: str):
        """OCR 识别错误回调"""
        print(f"[_on_ocr_error] OCR 识别出错: {error_msg}")
        self.status_label.setText(f"状态：识别出错 - {error_msg}")
        self.is_processing = False

        error_lower = error_msg.lower() if isinstance(error_msg, str) else ""
        if any(keyword in error_lower for keyword in ["could not create a primitive", "could not create a memory object"]):
            print("[_on_ocr_error] 检测到 oneDNN Primitive/Memory 创建失败，准备重置 OCR 引擎")
            self._restart_ocr_engine(error_msg)
        
        # 如果还在识别中，等待一段时间后继续下一次识别
        if self.is_capturing:
            interval_ms = self.interval_spin.value() * 1000
            QTimer.singleShot(interval_ms, self._capture_and_analyze)
            print(f"[_on_ocr_error] 已安排下一次识别，延迟 {interval_ms}ms")
    
    def _on_ocr_thread_finished(self):
        """OCR 线程完成回调（清理）"""
        if self.ocr_worker:
            self.ocr_worker.deleteLater()
            self.ocr_worker = None

    def _restart_ocr_engine(self, reason: Optional[str] = None):
        """尝试重置 OCR 引擎，缓解内存/primitive 创建失败"""
        if self._ocr_resetting:
            print("[_restart_ocr_engine] OCR 重置已在进行中，跳过")
            return

        self._ocr_resetting = True

        def do_restart():
            try:
                print(f"[_restart_ocr_engine] 正在重置 OCR 引擎，原因: {reason}")
                self._cleanup_worker()
                self.ocr_engine = None
                try:
                    import gc
                    gc.collect()
                except Exception:
                    pass
                self._init_ocr()
            finally:
                self._ocr_resetting = False

        # 轻微延迟，确保当前事件处理完成
        QTimer.singleShot(200, do_restart)

    def _build_item_alias_rules(self):
        """构建物品同义词规则"""
        alias_config = copy.deepcopy(getattr(self, "alias_config", None) or DEFAULT_ITEM_ALIASES)
        contains_keywords_whitelist = {"高兽", "卷云", "里卷", "浮石", "符石", "小瓶", "大瓶"}
        exact_map: Dict[str, str] = {}
        contains_rules: List[Tuple[str, List[str]]] = []

        for canonical, meta in alias_config.items():
            variants = meta.get("aliases", []) if isinstance(meta, dict) else meta
            contains_keywords: List[str] = []
            for variant in variants:
                simplified = self._simplify_item_key(variant)
                if not simplified:
                    continue
                exact_map[simplified] = canonical
                # 对于较短的别名或常见关键词，保留原始文本用于包含匹配
                if len(variant) <= 4 or variant in contains_keywords_whitelist:
                    contains_keywords.append(variant)
            if contains_keywords:
                contains_rules.append((canonical, contains_keywords))

        return exact_map, contains_rules

    def _ensure_alias_entry(self, canonical: str, save: bool = True) -> bool:
        canonical = canonical.strip()
        if not canonical:
            return False
        if canonical in self.alias_config:
            return False
        category, subcategory = self._guess_item_category_pair(canonical)
        self.alias_config[canonical] = {
            "aliases": [canonical],
            "category": category,
            "subcategory": subcategory,
        }
        self.item_alias_exact, self.item_alias_contains = self._build_item_alias_rules()
        if hasattr(self, "item_matcher"):
            self.item_matcher.update_aliases(self.alias_config)
        if save:
            self._save_item_aliases()
        return True

    def _guess_item_category(self, canonical: str) -> str:
        if canonical in COMMON_GAME_ITEMS:
            return COMMON_GAME_ITEMS[canonical]
        for cat, _sub, keywords in CATEGORY_KEYWORD_MAP:
            for kw in keywords:
                if kw in canonical:
                    return cat
        return "杂项"

    def _guess_item_category_pair(self, canonical: str) -> Tuple[str, str]:
        category = self._guess_item_category(canonical)
        for cat, sub_cat, keywords in CATEGORY_KEYWORD_MAP:
            if cat != category:
                continue
            for kw in keywords:
                if kw in canonical:
                    return category, sub_cat
        return category, "未分类"

    def _clean_item_token(self, text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(r'[：:，,。！？!?\[\]\{\}\(\)<>«»“”]', '', cleaned)
        return cleaned.strip()

    def _is_invalid_item_name(self, name: str) -> bool:
        if not name:
            return True
        plain = name.strip()
        if not plain:
            return True
        compact = re.sub(r'\s+', '', plain)
        alnum = re.sub(r'[^\u4e00-\u9fa5A-Za-z0-9]', '', compact)
        if not re.search(r'[\u4e00-\u9fa5A-Za-z]', alnum):
            return True
        if len(alnum) == 1 and alnum not in {"图"}:
            return True
        if re.fullmatch(r'\d+(\.\d+)?', alnum):
            return True
        if re.fullmatch(r'\d+(\.\d+)?(w|W|万|千|百)?', compact):
            return True
        if plain in ITEM_NAME_STOPWORDS or alnum in ITEM_NAME_STOPWORDS:
            return True
        if alnum.endswith(("个", "件", "瓶", "张", "只", "条")) and len(alnum) <= 2:
            return True
        return False

    def _sanitize_item_candidate(self, raw_name: str) -> Optional[str]:
        cleaned = self._clean_item_token(raw_name)
        cleaned = self._truncate_item_name(cleaned)
        if self._is_invalid_item_name(cleaned):
            return None
        return self._normalize_item_name(cleaned)

    def _cleanup_item_capture(self, raw: str) -> str:
        if not raw:
            return ""
        raw = raw.strip()
        if not raw:
            return ""
        if re.search(r'\d', raw):
            split_parts = re.split(r'(?:收|卖)', raw, maxsplit=1)
            if split_parts and split_parts[0]:
                raw = split_parts[0]
            raw = re.sub(r'\d+(?:\.\d+)?[万千wW亿]+$', '', raw).strip()
        return raw

    def _infer_trade_type(self, text: str, default: str = "sell") -> Optional[str]:
        lowered = text.lower()
        buy_hits = sum(1 for kw in BUY_KEYWORDS if kw in text)
        sell_hits = sum(1 for kw in SELL_KEYWORDS if kw in text or kw in lowered)
        if buy_hits > sell_hits and buy_hits > 0:
            return "buy"
        if sell_hits > buy_hits and sell_hits > 0:
            return "sell"
        if buy_hits == sell_hits and buy_hits > 0:
            # 同时包含买卖关键词时，取最后出现的那个
            buy_positions = [text.rfind(kw) for kw in BUY_KEYWORDS if kw in text]
            sell_positions = [text.rfind(kw) for kw in SELL_KEYWORDS if kw in text or kw in lowered]
            last_buy = max(buy_positions) if buy_positions else -1
            last_sell = max(sell_positions) if sell_positions else -1
            if last_buy >= last_sell and last_buy != -1:
                return "buy"
            if last_sell > last_buy and last_sell != -1:
                return "sell"
        if "收" in text:
            return "buy"
        if any(sym in text for sym in ("出", "卖", "让", "带走")):
            return "sell"
        return default if default else None



    def _get_alias_file(self) -> str:
        return os.path.join(os.path.dirname(__file__), "novels_data", "item_aliases.json")

    def _load_item_aliases(self) -> Dict[str, Dict[str, object]]:
        config = copy.deepcopy(DEFAULT_ITEM_ALIASES)
        alias_file = self._get_alias_file()
        if os.path.exists(alias_file):
            try:
                with open(alias_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        for canonical, meta in data.items():
                            if isinstance(meta, dict):
                                aliases = meta.get("aliases", [])
                                category = meta.get("category", self._guess_item_category(canonical))
                                subcategory = meta.get("subcategory", "未分类")
                                cleaned = [v.strip() for v in aliases if isinstance(v, str) and v.strip()]
                                if cleaned:
                                    config[canonical] = {
                                        "aliases": cleaned,
                                        "category": category,
                                        "subcategory": subcategory,
                                    }
                            elif isinstance(meta, list):
                                cleaned = [v.strip() for v in meta if isinstance(v, str) and v.strip()]
                                if cleaned:
                                    config[canonical] = {
                                        "aliases": cleaned,
                                        "category": self._guess_item_category(canonical),
                                        "subcategory": "未分类",
                                    }
            except Exception as exc:
                print(f"[ItemAlias] 加载用户别名失败: {exc}")
        for canonical, category in COMMON_GAME_ITEMS.items():
            canonical = canonical.strip()
            if canonical and canonical not in config:
                cat_guess, sub = self._guess_item_category_pair(canonical)
                config[canonical] = {
                    "aliases": [canonical],
                    "category": cat_guess or category,
                    "subcategory": sub,
                }
        return config

    def _save_item_aliases(self):
        alias_file = self._get_alias_file()
        os.makedirs(os.path.dirname(alias_file), exist_ok=True)
        try:
            with open(alias_file, "w", encoding="utf-8") as f:
                json.dump(self.alias_config, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", f"无法保存物品别名：{exc}")

    def _open_alias_manager(self):
        dialog = ItemAliasDialog(self.alias_config, DEFAULT_ITEM_ALIASES, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_config = dialog.get_alias_config()
            if new_config:
                self.alias_config = new_config
                self.item_alias_exact, self.item_alias_contains = self._build_item_alias_rules()
                if hasattr(self, "item_matcher"):
                    self.item_matcher.update_aliases(self.alias_config)
                self._save_item_aliases()
                QMessageBox.information(self, "成功", "物品别名已更新，后续识别将使用新的名称。")

    def _clear_data(self):
        """清空数据"""
        reply = QMessageBox.question(
            self,
            "确认清空",
            "确定要清空所有市场数据吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.market_data.clear()
            self.raw_messages.clear()
            self.item_repository.clear()
            self._update_ui()
            QMessageBox.information(self, "清空完成", "市场数据已清空")

    def _load_market_data(self):
        """加载市场数据"""
        data_file = os.path.join(os.path.dirname(__file__), "novels_data", "market_data.json")
        if os.path.exists(data_file):
            try:
                with open(data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.market_data = data.get('market_data', {})
                    self.raw_messages = data.get('raw_messages', [])
                    self.item_repository = data.get('item_repository', {}) or {}
                    # 确保 item_repository 是字典
                    if not isinstance(self.item_repository, dict):
                        self.item_repository = {}
                    
                    # 恢复别名配置
                    # 检查是否有新的物品需要添加到别名配置中
                    added_alias = False
                    for item_name in list(self.market_data.keys()):
                        added_alias |= self._ensure_alias_entry(item_name, save=False)
                    for item_name in list(self.item_repository.keys()):
                        added_alias |= self._ensure_alias_entry(item_name, save=False)
                    
                    if added_alias:
                        self.item_alias_exact, self.item_alias_contains = self._build_item_alias_rules()
                        self._save_item_aliases()
                        
                    self._update_ui()
            except Exception as exc:
                QMessageBox.warning(self, "加载失败", f"无法加载数据：{exc}")

    def _update_ui(self):
        """更新界面显示"""
        # 更新消息列表
        self.message_list.clear()
        for msg in self.raw_messages[-50:]:  # 只显示最近50条
            category = msg.get('category', '-')
            subcategory = msg.get('subcategory', '-')
            confidence = msg.get('confidence')
            confidence_text = f"{confidence:.2f}" if isinstance(confidence, (int, float)) else "-"
            display_text = (
                f"[{msg['time']}] [{category}/{subcategory}] {msg['type']} {msg['item']} "
                f"{msg['price']:.1f}万 (置信度 {confidence_text}) - {msg['text'][:30]}"
            )
            item = QListWidgetItem(display_text)
            if msg.get('status') == 'ignored':
                item.setForeground(Qt.GlobalColor.gray)
            elif msg.get('status') == 'learned':
                item.setForeground(Qt.GlobalColor.green)
            self.message_list.addItem(item)
        self.message_list.scrollToBottom()

        # 更新市场行情表
        self.market_table.setRowCount(0)
        rows_data = []
        for item_name, data in self.market_data.items():
            buy_prices = data.get('buy', [])
            sell_prices = data.get('sell', [])
            latest_time = data.get('latest_time', 0)
            
            avg_buy = sum(buy_prices) / len(buy_prices) if buy_prices else 0
            avg_sell = sum(sell_prices) / len(sell_prices) if sell_prices else 0
            
            # 计算利润空间 (卖出均价 - 买入均价)
            profit = 0
            if avg_buy > 0 and avg_sell > 0:
                profit = avg_sell - avg_buy
            
            rows_data.append({
                'name': item_name,
                'category': data.get('category', '未分类'),
                'subcategory': data.get('subcategory', '未分类'),
                'buy': avg_buy,
                'sell': avg_sell,
                'profit': profit,
                'latest': latest_time
            })
        
        # 按最新更新时间排序
        rows_data.sort(key=lambda x: x['latest'], reverse=True)
        
        for row_data in rows_data:
            row = self.market_table.rowCount()
            self.market_table.insertRow(row)
            self.market_table.setItem(row, 0, QTableWidgetItem(row_data['name']))
            self.market_table.setItem(row, 1, QTableWidgetItem(row_data['category']))
            self.market_table.setItem(row, 2, QTableWidgetItem(row_data['subcategory']))
            self.market_table.setItem(row, 3, QTableWidgetItem(f"{row_data['buy']:.1f}"))
            self.market_table.setItem(row, 4, QTableWidgetItem(f"{row_data['sell']:.1f}"))
            
            profit_item = QTableWidgetItem(f"{row_data['profit']:.1f}")
            if row_data['profit'] and row_data['profit'] > 0:
                profit_item.setForeground(Qt.GlobalColor.green)
            self.market_table.setItem(row, 5, profit_item)

        self._update_result_tree(rows_data)
        
        # 更新物品趋势表
        self._update_repository_table()
        
        # 更新状态
        total_items = len(self.market_data)
        total_messages = len(self.raw_messages)
        repo_count = len(self.item_repository)
        self.status_label.setText(
            f"状态：识别中... | 物品数：{total_items} | 消息数：{total_messages} | 仓库：{repo_count}"
        )

    def _update_result_tree(self, rows_data: List[Dict[str, Any]]):
        self.result_tree.clear()
        if not rows_data:
            self.category_stats_label.setText("分类统计：暂无数据")
            return

        stats: Dict[str, Dict[str, Any]] = {}
        for row in rows_data:
            category = row.get('category', '未分类')
            subcategory = row.get('subcategory', '未分类')
            profit = row.get('profit')
            confidence = row.get('confidence')

            cat_entry = stats.setdefault(category, {'count': 0, 'profit_values': [], 'subs': {}})
            cat_entry['count'] += 1
            if profit is not None:
                cat_entry['profit_values'].append(profit)
            
            sub_entry = cat_entry['subs'].setdefault(subcategory, {'count': 0, 'items': []})
            sub_entry['count'] += 1
            sub_entry['items'].append(row)

        summary_lines = []
        for cat, info in stats.items():
            avg_profit = sum(info['profit_values']) / len(info['profit_values']) if info['profit_values'] else 0
            summary_lines.append(f"{cat}({info['count']})")
            
            cat_item = QTreeWidgetItem([f"{cat} ({info['count']})", f"平均利润: {avg_profit:.1f}"])
            self.result_tree.addTopLevelItem(cat_item)
            
            for sub, sub_info in info['subs'].items():
                sub_item = QTreeWidgetItem([f"{sub} ({sub_info['count']})", ""])
                cat_item.addChild(sub_item)
                
                for item_entry in sub_info['items']:
                    profit = item_entry.get('profit', 0)
                    profit_text = f"{profit:.1f}"
                    confidence = item_entry.get('confidence')
                    confidence_text = f"{confidence:.2f}" if isinstance(confidence, (int, float)) else "-"
                    
                    detail_text = (
                        f"收 {item_entry['buy']:.1f} | "
                        f"卖 {item_entry['sell']:.1f} | "
                        f"利润 {profit_text} | 置信度 {confidence_text}"
                    )
                    sub_item.addChild(QTreeWidgetItem([item_entry['name'], detail_text]))

        self.result_tree.expandAll()
        self.category_stats_label.setText("分类统计：" + "； ".join(summary_lines))

    def _update_repository_table(self):
        """更新物品仓库趋势表"""
        if not hasattr(self, "item_table"):
            return

        self.item_table.setRowCount(0)
        if not self.item_repository:
            return

        today = datetime.now().date()
        today_key = today.strftime("%Y-%m-%d")
        yesterday_key = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        week_keys = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

        rows = []
        for item_name, data in self.item_repository.items():
            count = data.get('count', 0)
            records = data.get('records', []) # 假设有records字段，或者从history计算
            history = data.get('history', [])
            
            # 计算统计数据
            latest_price = data.get('last_price', 0)
            
            # 辅助函数：计算某日均价
            def get_avg_price(target_date_str):
                prices = [p for t, p in history if datetime.fromtimestamp(t).strftime("%Y-%m-%d") == target_date_str]
                return sum(prices) / len(prices) if prices else 0
            
            today_avg = get_avg_price(today_key)
            yesterday_avg = get_avg_price(yesterday_key)
            
            # 7日均价
            week_prices = [p for t, p in history if datetime.fromtimestamp(t).strftime("%Y-%m-%d") in week_keys]
            week_avg = sum(week_prices) / len(week_prices) if week_prices else 0
            
            # 趋势判断
            trend = "平稳"
            if today_avg > yesterday_avg:
                trend = "上涨"
            elif today_avg < yesterday_avg and yesterday_avg > 0:
                trend = "下跌"
                
            rows.append({
                'name': item_name,
                'count': count,
                'latest': latest_price,
                'today_avg': today_avg,
                'yesterday_avg': yesterday_avg,
                'week_avg': week_avg,
                'trend': trend
            })
            
        # 按出现次数排序
        rows.sort(key=lambda x: x['count'], reverse=True)
        
        for row_data in rows:
            row = self.item_table.rowCount()
            self.item_table.insertRow(row)
            
            # 尝试获取分类信息
            category_tag = ""
            if row_data['name'] in self.market_data:
                cat = self.market_data[row_data['name']].get('category', '')
                if cat:
                    category_tag = f"[{cat}]"
            
            label = row_data['name']
            
            def fmt(val):
                return f"{val:.1f}" if val else "-"
            
            self.item_table.setItem(row, 0, QTableWidgetItem(f"{label} {category_tag}"))
            self.item_table.setItem(row, 1, QTableWidgetItem(str(row_data['count'])))
            self.item_table.setItem(row, 2, QTableWidgetItem(fmt(row_data['latest'])))
            self.item_table.setItem(row, 3, QTableWidgetItem(fmt(row_data['today_avg'])))
            self.item_table.setItem(row, 4, QTableWidgetItem(fmt(row_data['yesterday_avg'])))
            self.item_table.setItem(row, 5, QTableWidgetItem(fmt(row_data['week_avg'])))
            
            trend_item = QTableWidgetItem(row_data['trend'])
            if row_data['trend'] == "上涨":
                trend_item.setForeground(Qt.GlobalColor.red)
            elif row_data['trend'] == "下跌":
                trend_item.setForeground(Qt.GlobalColor.green)
            self.item_table.setItem(row, 6, trend_item)

        print(f"[_analyze_texts] 分析完成")

    def _analyze_texts(self, texts: List[str]):
        """分析识别到的文本，提取价格信息 (支持复杂多样的游戏聊天格式)"""
        print(f"[_analyze_texts] 开始分析 {len(texts)} 条文本")
        
        cleaned_texts = [preprocess_text_line(t) for t in texts if t]
        print(f"[_analyze_texts] 清理后剩余 {len(cleaned_texts)} 条")
        
        # 交易关键词
        buy_keywords = ["收", "求", "购", "收购", "长期收", "高价收", "高收", "回收"]
        sell_keywords = ["卖", "出", "售", "出售", "甩卖", "来", "有"]
        
        total_found = 0
        
        for idx, text in enumerate(cleaned_texts):
            if not text or len(text) < 4:
                continue
            
            # 只打印前3条的详细信息
            if idx < 3:
                print(f"[_analyze_texts] 处理 [{idx}]: {text[:100]}")
            
            # 确定默认交易类型
            default_trade_type = "sell"
            for kw in buy_keywords:
                if kw in text:
                    default_trade_type = "buy"
                    break
            
            # 尝试多种模式提取
            found_count = 0
            
            # 模式0: 紧凑兽决列表 (例如: "偷4410必4350连4150吸1800夜2710...")
            # 这种格式常见于兽决价格列表，物品名后直接跟数字价格
            beast_skill_pattern = re.compile(
                r'([\u4e00-\u9fa5]{1,4})(\d{3,5})(?=[\u4e00-\u9fa5]\d{3,5}|\s|$)',
                re.UNICODE
            )
            # 只在包含"收兽决"或类似关键词时尝试此模式
            if any(kw in text for kw in ["兽决", "实价收", "高收", "长期收"]):
                for match in beast_skill_pattern.finditer(text):
                    skill_name = match.group(1)
                    price_str = match.group(2)
                    
                    # 价格必须在合理范围内 (100-99999)
                    try:
                        price_val = int(price_str)
                        if price_val < 100 or price_val > 99999:
                            continue
                    except:
                        continue
                    
                    if self._process_item_price_pair(skill_name, price_str, default_trade_type, text):
                        found_count += 1
                        if idx < 3:
                            print(f"    模式0(紧凑兽决)匹配: {skill_name} {price_str}")
            
            # 模式1: 价格+收/卖+物品 (例如: "70W收3x抓鬼", "343W收牌子")
            # 修复：物品名允许包含数字(如3x抓鬼、100展级图吉)，用更明确的边界区分
            pattern1 = re.compile(
                r'(\d+(?:\.\d+)?[wWkK万千亿mM]+)\s*([收卖出售求购])\s*([\u4e00-\u9fa5a-zA-Z0-9xX级]{2,15})(?=\s|\d+[wWkK万千亿]|[收卖出售求购]|$)',
                re.IGNORECASE
            )
            for match in pattern1.finditer(text):
                price_str = match.group(1)
                action = match.group(2)
                raw_item = match.group(3).strip()
                
                trade_type = "buy" if action in buy_keywords else "sell"
                
                if self._process_item_price_pair(raw_item, price_str, trade_type, text):
                    found_count += 1
                    if idx < 3:  # 只打印前3条的匹配
                        print(f"    模式1匹配: {price_str} {action} {raw_item}")
            
            # 模式2: 收/卖+物品+价格 (例如: "收质量兽决73万", "卖金刚99")
            # 修复：物品名允许数字，如"3x抓鬼"、"100展级图吉"
            pattern2 = re.compile(
                r'([收卖出售求购])\s*([\u4e00-\u9fa5a-zA-Z0-9xX级]{2,15}?)\s+(\d+(?:\.\d+)?[wWkK万千亿mM]+)',
                re.IGNORECASE
            )
            for match in pattern2.finditer(text):
                action = match.group(1)
                raw_item = match.group(2).strip()
                price_str = match.group(3)
                
                trade_type = "buy" if action in buy_keywords else "sell"
                
                if self._process_item_price_pair(raw_item, price_str, trade_type, text):
                    found_count += 1
                    if idx < 3:
                        print(f"    模式2匹配: {action} {raw_item} {price_str}")
            
            # 模式3: 物品名+价格 (紧凑格式，例如: "质量兽决73万", "金刚99")
            # 只有在前面模式没匹配到时才尝试，避免过度匹配
            if found_count == 0:
                pattern3 = re.compile(
                    r'([\u4e00-\u9fa5]+?)(\d+(?:\.\d+)?[wWkK万千亿mM]?)',
                    re.IGNORECASE
                )
                for match in pattern3.finditer(text):
                    raw_item = match.group(1).strip()
                    price_str = match.group(2)
                    if len(raw_item) < 2:
                        continue
                    if self._process_item_price_pair(raw_item, price_str, default_trade_type, text):
                        found_count += 1
            
            # 模式5: 连续物品+价格 (无分隔符) 例如 "质量兽决73万吸收小法68万金刚99"
            pattern5 = re.compile(
                r'([\u4e00-\u9fa5a-zA-Z0-9]+?)(\d+(?:\.\d+)?\s*[wWkK万千亿mM]?)',
                re.IGNORECASE
            )
            for match in pattern5.finditer(text):
                raw_item = match.group(1).strip()
                price_str = match.group(2)
                if self._process_item_price_pair(raw_item, price_str, default_trade_type, text):
                    found_count += 1
            
            # 模式4: 纯数字价格+物品 (例如: "2450 40双指", "1900且 5¥0字都")
            # 这种模式很容易误匹配，只在特定上下文中使用
            if found_count == 0 and (any(kw in text for kw in buy_keywords + sell_keywords)):
                pattern4 = re.compile(
                    r'(\d{3,5})\s+([^\d\s]{2,10})',
                    re.IGNORECASE
                )
                for match in pattern4.finditer(text):
                    price_str = match.group(1)
                    raw_item = match.group(2).strip()
                    
                    # 只处理价格看起来合理的情况 (100-99999)
                    try:
                        price_val = int(price_str)
                        if price_val < 100 or price_val > 99999:
                            continue
                    except:
                        continue
                    
                    if self._process_item_price_pair(raw_item, price_str, default_trade_type, text):
                        found_count += 1
            
            total_found += found_count
        
        print(f"[_analyze_texts] 分析完成，共提取 {total_found} 个物品价格对")
    
    def _process_item_price_pair(self, raw_item: str, price_str: str, trade_type: str, original_text: str) -> bool:
        """处理单个物品-价格对，返回是否成功提取"""
        # 过滤无效物品名
        if not raw_item or len(raw_item) < 2:
            return False
        
        # 清理物品名中的交易关键词
        clean_item = raw_item
        for kw in ["收", "卖", "出", "售", "求", "购", "收购", "出售", "甩卖", "长期收", "高价收", "高收", "回收"]:
            clean_item = clean_item.replace(kw, "")
        
        # 移除前导/尾随的括号和空格
        clean_item = re.sub(r'^[\s\[\]【】()（）]+', '', clean_item)
        clean_item = re.sub(r'[\[\]【】()（）]+$', '', clean_item)
        clean_item = clean_item.strip()
        
        if len(clean_item) < 2:
            return False
        
        # 尝试解析价格
        price = normalize_price_value(price_str)
        if not price or price <= 0:
            return False
        
        # 尝试多种清理策略来匹配物品
        # 策略1: 使用原始清理后的名称
        match_info = self.item_matcher.match(clean_item)
        
        # 策略2: 如果策略1失败，尝试移除前导数字（但保留X、级等有意义的部分）
        if not match_info:
            cleaned_v2 = re.sub(r'^(\d+)(?![XxX级技段])', '', clean_item).strip()
            if cleaned_v2 != clean_item and len(cleaned_v2) >= 2:
                match_info = self.item_matcher.match(cleaned_v2)
        
        # 策略3: 如果还是失败，尝试移除所有数字
        if not match_info:
            cleaned_v3 = re.sub(r'\d+', '', clean_item).strip()
            if cleaned_v3 != clean_item and len(cleaned_v3) >= 2:
                match_info = self.item_matcher.match(cleaned_v3)
        
        # 策略4: 尝试提取关键词（针对复杂物品名）
        if not match_info and len(clean_item) > 4:
            for suffix_len in [4, 3, 2]:
                suffix = clean_item[-suffix_len:]
                if len(suffix) >= 2 and not suffix.isdigit():
                    match_info = self.item_matcher.match(suffix)
                    if match_info and match_info.confidence >= 0.8:
                        break
        
        if not match_info:
            return False
        
        # 降低置信度要求，因为游戏聊天用语很多简称
        if match_info.confidence < 0.6:
            return False
        
        # 记录数据（只记录成功的）
        self._record_price(match_info, trade_type, price, original_text, raw_item)
        return True


    def _record_price(
        self,
        match_info: ItemMatchResult,
        trade_type: str,
        price: float,
        raw_text: str,
        raw_item: Optional[str] = None,
    ):
        """记录价格信息"""
        if not match_info:
            return
        item_name = match_info.standard_name

        if item_name not in self.market_data:
            self.market_data[item_name] = {
                'buy': [],
                'sell': [],
                'latest_time': None,
                'category': match_info.category,
                'subcategory': match_info.subcategory,
            }
        else:
            if 'category' not in self.market_data[item_name]:
                self.market_data[item_name]['category'] = match_info.category
            if 'subcategory' not in self.market_data[item_name]:
                self.market_data[item_name]['subcategory'] = match_info.subcategory
        
        data = self.market_data[item_name]
        data['latest_time'] = time.time()
        
        if trade_type == 'buy':
            data['buy'].append(price)
            # 保持最近 20 条
            if len(data['buy']) > 20:
                data['buy'] = data['buy'][-20:]
        else:
            data['sell'].append(price)
            if len(data['sell']) > 20:
                data['sell'] = data['sell'][-20:]
        
        # 添加到原始消息记录
        self.raw_messages.append({
            'time': datetime.now().strftime("%H:%M:%S"),
            'type': '收购' if trade_type == 'buy' else '出售',
            'item': item_name,
            'raw_item': raw_item or item_name,
            'price': price,
            'text': raw_text,
            'category': match_info.category,
            'subcategory': match_info.subcategory,
            'confidence': match_info.confidence,
            'status': 'pending' # pending, learned, ignored
        })
        # 保持最近 500 条
        if len(self.raw_messages) > 500:
            self.raw_messages = self.raw_messages[-500:]
            
        # 更新物品仓库统计
        if item_name not in self.item_repository:
            self.item_repository[item_name] = {
                'count': 0,
                'last_price': 0,
                'min_price': float('inf'),
                'max_price': 0,
                'history': []
            }
        
        repo_item = self.item_repository[item_name]
        repo_item['count'] += 1
        repo_item['last_price'] = price
        repo_item['min_price'] = min(repo_item['min_price'], price)
        repo_item['max_price'] = max(repo_item['max_price'], price)
        repo_item['history'].append((time.time(), price))
        
        self._update_ui()

    def _save_market_data(self):
        """保存市场数据"""
        data_file = os.path.join(os.path.dirname(__file__), "novels_data", "market_data.json")
        os.makedirs(os.path.dirname(data_file), exist_ok=True)
        try:
            with open(data_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'market_data': self.market_data,
                    'raw_messages': self.raw_messages[-100:],  # 只保存最近100条
                    'item_repository': self.item_repository
                }, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", f"无法保存数据：{exc}")

    def _open_learning_center(self):
        dialog = LearningCenterDialog(
            raw_messages=self.raw_messages,
            alias_config=self.alias_config,
            category_tree=CATEGORY_TREE,
            apply_callback=self._apply_learning_feedback,
            status_callback=self._mark_message_status,
            parent=self,
        )
        dialog.exec()
        self._save_market_data()
        self._update_ui()

    def _apply_learning_feedback(
        self,
        message_index: int,
        canonical_name: str,
        category: Optional[str],
        subcategory: Optional[str],
        extra_alias: Optional[str] = None,
        use_raw_alias: bool = True,
    ) -> Tuple[bool, str]:
        if message_index < 0 or message_index >= len(self.raw_messages):
            return False, "找不到对应的原始记录"
        canonical_name = canonical_name.strip()
        if not canonical_name:
            return False, "标准名称不能为空"

        message = self.raw_messages[message_index]
        raw_token = message.get('raw_item') or ""
        category = category or DEFAULT_ITEM_CATEGORY
        subcategory = subcategory or "未分类"

        entry = self.alias_config.setdefault(
            canonical_name,
            {
                "aliases": [],
                "category": category,
                "subcategory": subcategory,
                "keywords": [],
            },
        )
        entry["category"] = category
        entry["subcategory"] = subcategory
        aliases = entry.setdefault("aliases", [])

        tokens = []
        if use_raw_alias:
            tokens.append(raw_token)
        tokens.append(extra_alias)

        for token in tokens:
            if token and token not in aliases and token != canonical_name:
                aliases.append(token)

        self.alias_config[canonical_name] = entry
        self.item_alias_exact, self.item_alias_contains = self._build_item_alias_rules()
        if hasattr(self, "item_matcher"):
            self.item_matcher.update_aliases(self.alias_config)
        self._save_item_aliases()
        self._ensure_alias_entry(canonical_name, save=False)

        message['item'] = canonical_name
        message['category'] = category
        message['subcategory'] = subcategory
        message['status'] = 'learned'

        return True, "已更新词典并记录学习结果"

    def _mark_message_status(self, message_index: int, status: str) -> Tuple[bool, str]:
        if message_index < 0 or message_index >= len(self.raw_messages):
            return False, "记录不存在"
        status = status or "pending"
        self.raw_messages[message_index]['status'] = status
        return True, f"已标记为{status}"

    def _export_learning_data(self):
        default_path = os.path.join(os.path.dirname(__file__), "novels_data", "learning_snapshot.json")
        file_path, _ = QFileDialog.getSaveFileName(self, "导出配置与学习数据", default_path, "JSON Files (*.json)")
        if not file_path:
            return
        data = {
            'market_data': self.market_data,
            'raw_messages': self.raw_messages,
            'item_repository': self.item_repository,
            'alias_config': self.alias_config,
        }
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "成功", f"已导出到：{file_path}")
        except Exception as exc:
            QMessageBox.warning(self, "导出失败", f"无法保存文件：{exc}")

    def _import_learning_data(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "导入配置与学习数据", "", "JSON Files (*.json)")
        if not file_path:
            return
        reply = QMessageBox.question(
            self,
            "确认导入",
            "将覆盖当前的市场数据、仓库和物品词典，确定继续导入吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.market_data = data.get('market_data', {}) or {}
            self.raw_messages = data.get('raw_messages', []) or []
            self.item_repository = data.get('item_repository', {}) or {}
            self.alias_config = data.get('alias_config', self.alias_config) or self.alias_config
            for msg in self.raw_messages:
                if isinstance(msg, dict):
                    msg.setdefault('status', 'pending')
                    msg.setdefault('raw_item', msg.get('item', ''))
            self.item_alias_exact, self.item_alias_contains = self._build_item_alias_rules()
            if hasattr(self, "item_matcher"):
                self.item_matcher.update_aliases(self.alias_config)
            self._save_item_aliases()
            self._save_market_data()
            self._update_ui()
            QMessageBox.information(self, "成功", "数据已导入。")
        except Exception as exc:
            QMessageBox.warning(self, "导入失败", f"无法读取文件：{exc}")

    @staticmethod
    def _simplify_item_key(text: str) -> str:
        """标准化字符串（去除非中英文、转小写）"""
        if not text:
            return ""
        simplified = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9]', '', text)
        return simplified.lower()

    def _normalize_item_name(self, item_name: str) -> str:
        """根据同义词规则将物品名归一化"""
        if not item_name:
            return item_name

        simplified = self._simplify_item_key(item_name)
        if simplified in self.item_alias_exact:
            return self.item_alias_exact[simplified]

        for canonical, keywords in self.item_alias_contains:
            for keyword in keywords:
                if keyword in item_name or self._simplify_item_key(keyword) in simplified:
                    return canonical

        self._ensure_alias_entry(item_name)
        return item_name

    def _refresh_subcategory_filter(self):
        current_cat = self.category_filter_combo.currentData()
        self.subcategory_filter_combo.blockSignals(True)
        self.subcategory_filter_combo.clear()
        self.subcategory_filter_combo.addItem("全部", None)
        if current_cat and current_cat in CATEGORY_TREE:
            for sub in CATEGORY_TREE[current_cat].keys():
                self.subcategory_filter_combo.addItem(sub, sub)
        self.subcategory_filter_combo.blockSignals(False)

    def _on_category_filter_changed(self, index: int):
        _ = index
        self._refresh_subcategory_filter()
        self._on_filter_control_changed()

    def _on_filter_control_changed(self):
        self._update_ui()

    def _take_screenshot(self):
        """截图"""
        try:
            if PIL_AVAILABLE:
                if self.capture_region is None:
                    # 使用 PIL 全屏截图
                    return ImageGrab.grab()
                else:
                    # 区域截图
                    x, y, width, height = self.capture_region
                    bbox = (x, y, x + width, y + height)
                    return ImageGrab.grab(bbox=bbox)
            else:
                # 使用 PyQt 截图
                screen = QApplication.primaryScreen()
                if screen:
                    if self.capture_region is None:
                        return screen.grabWindow(0)
                    else:
                        x, y, width, height = self.capture_region
                        return screen.grabWindow(0, x, y, width, height)
        except Exception as exc:
            self.status_label.setText(f"截图失败：{exc}")
        return None


    def _analyze_texts(self, texts: List[str]):
        """分析识别到的文本，提取价格信息 (支持多物品同行) - 智能邻近匹配版"""
        print(f"[_analyze_texts] 开始分析 {len(texts)} 条文本")
        
        cleaned_texts = [preprocess_text_line(t) for t in texts if t]
        print(f"[_analyze_texts] 清理后剩余 {len(cleaned_texts)} 条")
        
        # 交易意向关键词
        buy_keywords = ["收", "求", "购", "收购", "回收", "求购", "换"]
        sell_keywords = ["卖", "出", "售", "出售", "甩卖", "处理", "车费", "带", "交易", "Q", "q", "换"]
        
        # 价格匹配正则：匹配数字 + 可选单位
        # 新增：在价格后连续捕获多个宝宝/召唤兽名称（如 "持国多闻"、"涂山瞳龙龟"）
        # 该逻辑在找到价格后，向后扫描连续的中文块，尝试匹配多个宝宝名称并记录相同价格
        # 只在未通过 "或者" 或其他多物品逻辑捕获时执行
        # 具体实现将在后续代码块中加入（在处理 price_match 后）
        # 限制：价格不超过5位数字（用户说价格不会超过5个数字）
        price_pattern = re.compile(r'(\d{1,5}(?:\.\d+)?)\s*([wW万mMkK亿]?)')
        
        count_extracted = 0
        
        for text in cleaned_texts:
            if not text or len(text) < 4:
                continue
            
            # 1. 确定交易类型
            trade_type = None
            if any(k in text[:5] for k in buy_keywords):
                trade_type = 'buy'
            elif any(k in text[:5] for k in sell_keywords):
                trade_type = 'sell'
            
            if not trade_type:
                if any(k in text for k in buy_keywords):
                    trade_type = 'buy'
                elif any(k in text for k in sell_keywords):
                    trade_type = 'sell'
            
            if not trade_type:
                if "摊" in text:
                    trade_type = 'sell'
                else:
                    # 默认设为 sell，不再跳过，因为很多时候没有明确关键词 (如 "69飞贼 20W")
                    trade_type = 'sell'

            # 2. 提取价格和物品 - 智能邻近匹配
            clean_line = text
            for k in buy_keywords + sell_keywords:
                clean_line = clean_line.replace(k, " ")
            
            matches = list(price_pattern.finditer(clean_line))
            print(f"[_analyze_texts] Line: {clean_line}")
            print(f"[_analyze_texts] Matches: {[m.group(0) for m in matches]}")
            
            # 记录已匹配的区间 (start, end)，避免重复识别
            matched_ranges = []
            last_search_start = 0
            
            for i, match in enumerate(matches):
                raw_num = match.group(1)
                unit = match.group(2)
                full_price_str = raw_num + unit
                # 验证价格有效性
                price = normalize_price_value(full_price_str)
                if price is None:
                    continue
                
                # --- 过滤误判：时间/数量单位 ---
                # 检查价格后面紧跟的字符，如果是 "点", "级", "号", "个", "人", "张", "次", "倍"
                # 且没有价格单位 (w, 万)，则认为是数量或时间，忽略
                price_end = match.end()
                if not unit and price_end < len(clean_line):
                    next_char = clean_line[price_end]
                    if next_char in ["点", "级", "号", "个", "人", "张", "次", "倍"]:
                        # print(f"[_analyze_texts] 忽略疑似数量/时间: {full_price_str}{next_char} in '{text}'")
                        continue
                
                price_start = match.start()
                
                # Debug print
                # print(f"Checking price {full_price_str} at {price_start}")
                
                # --- 寻找候选物品 ---
                
                # 1. 向前寻找
                segment_before = clean_line[last_search_start:price_start].strip()
                print(f"    SegBefore: '{segment_before}'")
                
                # 如果包含"或者"，则需要找出所有物品
                all_matches_back = []
                all_ranges_back = []  # 对应的ranges
                if "或者" in segment_before or "或" in segment_before:
                    # 尝试找出所有可能的物品
                    # 简单策略：扫描所有词
                    words = segment_before.split()
                    for word in reversed(words):
                        if word in ["或者", "或", "换"]:
                            continue
                        # 尝试匹配整个词
                        m = self.item_matcher.match(word)
                        if not m:
                            # 尝试去除数字
                            stripped = re.sub(r'\d+', '', word).strip()
                            if stripped:
                                m = self.item_matcher.match(stripped)
                        if m and m not in all_matches_back:
                            all_matches_back.append(m)
                            # 计算这个物品的range
                            raw_segment_before = clean_line[last_search_start:price_start]
                            idx = raw_segment_before.rfind(m.raw_name)
                            if idx != -1:
                                abs_start = last_search_start + idx
                                abs_end = abs_start + len(m.raw_name)
                                all_ranges_back.append((abs_start, abs_end))
                
                # 如果没有通过"或者"找到多个，使用常规scan
                match_back = None
                dist_back = float('inf')
                back_range = None
                
                if not all_matches_back:
                    match_back = self.item_matcher.scan(segment_before)
                    if match_back:
                        all_matches_back = [match_back]
                        raw_segment_before = clean_line[last_search_start:price_start]
                        idx = raw_segment_before.rfind(match_back.raw_name)
                        if idx != -1:
                            abs_start = last_search_start + idx
                            abs_end = abs_start + len(match_back.raw_name)
                            all_ranges_back.append((abs_start, abs_end))
                        
                # 计算range（简化：只算第一个匹配的range用于distance）
                if all_matches_back:
                    match_back = all_matches_back[0]  # 用于distance计算
                    if all_ranges_back:
                        back_range = all_ranges_back[0]
                        abs_start, abs_end = back_range
                        raw_segment_before = clean_line[last_search_start:price_start]
                        item_end_in_segment = abs_start - last_search_start + len(match_back.raw_name)
                        dist_back = len(raw_segment_before.rstrip()) - item_end_in_segment
                        print(f"    MatchBack: {[m.standard_name for m in all_matches_back]}")
                
                # 2. 向后寻找
                next_price_start = matches[i+1].start() if i < len(matches) - 1 else len(clean_line)
                segment_after = clean_line[price_end:next_price_start].strip()
                print(f"    SegAfter: '{segment_after}'")
                # Attempt to find multiple items in the segment after the price
                selected_matches_fwd = []
                selected_all_ranges_fwd = []
                dist_fwd = float('inf')
                fwd_range = None
                if segment_after:
                    remaining = segment_after
                    offset = price_end  # absolute position offset in clean_line
                    while remaining:
                        m = self.item_matcher.scan_forward(remaining)
                        if not m:
                            break
                        idx = remaining.find(m.raw_name)
                        if idx == -1:
                            break
                        abs_start = offset + idx
                        abs_end = abs_start + len(m.raw_name)
                        selected_matches_fwd.append(m)
                        selected_all_ranges_fwd.append((abs_start, abs_end))
                        if dist_fwd == float('inf'):
                            dist_fwd = idx
                            fwd_range = (abs_start, abs_end)
                        # Move past this match for next iteration
                        remaining = remaining[idx + len(m.raw_name):]
                        offset = abs_end
                # Fallback: if no forward matches found, try single scan (maintains previous behavior)
                if not selected_matches_fwd and segment_after:
                    match_fwd = self.item_matcher.scan_forward(segment_after)
                    if match_fwd:
                        selected_matches_fwd = [match_fwd]
                        raw_segment_after = clean_line[price_end:next_price_start]
                        idx = raw_segment_after.find(match_fwd.raw_name)
                        if idx != -1:
                            dist_fwd = idx
                            abs_start = price_end + idx
                            abs_end = abs_start + len(match_fwd.raw_name)
                            fwd_range = (abs_start, abs_end)
                            selected_all_ranges_fwd = [(abs_start, abs_end)]
                # --- Skip Level Logic: 如果当前区间没找到，且下一个"价格"看起来像等级，则尝试跨越它寻找 ---
                if not selected_matches_fwd and i < len(matches) - 1:
                    next_match = matches[i+1]
                    nm_str = next_match.group(1)
                    nm_unit = next_match.group(2)
                    nm_val = normalize_price_value(nm_str + nm_unit)
                    if not nm_unit and nm_val and 35 < nm_val < 250:
                        print(f"    Skip Level Candidate: {nm_val}")
                        next_next_start = matches[i+2].start() if i < len(matches) - 2 else len(clean_line)
                        extended_segment = clean_line[price_end:next_next_start]
                        print(f"    Extended Seg: '{extended_segment}'")
                        match_fwd_extended = self.item_matcher.scan(extended_segment)
                        if match_fwd_extended:
                            selected_matches_fwd = [match_fwd_extended]
                            raw_segment_after = clean_line[price_end:next_next_start]
                            idx = raw_segment_after.find(match_fwd_extended.raw_name)
                            if idx != -1:
                                dist_fwd = idx
                                abs_start = price_end + idx
                                abs_end = abs_start + len(match_fwd_extended.raw_name)
                                fwd_range = (abs_start, abs_end)
                                selected_all_ranges_fwd = [(abs_start, abs_end)]
                                print(f"    Skip Level Match: {match_fwd_extended.standard_name}")
                # --- 决策 ---
                selected_match = None
                selected_range = None
                selected_matches = []  # 可能有多个
                selected_all_ranges = []  # 所有物品的ranges
                
                # Helper to check consumption
                def check_consumed(rng):
                    if not rng: return False
                    s, e = rng
                    for rs, re in matched_ranges:
                        if not (e <= rs or s >= re):
                            return True
                    return False

                # Candidates
                cand_back = None
                if match_back:
                    cand_back = {
                        'match': match_back,
                        'range': back_range,
                        'matches': all_matches_back if all_matches_back else [match_back],
                        'ranges': all_ranges_back if all_ranges_back else ([back_range] if back_range else []),
                        'dist': dist_back
                    }
                
                cand_fwd = None
                if selected_matches_fwd:
                    cand_fwd = {
                        'match': selected_matches_fwd[0],
                        'range': fwd_range,
                        'matches': selected_matches_fwd,
                        'ranges': selected_all_ranges_fwd,
                        'dist': dist_fwd
                    }

                # Debug for 5.0
                if price == 5.0:
                    print(f"    Debug 5.0: Back={cand_back}, Fwd={cand_fwd}")
                    if cand_back:
                        print(f"      Back Range: {cand_back['range']}, Consumed: {check_consumed(cand_back['range'])}")
                
                # Selection Logic with Fallback
                if cand_back and cand_fwd:
                    # Prefer closer one
                    if cand_back['dist'] <= cand_fwd['dist']:
                        # Try back first
                        if not check_consumed(cand_back['range']):
                            selected_match = cand_back['match']
                            selected_range = cand_back['range']
                            selected_matches = cand_back['matches']
                            selected_all_ranges = cand_back['ranges']
                        elif not check_consumed(cand_fwd['range']):
                            # Fallback to fwd
                            selected_match = cand_fwd['match']
                            selected_range = cand_fwd['range']
                            selected_matches = cand_fwd['matches']
                            selected_all_ranges = cand_fwd['ranges']
                    else:
                        # Try fwd first
                        if not check_consumed(cand_fwd['range']):
                            selected_match = cand_fwd['match']
                            selected_range = cand_fwd['range']
                            selected_matches = cand_fwd['matches']
                            selected_all_ranges = cand_fwd['ranges']
                        elif not check_consumed(cand_back['range']):
                            # Fallback to back
                            selected_match = cand_back['match']
                            selected_range = cand_back['range']
                            selected_matches = cand_back['matches']
                            selected_all_ranges = cand_back['ranges']
                elif cand_back:
                    if not check_consumed(cand_back['range']):
                        selected_match = cand_back['match']
                        selected_range = cand_back['range']
                        selected_matches = cand_back['matches']
                        selected_all_ranges = cand_back['ranges']
                elif cand_fwd:
                    if not check_consumed(cand_fwd['range']):
                        selected_match = cand_fwd['match']
                        selected_range = cand_fwd['range']
                        selected_matches = cand_fwd['matches']
                        selected_all_ranges = cand_fwd['ranges']
                
                if selected_match:
                    print(f"  Selected: {[m.standard_name for m in selected_matches]}, Ranges: {selected_all_ranges}")
                    
                    # 检查是否已被消耗（只检查第一个range）
                    is_consumed = False
                    if selected_range:
                        sel_start, sel_end = selected_range
                        for r_start, r_end in matched_ranges:
                            # 简单的重叠检查
                            if not (sel_end <= r_start or sel_start >= r_end):
                                is_consumed = True
                                print(f"  Consumed by: {r_start}-{r_end}")
                                break
                    
                    if is_consumed:
                        continue
                    
                    # 价格修正
                    if price > 50000 and not unit: 
                         price = price / 10000.0
                    
                    # --- 过滤误判：等级/属性值 ---
                    is_ignored = False
                    if not unit:
                        if 35 < price < 250:
                            if selected_match.category in ["收费带队", "临时符", "军火/装备"]:
                                is_ignored = True
                                print(f"  Ignored Level/Stat: {price} {selected_match.standard_name}")
                    
                    if not is_ignored:
                        # 记录所有匹配的物品
                        for match_item in selected_matches:
                            self._record_price(match_item, trade_type, price, text, match_item.raw_name)
                            count_extracted += 1
                            print(f"  Recorded: {match_item.standard_name} {price}")
                        
                        # 记录被消耗的区间：价格区间 + 所有物品区间
                        matched_ranges.append((price_start, price_end))
                        for item_range in selected_all_ranges:
                            if item_range:
                                matched_ranges.append(item_range)
                else:
                    print(f"  No match found for {full_price_str}")
                    # 如果价格没有匹配到物品，我们还是记录价格区间，以免它干扰后续扫描
                    matched_ranges.append((price_start, price_end))

            # 3. 再次扫描寻找未匹配价格的物品 (Unpriced Items)
            sorted_ranges = sorted(matched_ranges, key=lambda x: x[0])
            last_idx = 0
            unmatched_chunks = []
            for start, end in sorted_ranges:
                if start > last_idx:
                    unmatched_chunks.append(clean_line[last_idx:start])
                last_idx = max(last_idx, end)
            if last_idx < len(clean_line):
                unmatched_chunks.append(clean_line[last_idx:])
                
            for chunk in unmatched_chunks:
                if not chunk.strip(): continue
                match = self.item_matcher.scan(chunk)
                if match:
                    self._record_price(match, trade_type, 0.0, text, match.raw_name)
                    print(f"  Unpriced item: {match.standard_name}")

            # 3. 补充扫描：寻找未匹配价格的物品
            # 遍历 clean_line 中的每个词，如果它不与 matched_ranges 重叠，且能匹配物品
            
            # 简单的分词策略
            # 为了处理 "收神兜兜 炼兽真经"，我们按空格分割
            # 但我们需要知道每个词在原字符串中的位置
            
            current_pos = 0
            # 使用正则分割保留分隔符，以便计算位置，或者手动遍历
            # 这里简化：假设空格分隔
            
            # 更稳健的方法：正则查找所有非空白片段
            token_iter = re.finditer(r'\S+', clean_line)
            
            for token_match in token_iter:
                token_start = token_match.start()
                token_end = token_match.end()
                token_text = token_match.group()
                
                # 检查是否与已匹配区间重叠
                is_overlapped = False
                for (ms, me) in matched_ranges:
                    # 只要有交集就算重叠
                    if max(token_start, ms) < min(token_end, me):
                        is_overlapped = True
                        break
                
                if is_overlapped:
                    continue
                
                # 尝试匹配物品
                # 排除纯数字 (可能是漏掉的价格部分)
                if re.match(r'^\d+(\.\d+)?[wW万mMkK亿]?$', token_text):
                    continue
                    
                match_info = self.item_matcher.match(token_text)
                if match_info:
                    # 记录无价格物品 (价格设为 0)
                    self._record_price(match_info, trade_type, 0.0, text, match_info.raw_name)
                    count_extracted += 1
                    # 记录区间，避免重复 (虽然这里是单次遍历，但是个好习惯)
                    matched_ranges.append((token_start, token_end))

        print(f"[_analyze_texts] 分析完成，共提取 {count_extracted} 条信息")

    def _record_price(
        self,
        match_info: ItemMatchResult,
        trade_type: str,
        price: float,
        raw_text: str,
        raw_item: Optional[str] = None,
    ):
        """记录价格信息"""
        if not match_info:
            return
        item_name = match_info.standard_name

        if item_name not in self.market_data:
            self.market_data[item_name] = {
                'buy': [],
                'sell': [],
                'latest_time': None,
                'category': match_info.category,
                'subcategory': match_info.subcategory,
            }
        else:
            if 'category' not in self.market_data[item_name]:
                self.market_data[item_name]['category'] = match_info.category
            if 'subcategory' not in self.market_data[item_name]:
                self.market_data[item_name]['subcategory'] = match_info.subcategory
        
        self.market_data[item_name][trade_type].append(price)
        self.market_data[item_name]['latest_time'] = time.time()
        self.market_data[item_name]['confidence'] = match_info.confidence
        
        # 记录原始消息（最多保留100条）
        self.raw_messages.append({
            'item': item_name,
            'category': match_info.category,
            'subcategory': match_info.subcategory,
            'confidence': match_info.confidence,
            'match_method': match_info.method,
            'type': trade_type,
            'price': price,
            'text': raw_text,
            'time': datetime.now().strftime("%H:%M:%S"),
            'raw_item': raw_item or match_info.raw_name or match_info.standard_name,
            'status': 'pending',
        })
        
        # 限制消息数量
        if len(self.raw_messages) > 200:
            self.raw_messages.pop(0)
            
        # 更新物品仓库统计
        self._update_item_repository(item_name, trade_type, price)
        
        self._update_ui()



    def _update_item_repository(self, item_name: str, trade_type: str, price: float):
        """更新物品仓库中的统计信息"""
        now = datetime.now()
        date_key = now.strftime("%Y-%m-%d")

        repo = self.item_repository.setdefault(
            item_name,
            {
                'count': 0,
                'last_seen': None,
                'records': [],
                'daily': {},  # {date: {'buy': [], 'sell': []}}
                'category': None,
                'subcategory': None,
            }
        )

        source_meta = self.market_data.get(item_name, {})
        if not repo.get('category'):
            repo['category'] = source_meta.get('category', '未分类')
        if not repo.get('subcategory'):
            repo['subcategory'] = source_meta.get('subcategory', '未分类')

        repo['count'] = repo.get('count', 0) + 1
        repo['last_seen'] = now.isoformat()

        records = repo.setdefault('records', [])
        records.append({
            'time': now.isoformat(),
            'type': trade_type,
            'price': price
        })
        if len(records) > 200:
            repo['records'] = records[-200:]

        daily = repo.setdefault('daily', {})
        day_entry = daily.setdefault(date_key, {'buy': [], 'sell': []})
        day_entry.setdefault('buy', [])
        day_entry.setdefault('sell', [])
        day_entry[trade_type].append(price)

        # 只保留最近60天的日统计
        cutoff_date = (now - timedelta(days=60)).strftime("%Y-%m-%d")
        for key in list(daily.keys()):
            if key < cutoff_date:
                del daily[key]

    def _get_daily_average(self, daily_data: Dict[str, Dict[str, List[float]]], date_key: str) -> Optional[float]:
        entry = daily_data.get(date_key)
        if not entry:
            return None
        prices: List[float] = []
        for arr in entry.values():
            if arr:
                prices.extend(arr)
        if not prices:
            return None
        return sum(prices) / len(prices)

    def _get_period_average(self, daily_data: Dict[str, Dict[str, List[float]]], date_keys: List[str]) -> Optional[float]:
        prices: List[float] = []
        for key in date_keys:
            entry = daily_data.get(key)
            if not entry:
                continue
            for arr in entry.values():
                if arr:
                    prices.extend(arr)
        if not prices:
            return None
        return sum(prices) / len(prices)

    def _format_trend(self, today_avg: Optional[float], yesterday_avg: Optional[float]) -> str:
        if today_avg is None or yesterday_avg is None:
            return "-"
        diff = today_avg - yesterday_avg
        if abs(diff) < 1e-6:
            return "持平"
        if yesterday_avg == 0:
            return "新增"
        percent = diff / yesterday_avg * 100
        arrow = "↑" if diff > 0 else "↓"
        return f"{arrow}{abs(percent):.1f}%"

    def _update_repository_table(self):
        """更新物品仓库趋势表"""
        if not hasattr(self, "item_table"):
            return

        self.item_table.setRowCount(0)
        if not self.item_repository:
            return

        today = datetime.now().date()
        today_key = today.strftime("%Y-%m-%d")
        yesterday_key = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        week_keys = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

        rows = []
        for item_name, data in self.item_repository.items():
            count = data.get('count', 0)
            records = data.get('records', [])
            latest_price = records[-1]['price'] if records else None
            daily_stats = data.get('daily', {})

            today_avg = self._get_daily_average(daily_stats, today_key)
            yesterday_avg = self._get_daily_average(daily_stats, yesterday_key)
            week_avg = self._get_period_average(daily_stats, week_keys)
            trend = self._format_trend(today_avg, yesterday_avg)

            rows.append({
                'item': item_name,
                'category': data.get('category', '未分类'),
                'subcategory': data.get('subcategory', '未分类'),
                'count': count,
                'latest': latest_price,
                'today_avg': today_avg,
                'yesterday_avg': yesterday_avg,
                'week_avg': week_avg,
                'trend': trend
            })

        rows.sort(key=lambda x: (-x['count'], x['item']))

        for row_data in rows:
            row = self.item_table.rowCount()
            self.item_table.insertRow(row)

            def fmt(value: Optional[float]) -> str:
                return f"{value:.1f}" if isinstance(value, (int, float)) and value is not None else "-"

            label = row_data['item']
            category_tag = f"({row_data.get('category', '-')}/{row_data.get('subcategory', '-')})"
            self.item_table.setItem(row, 0, QTableWidgetItem(f"{label} {category_tag}"))
            self.item_table.setItem(row, 1, QTableWidgetItem(str(row_data['count'])))
            self.item_table.setItem(row, 2, QTableWidgetItem(fmt(row_data['latest'])))
            self.item_table.setItem(row, 3, QTableWidgetItem(fmt(row_data['today_avg'])))
            self.item_table.setItem(row, 4, QTableWidgetItem(fmt(row_data['yesterday_avg'])))
            self.item_table.setItem(row, 5, QTableWidgetItem(fmt(row_data['week_avg'])))
            self.item_table.setItem(row, 6, QTableWidgetItem(row_data['trend']))

    def _update_result_tree(self, rows_data: List[Dict[str, Any]]):
        self.result_tree.clear()
        if not rows_data:
            self.category_stats_label.setText("分类统计：暂无数据")
            return

        stats: Dict[str, Dict[str, Any]] = {}
        for row in rows_data:
            category = row.get('category', '未分类')
            subcategory = row.get('subcategory', '未分类')
            profit = row.get('profit')
            confidence = row.get('confidence')

            cat_entry = stats.setdefault(category, {'count': 0, 'profit_values': [], 'subs': {}})
            cat_entry['count'] += 1
            if profit is not None:
                cat_entry['profit_values'].append(profit)

            sub_entry = cat_entry['subs'].setdefault(subcategory, {'count': 0, 'profit_values': [], 'items': []})
            sub_entry['count'] += 1
            if profit is not None:
                sub_entry['profit_values'].append(profit)
            sub_entry['items'].append({
                'name': row['item'],
                'min_buy': row['min_buy'],
                'max_buy': row['max_buy'],
                'min_sell': row['min_sell'],
                'max_sell': row['max_sell'],
                'profit': profit,
                'confidence': confidence,
            })

        summary_lines = []
        for category in sorted(stats.keys()):
            cat_entry = stats[category]
            profit_values = cat_entry['profit_values']
            cat_avg = sum(profit_values) / len(profit_values) if profit_values else 0
            cat_item = QTreeWidgetItem([
                f"{category} ({cat_entry['count']})",
                f"均利润 {cat_avg:.1f}万" if profit_values else "暂无利润数据"
            ])
            self.result_tree.addTopLevelItem(cat_item)
            summary_lines.append(f"{category}均利润{cat_avg:.1f}万" if profit_values else f"{category}暂无利润")

            for subcategory in sorted(cat_entry['subs'].keys()):
                sub_entry = cat_entry['subs'][subcategory]
                sub_profit_values = sub_entry['profit_values']
                sub_avg = sum(sub_profit_values) / len(sub_profit_values) if sub_profit_values else 0
                sub_item = QTreeWidgetItem([
                    f"{subcategory} ({sub_entry['count']})",
                    f"均利润 {sub_avg:.1f}万" if sub_profit_values else "暂无利润数据"
                ])
                cat_item.addChild(sub_item)

                for item_entry in sub_entry['items']:
                    profit_text = f"{item_entry['profit']:.1f}万" if item_entry['profit'] is not None else "-"
                    confidence_text = f"{item_entry['confidence']:.2f}" if isinstance(item_entry['confidence'], (float, int)) else "-"
                    detail_text = (
                        f"收 {item_entry['min_buy'] or '-'}~{item_entry['max_buy'] or '-'} | "
                        f"卖 {item_entry['min_sell'] or '-'}~{item_entry['max_sell'] or '-'} | "
                        f"利润 {profit_text} | 置信度 {confidence_text}"
                    )
                    sub_item.addChild(QTreeWidgetItem([item_entry['name'], detail_text]))

        self.result_tree.expandAll()
        self.category_stats_label.setText("分类统计：" + "； ".join(summary_lines))

    def _update_ui(self):
        """更新界面显示"""
        # 更新消息列表
        self.message_list.clear()
        for msg in self.raw_messages[-50:]:  # 只显示最近50条
            category = msg.get('category', '-')
            subcategory = msg.get('subcategory', '-')
            confidence = msg.get('confidence')
            confidence_text = f"{confidence:.2f}" if isinstance(confidence, (int, float)) else "-"
            display_text = (
                f"[{msg['time']}] [{category}/{subcategory}] {msg['type']} {msg['item']} "
                f"{msg['price']:.1f}万 (置信度 {confidence_text}) - {msg['text'][:30]}"
            )
            self.message_list.addItem(display_text)
        self.message_list.scrollToBottom()
        
        # 更新市场表格
        self.market_table.setRowCount(0)
        rows_data = []
        cat_filter = self.category_filter_combo.currentData()
        sub_filter = self.subcategory_filter_combo.currentData()
        min_profit_filter = self.min_profit_spin.value()
        
        for item_name, data in self.market_data.items():
            buy_prices = data['buy']
            sell_prices = data['sell']
            
            if not buy_prices and not sell_prices:
                continue
            
            min_buy = min(buy_prices) if buy_prices else None
            max_buy = max(buy_prices) if buy_prices else None
            min_sell = min(sell_prices) if sell_prices else None
            max_sell = max(sell_prices) if sell_prices else None
            
            # 计算利润空间（最低卖价 - 最高收价）
            profit = None
            if min_sell is not None and max_buy is not None:
                profit = min_sell - max_buy
            elif min_sell is not None and min_buy is not None:
                profit = min_sell - min_buy

            category = data.get('category', '未分类')
            subcategory = data.get('subcategory', '未分类')
            confidence = data.get('confidence')

            if cat_filter and category != cat_filter:
                continue
            if sub_filter and subcategory != sub_filter:
                continue
            if min_profit_filter and (profit is None or profit < min_profit_filter):
                continue
            
            rows_data.append({
                'item': item_name,
                'category': category,
                'subcategory': subcategory,
                'confidence': confidence,
                'min_buy': min_buy,
                'max_buy': max_buy,
                'min_sell': min_sell,
                'max_sell': max_sell,
                'profit': profit,
                'buy_prices': buy_prices,
                'sell_prices': sell_prices,
            })
        
        # 按利润排序（有利润的优先，然后按利润从高到低）
        rows_data.sort(key=lambda x: (x['profit'] is None, -(x['profit'] or 0)))
        
        # 填充表格
        for row_data in rows_data:
            row = self.market_table.rowCount()
            self.market_table.insertRow(row)
            
            item_label = row_data['item']
            category = row_data.get('category', '未分类')
            subcategory = row_data.get('subcategory', '未分类')
            self.market_table.setItem(row, 0, QTableWidgetItem(f"{item_label} ({category}/{subcategory})"))
            self.market_table.setItem(row, 1, QTableWidgetItem(f"{row_data['min_buy']:.1f}" if row_data['min_buy'] else "-"))
            self.market_table.setItem(row, 2, QTableWidgetItem(f"{row_data['max_buy']:.1f}" if row_data['max_buy'] else "-"))
            self.market_table.setItem(row, 3, QTableWidgetItem(f"{row_data['min_sell']:.1f}" if row_data['min_sell'] else "-"))
            self.market_table.setItem(row, 4, QTableWidgetItem(f"{row_data['max_sell']:.1f}" if row_data['max_sell'] else "-"))
            profit_text = f"{row_data['profit']:.1f}" if row_data['profit'] is not None else "-"
            if row_data['profit'] and row_data['profit'] > 0:
                profit_text += " ✓"
            profit_item = QTableWidgetItem(profit_text)
            if row_data['profit'] and row_data['profit'] > 0:
                profit_item.setForeground(Qt.GlobalColor.green)
            self.market_table.setItem(row, 5, profit_item)

        self._update_result_tree(rows_data)
        
        # 更新物品趋势表
        self._update_repository_table()
        
        # 更新状态
        total_items = len(self.market_data)
        total_messages = len(self.raw_messages)
        repo_count = len(self.item_repository)
        self.status_label.setText(
            f"状态：识别中... | 物品数：{total_items} | 消息数：{total_messages} | 仓库：{repo_count}"
        )

    def _clear_data(self):
        """清空数据"""
        reply = QMessageBox.question(
            self,
            "确认清空",
            "确定要清空所有市场数据吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.market_data.clear()
            self.raw_messages.clear()
            self.item_repository.clear()
            self._update_ui()

    def _save_market_data(self):
        """保存市场数据"""
        data_file = os.path.join(os.path.dirname(__file__), "novels_data", "market_data.json")
        os.makedirs(os.path.dirname(data_file), exist_ok=True)
        try:
            with open(data_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'market_data': self.market_data,
                    'raw_messages': self.raw_messages[-100:],  # 只保存最近100条
                    'item_repository': self.item_repository
                }, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", f"无法保存数据：{exc}")

    def _load_market_data(self):
        """加载市场数据"""
        data_file = os.path.join(os.path.dirname(__file__), "novels_data", "market_data.json")
        if os.path.exists(data_file):
            try:
                with open(data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.market_data = data.get('market_data', {})
                    self.raw_messages = data.get('raw_messages', [])
                    self.item_repository = data.get('item_repository', {}) or {}
                    if not isinstance(self.item_repository, dict):
                        self.item_repository = {}
                    for msg in self.raw_messages:
                        if isinstance(msg, dict):
                            msg.setdefault('status', 'pending')
                            msg.setdefault('raw_item', msg.get('item', ''))
                    for meta in self.market_data.values():
                        if isinstance(meta, dict):
                            meta.setdefault('category', '未分类')
                            meta.setdefault('subcategory', '未分类')
                            meta.setdefault('confidence', None)
                    added_alias = False
                    for item_name in list(self.market_data.keys()):
                        added_alias |= self._ensure_alias_entry(item_name, save=False)
                    for item_name in list(self.item_repository.keys()):
                        added_alias |= self._ensure_alias_entry(item_name, save=False)
                    if added_alias:
                        self.item_alias_exact, self.item_alias_contains = self._build_item_alias_rules()
                        self._save_item_aliases()
                    self._update_ui()
            except Exception as exc:
                QMessageBox.warning(self, "加载失败", f"无法加载数据：{exc}")

    def closeEvent(self, event):
        """关闭时保存数据"""
        if self.is_capturing:
            self._stop_capture()
        self._save_market_data()
        super().closeEvent(event)


class ItemAliasDialog(QDialog):
    """物品别名管理对话框"""

    def __init__(
        self,
        alias_config: Dict[str, Dict[str, object]],
        default_config: Dict[str, Dict[str, object]],
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("物品名管理")
        self.resize(920, 480)
        self.category_choices = ITEM_CATEGORY_CHOICES
        self.category_tree = CATEGORY_TREE
        self.subcategory_placeholder = "未分类"
        self.default_config = copy.deepcopy(default_config)
        self.current_filter_category: Optional[str] = None
        self.current_filter_subcategory: Optional[str] = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("说明：设置标准物品名、所属大类，以及逗号分隔的别名（含错别字写法）。"))
        layout.addWidget(QLabel("提示：可用“恢复默认”重建系统词典，或“清空全部”从空白开始。"))

        content_layout = QHBoxLayout()
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderHidden(True)
        self.tree_widget.setMaximumWidth(220)
        content_layout.addWidget(self.tree_widget)

        self.table = QTableWidget(self)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["标准名称", "一级分类", "二级分类", "别名（逗号分隔）"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.AllEditTriggers)
        content_layout.addWidget(self.table, stretch=1)

        controls_layout = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜索标准名称或别名")
        self.search_box.textChanged.connect(self._apply_filter)
        controls_layout.addWidget(QLabel("搜索："))
        controls_layout.addWidget(self.search_box)
        layout.addLayout(controls_layout)
        layout.addLayout(content_layout)

        for canonical, meta in alias_config.items():
            aliases = meta.get("aliases", []) if isinstance(meta, dict) else meta
            category = meta.get("category", DEFAULT_ITEM_CATEGORY) if isinstance(meta, dict) else DEFAULT_ITEM_CATEGORY
            subcategory = meta.get("subcategory", self.subcategory_placeholder)
            self._append_row(canonical, category, subcategory, ",".join(aliases))
        self._populate_category_tree()
        self.tree_widget.currentItemChanged.connect(self._on_tree_selection_changed)

        button_layout = QHBoxLayout()
        self.add_button = QPushButton("新增")
        self.add_button.clicked.connect(self._add_row)
        self.remove_button = QPushButton("删除选中")
        self.remove_button.clicked.connect(self._remove_selected_rows)
        self.clear_button = QPushButton("清空全部")
        self.clear_button.clicked.connect(self._clear_all_rows)
        self.reset_button = QPushButton("恢复默认")
        self.reset_button.clicked.connect(self._reset_to_default)
        button_layout.addWidget(self.add_button)
        button_layout.addWidget(self.remove_button)
        button_layout.addWidget(self.clear_button)
        button_layout.addWidget(self.reset_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def _append_row(self, canonical: str = "", category: Optional[str] = None, subcategory: Optional[str] = None, variants: str = ""):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(canonical))

        category_combo = QComboBox()
        category_combo.addItems(self.category_choices)
        category_combo.setCurrentText(category if category in self.category_choices else DEFAULT_ITEM_CATEGORY)
        category_combo.currentTextChanged.connect(lambda text, r=row: self._on_category_changed(r, text))
        self.table.setCellWidget(row, 1, category_combo)

        subcategory_combo = QComboBox()
        self._populate_subcategory_combo(subcategory_combo, category_combo.currentText(), subcategory)
        self.table.setCellWidget(row, 2, subcategory_combo)

        self.table.setItem(row, 3, QTableWidgetItem(variants))
        self._apply_filter()

    def _add_row(self):
        self._append_row()

    def _remove_selected_rows(self):
        selected_rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in selected_rows:
            self.table.removeRow(row)
        self._apply_filter()

    def _clear_all_rows(self):
        if QMessageBox.question(self, "确认", "确定要清空所有词条吗？") == QMessageBox.StandardButton.Yes:
            self.table.setRowCount(0)

    def _reset_to_default(self):
        if QMessageBox.question(self, "确认", "将恢复系统默认词典，继续吗？") != QMessageBox.StandardButton.Yes:
            return
        self.table.setRowCount(0)
        for canonical, meta in self.default_config.items():
            aliases = meta.get("aliases", [])
            category = meta.get("category", DEFAULT_ITEM_CATEGORY)
            subcategory = meta.get("subcategory", self.subcategory_placeholder)
            self._append_row(canonical, category, subcategory, ",".join(aliases))
        self._apply_filter()

    def _apply_filter(self):
        visible_rows: Set[int] = set()
        for row in range(self.table.rowCount()):
            combo = self.table.cellWidget(row, 1)
            sub_combo = self.table.cellWidget(row, 2)
            row_category = combo.currentText() if isinstance(combo, QComboBox) else DEFAULT_ITEM_CATEGORY
            row_subcategory = sub_combo.currentText() if isinstance(sub_combo, QComboBox) else self.subcategory_placeholder
            name_item = self.table.item(row, 0)
            alias_item = self.table.item(row, 3)
            row_name = name_item.text() if name_item else ""
            row_aliases = alias_item.text() if alias_item else ""
            search_text = self.search_box.text().strip()
            name_match = True
            if search_text:
                lower = search_text.lower()
                name_match = lower in row_name.lower() or lower in row_aliases.lower()
            hide = False
            if self.current_filter_category and row_category != self.current_filter_category:
                hide = True
            if not hide and self.current_filter_subcategory and row_subcategory != self.current_filter_subcategory:
                hide = True
            if not hide and not name_match:
                hide = True
            self.table.setRowHidden(row, hide)
            if not hide:
                visible_rows.add(row)
        self._refresh_tree_counts(visible_rows)

    def _refresh_tree_counts(self, visible_rows: Set[int]):
        counts: Dict[Tuple[Optional[str], Optional[str]], int] = {}
        for row in visible_rows:
            combo = self.table.cellWidget(row, 1)
            sub_combo = self.table.cellWidget(row, 2)
            row_category = combo.currentText() if isinstance(combo, QComboBox) else DEFAULT_ITEM_CATEGORY
            row_subcategory = sub_combo.currentText() if isinstance(sub_combo, QComboBox) else self.subcategory_placeholder
            counts[(None, None)] = counts.get((None, None), 0) + 1
            counts[(row_category, None)] = counts.get((row_category, None), 0) + 1
            counts[(row_category, row_subcategory)] = counts.get((row_category, row_subcategory), 0) + 1

        def update_item_labels(item: QTreeWidgetItem):
            data = item.data(0, Qt.ItemDataRole.UserRole)
            base_text = item.text(0).split(' (')[0]
            count = counts.get(data, 0)
            if count:
                item.setText(0, f"{base_text} ({count})")
            else:
                item.setText(0, base_text)
            for idx in range(item.childCount()):
                update_item_labels(item.child(idx))

        for idx in range(self.tree_widget.topLevelItemCount()):
            update_item_labels(self.tree_widget.topLevelItem(idx))

    def _populate_category_tree(self):
        self.tree_widget.blockSignals(True)
        self.tree_widget.clear()
        root = QTreeWidgetItem(["全部"])
        root.setData(0, Qt.ItemDataRole.UserRole, (None, None))
        self.tree_widget.addTopLevelItem(root)

        for cat in self.category_choices:
            cat_item = QTreeWidgetItem([cat])
            cat_item.setData(0, Qt.ItemDataRole.UserRole, (cat, None))
            root.addChild(cat_item)
            subcategories = self.category_tree.get(cat, {})
            if subcategories:
                for sub_cat in sorted(subcategories.keys()):
                    sub_item = QTreeWidgetItem([sub_cat])
                    sub_item.setData(0, Qt.ItemDataRole.UserRole, (cat, sub_cat))
                    cat_item.addChild(sub_item)
        self.tree_widget.expandAll()
        self.tree_widget.setCurrentItem(root)
        self.tree_widget.blockSignals(False)

    def _on_tree_selection_changed(self, current: Optional[QTreeWidgetItem], _previous: Optional[QTreeWidgetItem]):
        if not current:
            self.current_filter_category = None
            self.current_filter_subcategory = None
        else:
            cat, sub = current.data(0, Qt.ItemDataRole.UserRole)
            self.current_filter_category = cat
            self.current_filter_subcategory = sub
        self._apply_filter()

    def _populate_subcategory_combo(self, combo: QComboBox, category: str, preferred: Optional[str]):
        combo.blockSignals(True)
        combo.clear()
        options = list(self.category_tree.get(category, {}).keys())
        if not options:
            options = [self.subcategory_placeholder]
        combo.addItems(options)
        if preferred in options:
            combo.setCurrentText(preferred)
        else:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _on_category_changed(self, row: int, category: str):
        sub_combo = self.table.cellWidget(row, 2)
        if isinstance(sub_combo, QComboBox):
            self._populate_subcategory_combo(sub_combo, category, sub_combo.currentText())
        self._apply_filter()

    def get_alias_config(self) -> Dict[str, Dict[str, object]]:
        config: Dict[str, Dict[str, object]] = {}
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            alias_item = self.table.item(row, 3)
            combo = self.table.cellWidget(row, 1)
            sub_combo = self.table.cellWidget(row, 2)
            canonical = name_item.text().strip() if name_item else ""
            if not canonical:
                continue
            aliases: List[str] = []
            if alias_item and alias_item.text().strip():
                aliases = [a.strip() for a in alias_item.text().split(",") if a.strip()]
            if not aliases:
                aliases = [canonical]
            if canonical not in aliases:
                aliases.insert(0, canonical)
            category = combo.currentText() if isinstance(combo, QComboBox) else DEFAULT_ITEM_CATEGORY
            subcategory = sub_combo.currentText() if isinstance(sub_combo, QComboBox) else self.subcategory_placeholder
            config[canonical] = {
                "aliases": aliases,
                "category": category or DEFAULT_ITEM_CATEGORY,
                "subcategory": subcategory or self.subcategory_placeholder,
            }
        return config


class LearningCenterDialog(QDialog):
    """持续学习与反馈面板"""

    STATUS_LABELS = {
        "pending": "待处理",
        "confirmed": "已确认",
        "ignored": "已忽略",
        "learned": "已学习",
    }

    def __init__(
        self,
        raw_messages: List[Dict[str, Any]],
        alias_config: Dict[str, Dict[str, object]],
        category_tree: Dict[str, Dict[str, List[str]]],
        apply_callback,
        status_callback,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("持续学习中心")
        self.resize(1080, 620)
        self.raw_messages = raw_messages
        self.alias_config = alias_config
        self.category_tree = category_tree
        self.apply_callback = apply_callback
        self.status_callback = status_callback
        self.filtered_indices: List[int] = []
        self.selected_index: Optional[int] = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("说明：筛查低置信度记录，手动确认或纠正后将写入物品词典，实现持续学习。"))

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("状态："))
        self.status_filter_combo = QComboBox()
        self.status_filter_combo.addItem("全部", None)
        for key, text in self.STATUS_LABELS.items():
            self.status_filter_combo.addItem(text, key)
        self.status_filter_combo.currentIndexChanged.connect(self._refresh_table)
        filter_layout.addWidget(self.status_filter_combo)

        filter_layout.addWidget(QLabel("最低置信度："))
        self.confidence_spin = QDoubleSpinBox()
        self.confidence_spin.setRange(0.0, 1.0)
        self.confidence_spin.setSingleStep(0.05)
        self.confidence_spin.setDecimals(2)
        self.confidence_spin.setValue(0.0)
        self.confidence_spin.valueChanged.connect(self._refresh_table)
        filter_layout.addWidget(self.confidence_spin)

        filter_layout.addWidget(QLabel("搜索："))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("原始物品名 / 匹配结果 / 原文关键字")
        self.search_edit.textChanged.connect(self._refresh_table)
        filter_layout.addWidget(self.search_edit)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        self.summary_label = QLabel("暂无记录")
        layout.addWidget(self.summary_label)

        self.table = QTableWidget()
        self.table.setColumnCount(11)
        self.table.setHorizontalHeaderLabels([
            "序号", "时间", "原识别", "匹配结果", "分类", "子类",
            "价格", "类型", "置信度", "状态", "来源文本"
        ])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self.table, stretch=1)

        detail_group = QGroupBox("纠正与学习")
        grid = QGridLayout(detail_group)

        self.selected_raw_label = QLabel("-")
        grid.addWidget(QLabel("原识别："), 0, 0)
        grid.addWidget(self.selected_raw_label, 0, 1, 1, 3)

        self.canonical_edit = QLineEdit()
        grid.addWidget(QLabel("标准名称："), 1, 0)
        grid.addWidget(self.canonical_edit, 1, 1)

        self.category_combo = QComboBox()
        self.category_combo.addItems(ITEM_CATEGORY_CHOICES)
        self.category_combo.currentTextChanged.connect(self._on_category_changed)
        grid.addWidget(QLabel("一级分类："), 1, 2)
        grid.addWidget(self.category_combo, 1, 3)

        self.subcategory_combo = QComboBox()
        grid.addWidget(QLabel("二级分类："), 2, 0)
        grid.addWidget(self.subcategory_combo, 2, 1)

        self.alias_edit = QLineEdit()
        self.alias_edit.setPlaceholderText("额外别名（可选）")
        grid.addWidget(QLabel("新增别名："), 2, 2)
        grid.addWidget(self.alias_edit, 2, 3)

        self.auto_alias_checkbox = QCheckBox("自动学习原识别词（推荐）")
        self.auto_alias_checkbox.setChecked(True)
        grid.addWidget(self.auto_alias_checkbox, 3, 0, 1, 2)

        self.status_info = QLabel("")
        grid.addWidget(self.status_info, 3, 2, 1, 2)

        button_layout = QHBoxLayout()
        self.confirm_button = QPushButton("标记为正确")
        self.confirm_button.clicked.connect(lambda: self._mark_status('confirmed'))
        button_layout.addWidget(self.confirm_button)

        self.ignore_button = QPushButton("标记为忽略")
        self.ignore_button.clicked.connect(lambda: self._mark_status('ignored'))
        button_layout.addWidget(self.ignore_button)

        self.apply_button = QPushButton("纠正并学习")
        self.apply_button.clicked.connect(self._apply_learning)
        button_layout.addWidget(self.apply_button)

        button_layout.addStretch()
        grid.addLayout(button_layout, 4, 0, 1, 4)

        layout.addWidget(detail_group)
        self._refresh_table()
        self._update_form_enabled(False)

    def _refresh_table(self):
        self.table.setRowCount(0)
        self.filtered_indices = []
        status_filter = self.status_filter_combo.currentData()
        min_conf = self.confidence_spin.value() or 0.0
        keyword = self.search_edit.text().strip().lower()

        total = 0
        low_conf = 0
        for idx in range(len(self.raw_messages) - 1, -1, -1):
            msg = self.raw_messages[idx]
            if not isinstance(msg, dict):
                continue
            status = msg.get('status', 'pending')
            confidence = float(msg.get('confidence') or 0)
            if status_filter and status != status_filter:
                continue
            if confidence < min_conf:
                continue
            combined = " ".join([
                msg.get('raw_item', ''),
                msg.get('item', ''),
                msg.get('text', ''),
            ]).lower()
            if keyword and keyword not in combined:
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.filtered_indices.append(idx)
            total += 1
            if confidence < 0.45:
                low_conf += 1

            self.table.setItem(row, 0, QTableWidgetItem(str(idx + 1)))
            self.table.setItem(row, 1, QTableWidgetItem(msg.get('time', '-')))
            self.table.setItem(row, 2, QTableWidgetItem(msg.get('raw_item', '-')))
            self.table.setItem(row, 3, QTableWidgetItem(msg.get('item', '-')))
            self.table.setItem(row, 4, QTableWidgetItem(msg.get('category', '-')))
            self.table.setItem(row, 5, QTableWidgetItem(msg.get('subcategory', '-')))
            price_value = msg.get('price')
            if isinstance(price_value, (int, float)):
                price_text = f"{price_value:.1f}"
            else:
                price_text = "-"
            self.table.setItem(row, 6, QTableWidgetItem(price_text))
            trade_type = msg.get('type')
            trade_label = "收购" if trade_type == 'buy' else "出售"
            self.table.setItem(row, 7, QTableWidgetItem(trade_label))
            self.table.setItem(row, 8, QTableWidgetItem(f"{confidence:.2f}"))
            self.table.setItem(row, 9, QTableWidgetItem(self.STATUS_LABELS.get(status, status)))
            text_item = QTableWidgetItem(msg.get('text', '')[:80])
            self.table.setItem(row, 10, text_item)

        self.summary_label.setText(f"共 {total} 条（低置信度 {low_conf} 条）")
        self.selected_index = None
        self._update_form_enabled(False)

    def _current_message_index(self) -> Optional[int]:
        selection = self.table.selectedIndexes()
        if not selection or not self.filtered_indices:
            return None
        row = selection[0].row()
        if 0 <= row < len(self.filtered_indices):
            return self.filtered_indices[row]
        return None

    def _on_selection_changed(self):
        idx = self._current_message_index()
        self.selected_index = idx
        if idx is None:
            self._update_form_enabled(False)
            self.selected_raw_label.setText("-")
            self.canonical_edit.clear()
            self.alias_edit.clear()
            self.status_info.clear()
            return
        message = self.raw_messages[idx]
        self.selected_raw_label.setText(message.get('raw_item', '-'))
        self.canonical_edit.setText(message.get('item', ''))
        category = message.get('category', DEFAULT_ITEM_CATEGORY)
        subcategory = message.get('subcategory', "未分类")
        if category not in ITEM_CATEGORY_CHOICES:
            category = DEFAULT_ITEM_CATEGORY
        self.category_combo.blockSignals(True)
        self.category_combo.setCurrentText(category)
        self.category_combo.blockSignals(False)
        self._populate_subcategories(category, subcategory)
        self.alias_edit.clear()
        status = message.get('status', 'pending')
        self.status_info.setText(f"当前状态：{self.STATUS_LABELS.get(status, status)}")
        self._update_form_enabled(True)

    def _populate_subcategories(self, category: str, preferred: Optional[str]):
        self.subcategory_combo.blockSignals(True)
        self.subcategory_combo.clear()
        options = list(self.category_tree.get(category, {}).keys())
        if not options:
            options = ["未分类"]
        self.subcategory_combo.addItems(options)
        if preferred in options:
            self.subcategory_combo.setCurrentText(preferred)
        else:
            self.subcategory_combo.setCurrentIndex(0)
        self.subcategory_combo.blockSignals(False)

    def _on_category_changed(self, category: str):
        self._populate_subcategories(category, self.subcategory_combo.currentText())

    def _mark_status(self, status: str):
        idx = self._current_message_index()
        if idx is None:
            QMessageBox.warning(self, "提示", "请先选择一条记录。")
            return
        success, info = self.status_callback(idx, status)
        if success:
            QMessageBox.information(self, "完成", info)
            self._refresh_table()
            self.status_info.setText(f"当前状态：{self.STATUS_LABELS.get(status, status)}")
        else:
            QMessageBox.warning(self, "失败", info)

    def _apply_learning(self):
        idx = self._current_message_index()
        if idx is None:
            QMessageBox.warning(self, "提示", "请先选择一条记录。")
            return
        canonical = self.canonical_edit.text().strip()
        category = self.category_combo.currentText()
        subcategory = self.subcategory_combo.currentText()
        extra_alias = self.alias_edit.text().strip() or None
        if not canonical:
            QMessageBox.warning(self, "提示", "请输入标准名称。")
            return
        success, info = self.apply_callback(
            idx,
            canonical,
            category,
            subcategory,
            extra_alias,
            self.auto_alias_checkbox.isChecked(),
        )
        if success:
            QMessageBox.information(self, "完成", info)
            self._refresh_table()
        else:
            QMessageBox.warning(self, "失败", info)

    def _update_form_enabled(self, enabled: bool):
        for widget in [
            self.canonical_edit,
            self.category_combo,
            self.subcategory_combo,
            self.alias_edit,
            self.auto_alias_checkbox,
            self.confirm_button,
            self.ignore_button,
            self.apply_button,
        ]:
            widget.setEnabled(enabled)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("梦幻阅读")
        self.resize(1100, 720)

        self.manager = NovelManager()
        self.manager.refresh_db_defaults()

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.novel_tab = NovelListTab(self.manager, parent=self)
        self.download_tab = DownloadTab(self.manager, parent=self)
        self.alarm_tab = AlarmTab(parent=self)
        self.ledger_tab = ProfitLedgerTab(parent=self)
        self.daily_brief_tab = DailyBriefTab(parent=self)
        self.video_tab = VideoPlayerTab(parent=self)
        self.transfer_tab = FileTransferTab(parent=self)
        self.market_tab = MarketAnalysisTab(parent=self)

        self.tabs.addTab(self.novel_tab, "小说列表")
        self.tabs.addTab(self.download_tab, "下载小说")
        self.tabs.addTab(self.alarm_tab, "闹钟提醒")
        self.tabs.addTab(self.ledger_tab, "收益记账")
        self.tabs.addTab(self.video_tab, "本地播放器")
        self.tabs.addTab(self.daily_brief_tab, "每日简报")
        self.tabs.addTab(self.transfer_tab, "互传文件")
        self.tabs.addTab(self.market_tab, "市场分析")
        from market_analysis_v2 import UltimatePriceTrendTab
        self.trend_tab = UltimatePriceTrendTab()
        self.tabs.addTab(self.trend_tab, "价格趋势")

    def on_novel_imported(self, novel_id: str, info: Dict):
        """供下载页回调：自动导入后刷新列表并选中"""
        self.novel_tab.refresh_novel_list()
        self.novel_tab._select_novel_by_id(novel_id)
        self.tabs.setCurrentWidget(self.novel_tab)
        QMessageBox.information(
            self,
            "已导入小说",
            f"检测到新下载的小说文件，已自动导入：{info.get('title', '')}",
        )

    def closeEvent(self, event):
        if hasattr(self, "transfer_tab"):
            self.transfer_tab.stop_server()
        super().closeEvent(event)


def exception_handler(exc_type, exc_value, exc_traceback):
    """全局异常处理函数"""
    if issubclass(exc_type, KeyboardInterrupt):
        # 允许Ctrl+C正常退出
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    import traceback
    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print(f"未捕获的异常: {error_msg}")
    
    # 尝试显示错误对话框
    try:
        from PyQt6.QtWidgets import QMessageBox
        app = QApplication.instance()
        if app:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setWindowTitle("程序错误")
            msg.setText(f"发生未捕获的异常：\n{exc_type.__name__}: {exc_value}")
            msg.setDetailedText(error_msg)
            msg.exec()
    except:
        pass

def main():
    # 设置全局异常处理
    sys.excepthook = exception_handler
    
    # 设置线程异常处理
    import threading
    threading.excepthook = lambda args: exception_handler(args.exc_type, args.exc_value, args.exc_traceback)
    
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()


