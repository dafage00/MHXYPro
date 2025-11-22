# -*- coding: utf-8 -*-
"""
小说获取模块
支持从多个小说源自动获取小说内容
"""

import re
import time
import json
from typing import List, Dict, Optional
import urllib.parse

# 可选依赖，用于在线获取
try:
    import requests
    from bs4 import BeautifulSoup
    HAS_ONLINE_SUPPORT = True
except ImportError:
    HAS_ONLINE_SUPPORT = False


class NovelFetcher:
    """小说获取器基类"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        if HAS_ONLINE_SUPPORT:
            self.session = requests.Session()
            self.session.headers.update(self.headers)
        else:
            self.session = None
    
    def search_novel(self, keyword: str) -> List[Dict]:
        """搜索小说"""
        raise NotImplementedError
    
    def get_novel_info(self, novel_url: str) -> Dict:
        """获取小说信息"""
        raise NotImplementedError
    
    def get_chapter_list(self, novel_url: str) -> List[Dict]:
        """获取章节列表"""
        raise NotImplementedError
    
    def get_chapter_content(self, chapter_url: str) -> str:
        """获取章节内容"""
        raise NotImplementedError


class GenericNovelFetcher(NovelFetcher):
    """通用小说获取器 - 支持从文本文件或URL直接读取"""
    
    def __init__(self):
        # 不调用super().__init__()，因为不需要网络功能
        self.headers = {}
        self.session = None
    
    def search_novel(self, keyword: str) -> List[Dict]:
        """搜索小说 - 支持本地文件"""
        results = []
        # 检查是否是本地文件路径
        import os
        if os.path.exists(keyword):
            results.append({
                'title': os.path.basename(keyword),
                'author': '本地文件',
                'url': keyword,
                'source': 'local'
            })
        return results
    
    def get_novel_info(self, novel_url: str) -> Dict:
        """获取小说信息"""
        import os
        if os.path.exists(novel_url):
            return {
                'title': os.path.basename(novel_url),
                'author': '本地文件',
                'description': '本地小说文件',
                'url': novel_url
            }
        return {}
    
    def get_chapter_list(self, novel_url: str) -> List[Dict]:
        """获取章节列表 - 从本地文件读取"""
        import os
        if not os.path.exists(novel_url):
            return []
        
        chapters = []
        try:
            with open(novel_url, 'r', encoding='utf-8') as f:
                content = f.read()
                # 尝试按章节分割
                chapter_matches = self._extract_chapter_matches(content)
                chapter_matches = self._trim_toc_matches(content, chapter_matches)
                
                if chapter_matches:
                    # 有章节标记，按章节分割
                    for i, match in enumerate(chapter_matches):
                        start = match.start()
                        end = chapter_matches[i + 1].start() if i + 1 < len(chapter_matches) else len(content)
                        chapter_title = match.group().strip()
                        chapters.append({
                            'title': chapter_title,
                            'url': f'{novel_url}#{i}',
                            'index': i
                        })
                else:
                    # 没有章节标记，按段落分割
                    paragraphs = content.split('\n\n')
                    chunk_size = 50  # 每50段为一章
                    for i in range(0, len(paragraphs), chunk_size):
                        chapters.append({
                            'title': f'第 {i // chunk_size + 1} 部分',
                            'url': f'{novel_url}#{i // chunk_size}',
                            'index': i // chunk_size
                        })
        except Exception as e:
            print(f"读取文件错误: {e}")
        
        return chapters
    
    def get_chapter_content(self, chapter_url: str) -> str:
        """获取章节内容"""
        import os
        # 解析URL，提取文件路径和章节索引
        if '#' in chapter_url:
            file_path, chapter_index = chapter_url.rsplit('#', 1)
            chapter_index = int(chapter_index)
        else:
            file_path = chapter_url
            chapter_index = 0
        
        if not os.path.exists(file_path):
            return "文件不存在"
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
                chapter_matches = self._extract_chapter_matches(content)
                chapter_matches = self._trim_toc_matches(content, chapter_matches)
                
                if chapter_matches:
                    # 有章节标记
                    if chapter_index < len(chapter_matches):
                        start = chapter_matches[chapter_index].start()
                        end = chapter_matches[chapter_index + 1].start() if chapter_index + 1 < len(chapter_matches) else len(content)
                        return content[start:end].strip()
                    else:
                        return "章节不存在"
                else:
                    # 没有章节标记，按段落分割
                    paragraphs = content.split('\n\n')
                    chunk_size = 50
                    start_idx = chapter_index * chunk_size
                    end_idx = min(start_idx + chunk_size, len(paragraphs))
                    if start_idx < len(paragraphs):
                        return '\n\n'.join(paragraphs[start_idx:end_idx])
                    else:
                        return "章节不存在"
        except Exception as e:
            return f"读取错误: {e}"

    @staticmethod
    def _extract_chapter_matches(content: str):
        """根据内容提取最佳章节匹配结果"""
        patterns = [
            r'第[一二三四五六七八九十百千万\d]+章[^\n]*',
            r'第\d+章[^\n]*',
            r'第\s*\d+\s*章[^\n]*',
            r'Chapter\s+\d+[^\n]*',
            r'CHAPTER\s+\d+[^\n]*'
        ]
        best_matches = []
        best_start = None
        best_count = 0
        for pattern in patterns:
            matches = list(re.finditer(pattern, content))
            if not matches:
                continue
            first_start = matches[0].start()
            count = len(matches)
            if best_start is None or first_start < best_start or (first_start == best_start and count > best_count):
                best_matches = matches
                best_start = first_start
                best_count = count
        return best_matches

    @staticmethod
    def _trim_toc_matches(content: str, matches):
        """移除正文前的目录章节匹配"""
        if not matches:
            return matches
        GAP_THRESHOLD = 800
        content_length = len(content)
        for idx, match in enumerate(matches[:-1]):
            next_start = matches[idx + 1].start()
            gap = max(0, next_start - match.start())
            if gap >= GAP_THRESHOLD:
                return matches[idx + 1:]
        return matches


class OnlineNovelFetcher(NovelFetcher):
    """在线小说获取器 - 支持从网站获取小说"""
    
    def __init__(self, base_url: str = ""):
        if not HAS_ONLINE_SUPPORT:
            raise ImportError("需要安装requests和beautifulsoup4才能使用在线功能")
        super().__init__()
        self.base_url = base_url
    
    def search_novel(self, keyword: str) -> List[Dict]:
        """搜索小说"""
        # 这里可以实现具体的搜索逻辑
        # 由于涉及版权问题，这里只提供框架
        return []
    
    def get_novel_info(self, novel_url: str) -> Dict:
        """获取小说信息"""
        try:
            response = self.session.get(novel_url, timeout=10)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 这里需要根据具体网站结构解析
            # 仅提供示例框架
            return {
                'title': '示例小说',
                'author': '示例作者',
                'description': '示例描述',
                'url': novel_url
            }
        except Exception as e:
            print(f"获取小说信息错误: {e}")
            return {}
    
    def get_chapter_list(self, novel_url: str) -> List[Dict]:
        """获取章节列表"""
        # 这里需要根据具体网站结构解析
        return []
    
    def get_chapter_content(self, chapter_url: str) -> str:
        """获取章节内容"""
        try:
            response = self.session.get(chapter_url, timeout=10)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 这里需要根据具体网站结构解析内容
            # 仅提供示例框架
            return "章节内容获取功能需要根据具体网站实现"
        except Exception as e:
            return f"获取章节内容错误: {e}"


def create_fetcher(source_type: str = "local") -> NovelFetcher:
    """创建小说获取器"""
    if source_type == "local":
        return GenericNovelFetcher()
    else:
        return OnlineNovelFetcher()

