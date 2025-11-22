# -*- coding: utf-8 -*-
"""
小说管理器
负责小说的存储、读取和管理
"""

import json
import os
from typing import List, Dict, Optional
from datetime import datetime


class NovelManager:
    """小说管理器"""
    
    def __init__(self, data_dir: str = "novels_data"):
        self.data_dir = data_dir
        self.download_cache_dir = os.path.join(self.data_dir, "download_cache")
        self.db_file = os.path.join(data_dir, "novels_db.json")
        self.ensure_data_dir()
        self.ensure_download_cache()
        self.novels_db = self.load_db()
    
    def ensure_data_dir(self):
        """确保数据目录存在"""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    def ensure_download_cache(self):
        """确保下载缓存目录存在"""
        if not os.path.exists(self.download_cache_dir):
            os.makedirs(self.download_cache_dir)
    
    def load_db(self) -> Dict:
        """加载数据库"""
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if not isinstance(data, dict):
                        data = {}
                    self.novels_db = data
                    self._ensure_db_defaults()
                    return self.novels_db
            except Exception as e:
                print(f"加载数据库错误: {e}")
                return {}
        self.novels_db = {
            'novels': [],
            'reading_history': [],
            'bookmarks': {},
            'reading_stats': {},
            'processed_downloads': []
        }
        return self.novels_db

    def _ensure_db_defaults(self):
        """确保数据库包含必要的字段"""
        if 'novels' not in self.novels_db:
            self.novels_db['novels'] = []
        if 'reading_history' not in self.novels_db:
            self.novels_db['reading_history'] = []
        if 'bookmarks' not in self.novels_db:
            self.novels_db['bookmarks'] = {}
        if 'reading_stats' not in self.novels_db:
            self.novels_db['reading_stats'] = {}
        if 'processed_downloads' not in self.novels_db:
            self.novels_db['processed_downloads'] = []

    def refresh_db_defaults(self):
        """刷新数据库默认字段"""
        self._ensure_db_defaults()
        self.save_db()
    
    def save_db(self):
        """保存数据库"""
        try:
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(self.novels_db, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存数据库错误: {e}")
    
    def add_novel(self, novel_info: Dict) -> str:
        """添加小说"""
        self._ensure_db_defaults()
        novel_id = f"novel_{len(self.novels_db.get('novels', [])) + 1}"
        novel_data = {
            'id': novel_id,
            'title': novel_info.get('title', '未知标题'),
            'author': novel_info.get('author', '未知作者'),
            'description': novel_info.get('description', ''),
            'url': novel_info.get('url', ''),
            'source': novel_info.get('source', 'local'),
            'added_time': datetime.now().isoformat(),
            'last_read_time': None,
            'current_chapter': 0,
            'total_chapters': 0
        }
        
        if 'novels' not in self.novels_db:
            self.novels_db['novels'] = []
        
        self.novels_db['novels'].append(novel_data)
        self.save_db()
        return novel_id
    
    def get_novel(self, novel_id: str) -> Optional[Dict]:
        """获取小说信息"""
        for novel in self.novels_db.get('novels', []):
            if novel.get('id') == novel_id:
                return novel
        return None
    
    def get_all_novels(self) -> List[Dict]:
        """获取所有小说"""
        self._ensure_db_defaults()
        return self.novels_db.get('novels', [])
    
    def update_reading_progress(self, novel_id: str, chapter_index: int):
        """更新阅读进度"""
        self._ensure_db_defaults()
        novel = self.get_novel(novel_id)
        if novel:
            novel['current_chapter'] = chapter_index
            novel['last_read_time'] = datetime.now().isoformat()
            self.save_db()
    
    def delete_novel(self, novel_id: str):
        """删除小说"""
        self._ensure_db_defaults()
        self.novels_db['novels'] = [
            n for n in self.novels_db.get('novels', [])
            if n.get('id') != novel_id
        ]
        self.save_db()
    
    def add_reading_history(self, novel_id: str, chapter_index: int, chapter_title: str):
        """添加阅读历史"""
        self._ensure_db_defaults()
        
        history_entry = {
            'novel_id': novel_id,
            'chapter_index': chapter_index,
            'chapter_title': chapter_title,
            'read_time': datetime.now().isoformat()
        }
        
        self.novels_db['reading_history'].insert(0, history_entry)
        # 只保留最近100条历史记录
        self.novels_db['reading_history'] = self.novels_db['reading_history'][:100]
        self.save_db()
    
    def get_reading_history(self, limit: int = 20) -> List[Dict]:
        """获取阅读历史"""
        return self.novels_db.get('reading_history', [])[:limit]
    
    def add_bookmark(self, novel_id: str, chapter_index: int, chapter_title: str, position: int = 0, note: str = ""):
        """添加书签"""
        self._ensure_db_defaults()
        
        if novel_id not in self.novels_db['bookmarks']:
            self.novels_db['bookmarks'][novel_id] = []
        
        bookmark = {
            'chapter_index': chapter_index,
            'chapter_title': chapter_title,
            'position': position,
            'note': note,
            'created_time': datetime.now().isoformat()
        }
        
        self.novels_db['bookmarks'][novel_id].append(bookmark)
        self.save_db()
        return len(self.novels_db['bookmarks'][novel_id]) - 1
    
    def get_bookmarks(self, novel_id: str) -> List[Dict]:
        """获取小说的所有书签"""
        return self.novels_db.get('bookmarks', {}).get(novel_id, [])
    
    def delete_bookmark(self, novel_id: str, bookmark_index: int):
        """删除书签"""
        self._ensure_db_defaults()
        if novel_id in self.novels_db.get('bookmarks', {}):
            bookmarks = self.novels_db['bookmarks'][novel_id]
            if 0 <= bookmark_index < len(bookmarks):
                del bookmarks[bookmark_index]
                self.save_db()
                return True
        return False
    
    def update_reading_stats(self, novel_id: str, reading_time: float = 0, words_read: int = 0):
        """更新阅读统计"""
        self._ensure_db_defaults()
        
        if novel_id not in self.novels_db['reading_stats']:
            self.novels_db['reading_stats'][novel_id] = {
                'total_reading_time': 0.0,
                'total_words_read': 0,
                'last_update_time': datetime.now().isoformat()
            }
        
        stats = self.novels_db['reading_stats'][novel_id]
        stats['total_reading_time'] = stats.get('total_reading_time', 0.0) + reading_time
        stats['total_words_read'] = stats.get('total_words_read', 0) + words_read
        stats['last_update_time'] = datetime.now().isoformat()
        self.save_db()
    
    def get_reading_stats(self, novel_id: str) -> Dict:
        """获取阅读统计"""
        self._ensure_db_defaults()
        return self.novels_db.get('reading_stats', {}).get(novel_id, {
            'total_reading_time': 0.0,
            'total_words_read': 0,
            'last_update_time': None
        })

    def get_download_cache_path(self) -> str:
        """获取下载缓存目录路径"""
        return self.download_cache_dir

    def _generate_download_signature(self, file_path: str, file_size: int, modified_time: float) -> str:
        """生成下载文件签名"""
        return f"{os.path.abspath(file_path)}|{file_size}|{int(modified_time)}"

    def is_download_processed(self, file_path: str, file_size: int, modified_time: float) -> bool:
        """判断下载文件是否已被处理"""
        self._ensure_db_defaults()
        signature = self._generate_download_signature(file_path, file_size, modified_time)
        return signature in self.novels_db.get('processed_downloads', [])

    def mark_download_processed(self, file_path: str, file_size: int, modified_time: float):
        """标记下载文件已处理"""
        self._ensure_db_defaults()
        signature = self._generate_download_signature(file_path, file_size, modified_time)
        processed = self.novels_db.setdefault('processed_downloads', [])
        if signature not in processed:
            processed.append(signature)
            # 避免无限增长，保留最近100条
            self.novels_db['processed_downloads'] = processed[-100:]
            self.save_db()



