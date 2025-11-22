# -*- coding: utf-8 -*-
"""
小说阅读器主程序
提供GUI界面用于阅读和管理小说
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import sys
import time
import threading
import queue
import subprocess
from novel_fetcher import create_fetcher
from novel_manager import NovelManager
from tts_manager import TTSManager


class NovelReaderApp:
    """小说阅读器应用"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("小说阅读器")
        self.root.geometry("1000x700")
        
        # 初始化管理器
        self.manager = NovelManager()
        self.manager.refresh_db_defaults()
        self.fetcher = create_fetcher("local")
        self.download_cache_dir = self.manager.get_download_cache_path()
        self.download_queue = queue.Queue()
        self.download_monitor_stop = threading.Event()
        self.download_monitor_thread = None
        self.active_webview_process = None
        self.download_tip_shown = False
        self.queued_downloads = set()
        
        # 当前阅读的小说
        self.current_novel = None
        self.current_chapters = []
        self.current_chapter_index = 0
        
        # 字体设置
        self.font_size = 12
        self.font_family = "微软雅黑"
        
        # 阅读统计
        self.reading_start_time = None
        self.last_stats_update = None
        
        # 初始化TTS管理器
        self.tts_manager = TTSManager()
        self.tts_manager.set_word_callback(self.on_tts_word)
        
        # 绑定快捷键
        self.setup_shortcuts()
        
        # 创建界面
        self.create_widgets()
        
        # 加载小说列表
        self.refresh_novel_list()

        # 启动下载监控
        self.start_download_monitor()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def create_widgets(self):
        """创建界面组件"""
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 配置网格权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=0, minsize=260)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        # 左侧面板 - 小说列表
        left_panel = ttk.Frame(main_frame, width=260)
        left_panel.grid(row=0, column=0, rowspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 10))
        left_panel.grid_propagate(False)
        left_panel.columnconfigure(0, weight=1)
        left_panel.rowconfigure(1, weight=1)
        
        # 工具栏
        toolbar = ttk.Frame(left_panel)
        toolbar.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        toolbar.columnconfigure(0, weight=1)
        
        ttk.Button(toolbar, text="添加小说", command=self.add_novel).grid(row=0, column=0, sticky=(tk.W, tk.E), padx=(0, 5))
        ttk.Button(toolbar, text="删除小说", command=self.delete_novel).grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 5))
        ttk.Button(toolbar, text="下载小说", command=self.open_download_window).grid(row=0, column=2, sticky=(tk.W, tk.E), padx=(0, 5))
        ttk.Button(toolbar, text="书签", command=self.show_bookmarks).grid(row=0, column=3, sticky=(tk.W, tk.E), padx=(0, 5))
        ttk.Button(toolbar, text="统计", command=self.show_stats).grid(row=0, column=4, sticky=(tk.W, tk.E))
        
        # 小说列表
        list_frame = ttk.Frame(left_panel)
        list_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        # 创建列表和滚动条
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        self.novel_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, font=("微软雅黑", 10))
        self.novel_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.novel_listbox.bind('<<ListboxSelect>>', self.on_novel_select)
        self.novel_listbox.bind('<Double-Button-1>', self.open_novel)
        
        scrollbar.config(command=self.novel_listbox.yview)
        
        # 右侧面板 - 阅读区域
        right_panel = ttk.Frame(main_frame)
        right_panel.grid(row=0, column=1, rowspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(4, weight=1)
        
        # 标题栏
        title_frame = ttk.Frame(right_panel)
        title_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        title_frame.columnconfigure(1, weight=1)
        
        self.title_label = ttk.Label(title_frame, text="请选择一本小说", font=("微软雅黑", 14, "bold"))
        self.title_label.grid(row=0, column=0, columnspan=2, sticky=tk.W)
        
        self.author_label = ttk.Label(title_frame, text="", font=("微软雅黑", 10))
        self.author_label.grid(row=1, column=0, columnspan=2, sticky=tk.W)
        
        # 章节导航
        nav_frame = ttk.Frame(right_panel)
        nav_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        nav_frame.columnconfigure(1, weight=1)
        
        ttk.Button(nav_frame, text="上一章", command=self.prev_chapter).grid(row=0, column=0, padx=(0, 5))
        ttk.Button(nav_frame, text="下一章", command=self.next_chapter).grid(row=0, column=2, padx=(5, 0))
        
        self.chapter_label = ttk.Label(nav_frame, text="", font=("微软雅黑", 10))
        self.chapter_label.grid(row=0, column=1, sticky=tk.W+tk.E)
        
        # 章节选择下拉框
        self.chapter_combo = ttk.Combobox(nav_frame, state="readonly", width=30)
        self.chapter_combo.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(5, 0))
        self.chapter_combo.bind('<<ComboboxSelected>>', self.on_chapter_select)
        
        # 搜索和字体控制
        control_frame = ttk.Frame(right_panel)
        control_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        control_frame.columnconfigure(1, weight=1)
        
        # 搜索框
        search_frame = ttk.Frame(control_frame)
        search_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 5))
        search_frame.columnconfigure(1, weight=1)
        
        ttk.Label(search_frame, text="搜索:", font=("微软雅黑", 9)).grid(row=0, column=0, padx=(0, 5))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, font=("微软雅黑", 9))
        self.search_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 5))
        self.search_entry.bind('<Return>', lambda e: self.search_text())
        self.search_entry.bind('<KeyRelease>', self.on_search_key_release)
        
        ttk.Button(search_frame, text="搜索", command=self.search_text).grid(row=0, column=2, padx=(0, 5))
        ttk.Button(search_frame, text="上一个", command=self.search_prev).grid(row=0, column=3, padx=(0, 5))
        ttk.Button(search_frame, text="下一个", command=self.search_next).grid(row=0, column=4)
        
        self.search_results = []
        self.current_search_index = -1
        
        # 字体大小控制
        font_frame = ttk.Frame(control_frame)
        font_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E))
        
        ttk.Label(font_frame, text="字体大小:", font=("微软雅黑", 9)).grid(row=0, column=0, padx=(0, 5))
        ttk.Button(font_frame, text="A-", command=self.decrease_font).grid(row=0, column=1, padx=(0, 5))
        self.font_size_label = ttk.Label(font_frame, text="12", font=("微软雅黑", 9), width=5)
        self.font_size_label.grid(row=0, column=2, padx=(0, 5))
        ttk.Button(font_frame, text="A+", command=self.increase_font).grid(row=0, column=3, padx=(0, 5))
        
        ttk.Button(font_frame, text="添加书签", command=self.add_bookmark).grid(row=0, column=4, padx=(10, 0))
        
        # 语音朗读控制区域
        tts_frame = ttk.LabelFrame(right_panel, text="语音朗读", padding="5")
        tts_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        tts_frame.columnconfigure(2, weight=1)
        
        # 语音选择
        voice_label = ttk.Label(tts_frame, text="语音:", font=("微软雅黑", 9))
        voice_label.grid(row=0, column=0, padx=(0, 5))
        
        # 获取可用语音列表
        self.available_voices = []
        try:
            self.available_voices = self.tts_manager.get_available_voice_names()
        except:
            pass
        
        # 语音下拉框
        self.voice_var = tk.StringVar()
        self.voice_combo = ttk.Combobox(tts_frame, textvariable=self.voice_var, 
                                        state="readonly", width=40, font=("微软雅黑", 9))
        self.voice_combo.grid(row=0, column=1, columnspan=2, padx=(0, 10), sticky=(tk.W, tk.E))
        self.voice_combo.bind('<<ComboboxSelected>>', self.on_voice_select)
        
        # 更新语音列表
        self.update_voice_list()
        
        # 朗读控制按钮
        button_frame = ttk.Frame(tts_frame)
        button_frame.grid(row=0, column=3, columnspan=2, sticky=tk.E)
        
        self.test_button = ttk.Button(button_frame, text="试听声音", command=self.test_voice)
        self.test_button.grid(row=0, column=0, padx=(10, 5))
        
        self.play_button = ttk.Button(button_frame, text="开始朗读", command=self.start_reading)
        self.play_button.grid(row=0, column=1, padx=5)
        
        self.stop_button = ttk.Button(button_frame, text="停止", command=self.stop_reading)
        self.stop_button.grid(row=0, column=2, padx=5)
        
        # 语速控制
        speed_frame = ttk.Frame(tts_frame)
        speed_frame.grid(row=1, column=0, columnspan=5, sticky=(tk.W, tk.E), pady=(5, 0))
        
        speed_label = ttk.Label(speed_frame, text="语速:", font=("微软雅黑", 9))
        speed_label.grid(row=0, column=0, padx=(0, 5))
        
        self.speed_var = tk.IntVar(value=150)
        self.speed_scale = ttk.Scale(speed_frame, from_=50, to=300, orient=tk.HORIZONTAL,
                                     variable=self.speed_var, length=200,
                                     command=self.on_speed_change)
        self.speed_scale.grid(row=0, column=1, padx=(0, 5))
        
        self.speed_label = ttk.Label(speed_frame, text="150", font=("微软雅黑", 9), width=5)
        self.speed_label.grid(row=0, column=2)
        
        # 检查TTS是否可用（PowerShell TTS总是可用，所以这里主要检查pyttsx3）
        if not self.tts_manager.is_available():
            warning_text = "(使用PowerShell TTS，功能正常)"
        else:
            warning_text = ""
        
        self.voice_warning_label = ttk.Label(tts_frame, text=warning_text,
                                             font=("微软雅黑", 8), foreground="gray")
        self.voice_warning_label.grid(row=2, column=0, columnspan=5, pady=(5, 0), sticky=tk.W)
        
        # 延迟更新语音列表（因为TTS管理器可能还在初始化）
        self.root.after(500, self.update_voice_list)
        
        # 阅读区域
        text_frame = ttk.Frame(right_panel)
        text_frame.grid(row=4, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        
        self.content_text = scrolledtext.ScrolledText(
            text_frame,
            wrap=tk.WORD,
            font=(self.font_family, self.font_size),
            bg="#F5F5F5",
            padx=20,
            pady=20,
            spacing1=5,
            spacing2=2,
            spacing3=5
        )
        self.content_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.content_text.tag_configure("tts_highlight", background="#cfe8ff")
        self.content_text.tag_configure("search_highlight", background="#ffff00")
        
        # 状态栏
        status_frame = ttk.Frame(right_panel)
        status_frame.grid(row=5, column=0, sticky=(tk.W, tk.E), pady=(10, 0))
        status_frame.columnconfigure(0, weight=1)
        
        self.status_label = ttk.Label(status_frame, text="就绪", font=("微软雅黑", 9))
        self.status_label.grid(row=0, column=0, sticky=tk.W)
        
        self.stats_label = ttk.Label(status_frame, text="", font=("微软雅黑", 8), foreground="gray")
        self.stats_label.grid(row=0, column=1, sticky=tk.E)
    
    def refresh_novel_list(self):
        """刷新小说列表"""
        self.novel_listbox.delete(0, tk.END)
        novels = self.manager.get_all_novels()
        for novel in novels:
            title = novel.get('title', '未知标题')
            author = novel.get('author', '未知作者')
            display_text = f"{title} - {author}"
            self.novel_listbox.insert(tk.END, display_text)
    
    def add_novel(self):
        """添加小说"""
        file_path = filedialog.askopenfilename(
            title="选择小说文件",
            filetypes=[
                ("文本文件", "*.txt"),
                ("所有文件", "*.*")
            ]
        )
        
        if file_path:
            try:
                # 获取小说信息
                novel_info = self.fetcher.get_novel_info(file_path)
                if not novel_info:
                    novel_info = {
                        'title': os.path.basename(file_path),
                        'author': '未知作者',
                        'description': '',
                        'url': file_path,
                        'source': 'local'
                    }
                
                # 添加到管理器
                novel_id = self.manager.add_novel(novel_info)
                
                # 刷新列表
                self.refresh_novel_list()
                
                # 选中新添加的小说
                novels = self.manager.get_all_novels()
                for i, novel in enumerate(novels):
                    if novel.get('id') == novel_id:
                        self.novel_listbox.selection_set(i)
                        self.novel_listbox.see(i)
                        break
                
                messagebox.showinfo("成功", f"已添加小说: {novel_info['title']}")
            except Exception as e:
                messagebox.showerror("错误", f"添加小说失败: {e}")

    def open_download_window(self):
        """打开下载小说的内嵌浏览器"""
        if self.active_webview_process and self.active_webview_process.poll() is None:
            messagebox.showinfo("提示", "下载窗口已打开，请切换到已有窗口。")
            return
        if not self.download_tip_shown:
            messagebox.showinfo(
                "使用提示",
                f"请在打开的浏览器中搜索小说，并将TXT文件保存到以下目录：\n{self.download_cache_dir}\n"
                "保存完成后，程序会自动导入。"
            )
            self.download_tip_shown = True

        launcher_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "download_browser.py")
        if not os.path.exists(launcher_path):
            messagebox.showerror("错误", f"找不到浏览器启动脚本：{launcher_path}")
            return

        default_url = "https://www.biquge66.net/"
        try:
            self.active_webview_process = subprocess.Popen(
                [
                    sys.executable,
                    launcher_path,
                    "--url",
                    default_url,
                    "--download-dir",
                    self.download_cache_dir
                ]
            )
        except Exception as exc:
            messagebox.showerror("错误", f"打开下载窗口失败: {exc}")
    
    def delete_novel(self):
        """删除小说"""
        selection = self.novel_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要删除的小说")
            return
        
        if messagebox.askyesno("确认", "确定要删除选中的小说吗？"):
            index = selection[0]
            novels = self.manager.get_all_novels()
            if index < len(novels):
                novel_id = novels[index].get('id')
                self.manager.delete_novel(novel_id)
                self.refresh_novel_list()
                
                # 如果删除的是当前阅读的小说，清空阅读区域
                if self.current_novel and self.current_novel.get('id') == novel_id:
                    self.current_novel = None
                    self.current_chapters = []
                    self.update_display()
    
    def on_novel_select(self, event):
        """小说选择事件"""
        selection = self.novel_listbox.curselection()
        if selection:
            index = selection[0]
            novels = self.manager.get_all_novels()
            if index < len(novels):
                novel = novels[index]
                # 显示小说信息（但不加载内容）
                self.title_label.config(text=novel.get('title', '未知标题'))
                self.author_label.config(text=f"作者: {novel.get('author', '未知作者')}")
    
    def open_novel(self, event):
        """打开小说"""
        selection = self.novel_listbox.curselection()
        if not selection:
            return
        
        index = selection[0]
        novels = self.manager.get_all_novels()
        if index >= len(novels):
            return
        
        novel = novels[index]
        self.load_novel(novel)
    
    def load_novel(self, novel: dict):
        """加载小说"""
        try:
            self.status_label.config(text="正在加载小说...")
            self.root.update()
            
            self.current_novel = novel
            novel_url = novel.get('url', '')
            
            # 获取章节列表
            self.current_chapters = self.fetcher.get_chapter_list(novel_url)
            
            # 更新章节下拉框
            chapter_titles = [ch.get('title', f'章节 {i+1}') for i, ch in enumerate(self.current_chapters)]
            self.chapter_combo['values'] = chapter_titles
            
            # 恢复阅读进度
            current_chapter = novel.get('current_chapter', 0)
            if current_chapter < len(self.current_chapters):
                self.current_chapter_index = current_chapter
            else:
                self.current_chapter_index = 0
            
            # 更新章节选择
            if chapter_titles:
                self.chapter_combo.current(self.current_chapter_index)
            
            # 加载章节内容
            self.load_chapter_content()
            
            # 更新显示
            self.update_display()
            
            # 启动阅读统计计时
            self.reading_start_time = time.time()
            self.last_stats_update = None
            self.update_reading_stats_periodically()
            
            self.status_label.config(text="加载完成")
        except Exception as e:
            messagebox.showerror("错误", f"加载小说失败: {e}")
            self.status_label.config(text="加载失败")
    
    def load_chapter_content(self):
        """加载章节内容"""
        if not self.current_novel or not self.current_chapters:
            return
        
        if self.current_chapter_index >= len(self.current_chapters):
            return
        
        try:
            chapter = self.current_chapters[self.current_chapter_index]
            chapter_url = chapter.get('url', '')
            
            self.status_label.config(text="正在加载章节内容...")
            self.root.update()
            
            content = self.fetcher.get_chapter_content(chapter_url)
            
            # 显示内容
            self.content_text.delete(1.0, tk.END)
            self.content_text.insert(1.0, content)
            self.clear_highlight()
            
            # 重置滚动位置到顶部
            self.content_text.see(1.0)
            self.content_text.mark_set(tk.INSERT, 1.0)
            # 强制更新显示，确保滚动位置正确
            self.root.update_idletasks()
            
            # 更新阅读进度
            self.manager.update_reading_progress(
                self.current_novel.get('id'),
                self.current_chapter_index
            )
            
            # 添加阅读历史
            self.manager.add_reading_history(
                self.current_novel.get('id'),
                self.current_chapter_index,
                chapter.get('title', '')
            )
            
            self.status_label.config(text="就绪")
        except Exception as e:
            messagebox.showerror("错误", f"加载章节内容失败: {e}")
            self.status_label.config(text="加载失败")
    
    def update_display(self):
        """更新显示"""
        if self.current_novel:
            self.title_label.config(text=self.current_novel.get('title', '未知标题'))
            self.author_label.config(text=f"作者: {self.current_novel.get('author', '未知作者')}")
            
            if self.current_chapters and self.current_chapter_index < len(self.current_chapters):
                chapter = self.current_chapters[self.current_chapter_index]
                self.chapter_label.config(text=f"第 {self.current_chapter_index + 1} / {len(self.current_chapters)} 章")
        else:
            self.title_label.config(text="请选择一本小说")
            self.author_label.config(text="")
            self.chapter_label.config(text="")
            self.content_text.delete(1.0, tk.END)
            # 重置滚动位置
            self.content_text.see(1.0)
            self.content_text.mark_set(tk.INSERT, 1.0)
    
    def prev_chapter(self):
        """上一章"""
        if not self.current_chapters:
            return
        
        if self.current_chapter_index > 0:
            self.current_chapter_index -= 1
            self.chapter_combo.current(self.current_chapter_index)
            self.load_chapter_content()
            self.update_display()
    
    def next_chapter(self):
        """下一章"""
        if not self.current_chapters:
            return
        
        if self.current_chapter_index < len(self.current_chapters) - 1:
            self.current_chapter_index += 1
            self.chapter_combo.current(self.current_chapter_index)
            self.load_chapter_content()
            self.update_display()
    
    def on_chapter_select(self, event):
        """章节选择事件"""
        if not self.current_chapters:
            return
        
        selection = self.chapter_combo.current()
        if selection >= 0 and selection < len(self.current_chapters):
            self.current_chapter_index = selection
            self.load_chapter_content()
            self.update_display()
    
    def update_voice_list(self):
        """更新语音列表"""
        try:
            voices = self.tts_manager.get_available_voice_names()
            if voices:
                self.voice_combo['values'] = voices
                # 设置默认选择（如果有）
                if not self.voice_var.get() and voices:
                    # 尝试选择中文语音或第一个
                    for voice in voices:
                        if "中文" in voice or "Chinese" in voice or "ZH" in voice:
                            self.voice_var.set(voice)
                            self.tts_manager.set_voice_by_name(voice)
                            break
                    else:
                        self.voice_var.set(voices[0])
                        self.tts_manager.set_voice_by_name(voices[0])
            else:
                self.voice_combo['values'] = ["未找到可用语音"]
                self.voice_var.set("未找到可用语音")
        except Exception as e:
            print(f"更新语音列表错误: {e}")
            self.voice_combo['values'] = ["无法加载语音列表"]
    
    def on_voice_select(self, event=None):
        """语音选择改变事件"""
        selected_voice = self.voice_var.get()
        if selected_voice and selected_voice not in ["未找到可用语音", "无法加载语音列表"]:
            success = self.tts_manager.set_voice_by_name(selected_voice)
            if success:
                self.status_label.config(text=f"已选择语音: {selected_voice}")
            else:
                self.status_label.config(text=f"选择语音失败: {selected_voice}")
    
    def on_voice_change(self):
        """语音类型改变事件（兼容旧代码）"""
        # 这个方法保留用于兼容，但现在使用on_voice_select
        self.on_voice_select()
    
    def on_speed_change(self, value=None):
        """语速改变事件"""
        try:
            speed = int(float(self.speed_var.get()))
            self.speed_label.config(text=str(speed))
            self.tts_manager.set_rate(speed)
            # 实时更新状态
            self.status_label.config(text=f"语速已设置为: {speed}")
        except Exception as e:
            print(f"设置语速错误: {e}")
    
    def test_voice(self):
        """试听声音"""
        try:
            if not self.tts_manager.is_available():
                error_msg = "TTS功能不可用"
                if hasattr(self.tts_manager, 'init_error') and self.tts_manager.init_error:
                    error_msg += f"\n错误信息: {self.tts_manager.init_error}"
                else:
                    error_msg += "，请先安装pyttsx3库"
                messagebox.showwarning("警告", error_msg)
                return
            
            # 检查engine是否真的可用
            if not hasattr(self.tts_manager, 'engine') or self.tts_manager.engine is None:
                messagebox.showerror("错误", "TTS引擎未初始化，无法试听")
                return
            
            # 如果正在朗读，先停止
            if self.tts_manager.is_speaking:
                try:
                    self.tts_manager.stop()
                    time.sleep(0.2)  # 等待停止完成
                except Exception as stop_error:
                    print(f"停止当前朗读时出错: {stop_error}")
            
            # 设置语音和语速
            selected_voice = self.voice_var.get()
            speed = int(self.speed_var.get())
            
            print(f"试听设置: 语音={selected_voice}, 语速={speed}")
            
            # 设置语音
            if selected_voice and selected_voice not in ["未找到可用语音", "无法加载语音列表"]:
                success = self.tts_manager.set_voice_by_name(selected_voice)
                if not success:
                    messagebox.showwarning("警告", f"无法设置语音 {selected_voice}，请检查系统语音设置")
                    return
            else:
                messagebox.showwarning("警告", "请先选择一个有效的语音")
                return
            
            try:
                self.tts_manager.set_rate(speed)
            except Exception as rate_error:
                print(f"设置语速错误: {rate_error}")
                # 继续执行，语速设置失败可能不影响试听
            
            # 试听
            self.clear_highlight()
            
            # 更新按钮状态（在调用test_voice之前）
            self.test_button.config(state='disabled', text="试听中...")
            self.status_label.config(text=f"正在试听: {selected_voice}...")
            
            # 调用test_voice
            self.tts_manager.test_voice(callback=self.on_test_finished)
            
        except Exception as e:
            # 捕获所有异常，防止程序崩溃
            error_msg = f"试听功能出错: {str(e)}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            
            # 恢复按钮状态
            self.test_button.config(state='normal', text="试听声音")
            self.status_label.config(text="试听失败")
            
            # 显示错误信息
            messagebox.showerror("错误", f"试听时发生错误：\n{error_msg}\n\n请检查TTS设置或查看控制台输出获取详细信息。")
    
    def on_tts_word(self, start, end):
        """TTS开始朗读某个词时回调"""
        try:
            if start is None or end is None:
                return
            def highlight():
                try:
                    self._highlight_text_range(start, end)
                except Exception as e:
                    print(f"高亮文本错误: {e}")
            self.root.after(0, highlight)
        except Exception as e:
            print(f"TTS单词回调错误: {e}")

    def _highlight_text_range(self, start: int, end: int):
        try:
            if start < 0 or end <= start:
                return
            self.content_text.tag_remove("tts_highlight", "1.0", tk.END)
            start_index = f"1.0 + {start} chars"
            end_index = f"1.0 + {end} chars"
            self.content_text.tag_add("tts_highlight", start_index, end_index)
            self.content_text.see(start_index)
        except Exception as e:
            print(f"高亮文本范围错误: {e}")

    def clear_highlight(self):
        self.content_text.tag_remove("tts_highlight", "1.0", tk.END)

    def start_reading(self):
        """开始朗读"""
        try:
            print("开始朗读按钮被点击")
            
            if not self.tts_manager.is_available():
                error_msg = "TTS功能不可用"
                if hasattr(self.tts_manager, 'init_error') and self.tts_manager.init_error:
                    error_msg += f"\n错误信息: {self.tts_manager.init_error}"
                else:
                    error_msg += "，请先安装pyttsx3库"
                messagebox.showwarning("警告", error_msg)
                return
            
            # 检查engine是否真的可用
            if not hasattr(self.tts_manager, 'engine') or self.tts_manager.engine is None:
                messagebox.showerror("错误", "TTS引擎未初始化，无法朗读")
                return
            
            # 获取当前显示的文本
            try:
                content = self.content_text.get(1.0, tk.END).strip()
                print(f"获取到的文本内容长度: {len(content)}")
            except Exception as get_error:
                print(f"获取文本内容错误: {get_error}")
                messagebox.showerror("错误", f"无法获取文本内容：{get_error}")
                return
            
            if not content:
                messagebox.showinfo("提示", "当前没有可朗读的内容")
                return
            
            # 显示文本预览
            preview = content[:50] if len(content) > 50 else content
            print(f"文本预览: {preview}...")
            
            # 设置语音和语速
            try:
                selected_voice = self.voice_var.get()
                speed = int(self.speed_var.get())
                print(f"设置: 语音={selected_voice}, 语速={speed}")
                
                # 设置语音
                if selected_voice and selected_voice not in ["未找到可用语音", "无法加载语音列表"]:
                    success = self.tts_manager.set_voice_by_name(selected_voice)
                    if not success:
                        print(f"警告: 无法设置语音 {selected_voice}，将使用默认语音")
                else:
                    print("警告: 未选择有效语音，将使用默认语音")
            except Exception as var_error:
                print(f"获取语音设置错误: {var_error}")
                speed = 150
            
            try:
                self.tts_manager.set_rate(speed)
            except Exception as rate_error:
                print(f"设置语速错误: {rate_error}")
                # 继续执行，语速设置失败可能不影响朗读
            
            # 开始朗读
            print("调用speak方法开始朗读...")
            self.clear_highlight()
            
            # 更新按钮状态（在调用speak之前）
            self.play_button.config(state='disabled', text="朗读中...")
            self.stop_button.config(state='normal')
            self.status_label.config(text="正在朗读...")
            print("按钮状态已更新")
            
            # 调用speak方法
            try:
                self.tts_manager.speak(content, callback=self.on_reading_finished)
            except Exception as speak_error:
                # 如果speak调用失败，恢复按钮状态
                self.play_button.config(state='normal', text="开始朗读")
                self.stop_button.config(state='disabled')
                self.status_label.config(text="朗读启动失败")
                error_msg = f"启动朗读失败：{str(speak_error)}"
                print(error_msg)
                import traceback
                traceback.print_exc()
                messagebox.showerror("错误", error_msg)
                
        except Exception as e:
            # 捕获所有未预期的异常
            error_msg = f"朗读功能出错: {str(e)}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            
            # 恢复按钮状态
            try:
                self.play_button.config(state='normal', text="开始朗读")
                self.stop_button.config(state='disabled')
                self.status_label.config(text="朗读失败")
            except:
                pass
            
            # 显示错误信息
            try:
                messagebox.showerror("错误", f"朗读时发生错误：\n{error_msg}\n\n请检查TTS设置或查看控制台输出获取详细信息。")
            except:
                print("无法显示错误对话框")
    
    def stop_reading(self):
        """停止朗读"""
        self.tts_manager.stop()
        self.clear_highlight()
        self.play_button.config(state='normal', text="开始朗读")
        self.test_button.config(state='normal', text="试听声音")
        self.stop_button.config(state='disabled')
        self.status_label.config(text="已停止朗读")
    
    def on_test_finished(self, success: bool, message: str):
        """试听完成回调"""
        # 在主线程中更新UI，使用更安全的方式
        try:
            self.root.after(0, lambda s=success, m=message: self._update_test_status(s, m))
        except Exception as e:
            print(f"安排回调函数错误: {e}")
            # 如果after失败，直接在主线程中调用（如果当前在主线程）
            try:
                self._update_test_status(success, message)
            except Exception as e2:
                print(f"更新测试状态错误: {e2}")
    
    def _update_test_status(self, success: bool, message: str):
        """更新试听状态（在主线程中调用）"""
        try:
            self.test_button.config(state='normal', text="试听声音")
            
            if success:
                self.status_label.config(text="试听完成")
            else:
                self.status_label.config(text=f"试听失败: {message}")
                # 使用after延迟显示错误对话框，避免在回调中直接显示
                self.root.after(100, lambda: messagebox.showerror("试听失败", f"无法播放试听声音：\n{message}"))
            self.clear_highlight()
        except Exception as e:
            print(f"更新试听状态时发生错误: {e}")
            import traceback
            traceback.print_exc()
    
    def on_reading_finished(self, success: bool, message: str):
        """朗读完成回调"""
        # 在主线程中更新UI，使用更安全的方式
        try:
            self.root.after(0, lambda s=success, m=message: self._update_reading_status(s, m))
        except Exception as e:
            print(f"安排回调函数错误: {e}")
            # 如果after失败，直接在主线程中调用（如果当前在主线程）
            try:
                self._update_reading_status(success, message)
            except Exception as e2:
                print(f"更新朗读状态错误: {e2}")
    
    def _update_reading_status(self, success: bool, message: str):
        """更新朗读状态（在主线程中调用）"""
        try:
            self.play_button.config(state='normal', text="开始朗读")
            self.test_button.config(state='normal', text="试听声音")
            self.stop_button.config(state='disabled')
            
            if success:
                self.status_label.config(text="朗读完成")
            else:
                self.status_label.config(text=f"朗读失败: {message}")
                # 如果失败，显示详细错误，使用after延迟显示
                if "未初始化" in message or "失败" in message:
                    self.root.after(100, lambda: messagebox.showerror("朗读失败", f"朗读时发生错误：\n{message}"))
            self.clear_highlight()
        except Exception as e:
            print(f"更新朗读状态时发生错误: {e}")
            import traceback
            traceback.print_exc()
    
    def _check_voice_availability(self):
        """检查语音可用性（保留用于兼容）"""
        # 现在使用下拉框，不需要这个方法了
        pass
    
    def setup_shortcuts(self):
        """设置快捷键"""
        self.root.bind('<Control-f>', lambda e: self.search_entry.focus())
        self.root.bind('<Control-Left>', lambda e: self.prev_chapter())
        self.root.bind('<Control-Right>', lambda e: self.next_chapter())
        self.root.bind('<Control-plus>', lambda e: self.increase_font())
        self.root.bind('<Control-minus>', lambda e: self.decrease_font())
        self.root.bind('<Control-b>', lambda e: self.add_bookmark())
        self.root.bind('<F3>', lambda e: self.search_next())
        self.root.bind('<Shift-F3>', lambda e: self.search_prev())
    
    def increase_font(self):
        """增大字体"""
        if self.font_size < 30:
            self.font_size += 1
            self.update_font()
    
    def decrease_font(self):
        """减小字体"""
        if self.font_size > 8:
            self.font_size -= 1
            self.update_font()
    
    def update_font(self):
        """更新字体"""
        # 保存当前滚动位置
        current_pos = self.content_text.index(tk.INSERT)
        self.content_text.config(font=(self.font_family, self.font_size))
        self.font_size_label.config(text=str(self.font_size))
        # 恢复滚动位置
        try:
            self.content_text.see(current_pos)
        except:
            self.content_text.see(1.0)
    
    def add_bookmark(self):
        """添加书签"""
        if not self.current_novel:
            messagebox.showwarning("警告", "请先选择一本小说")
            return
        
        novel_id = self.current_novel.get('id')
        chapter_index = self.current_chapter_index
        chapter_title = ""
        if self.current_chapters and chapter_index < len(self.current_chapters):
            chapter_title = self.current_chapters[chapter_index].get('title', '')
        
        # 获取当前光标位置
        try:
            cursor_pos = self.content_text.index(tk.INSERT)
            line, col = cursor_pos.split('.')
            position = int(line) - 1
        except:
            position = 0
        
        bookmark_index = self.manager.add_bookmark(
            novel_id, chapter_index, chapter_title, position
        )
        messagebox.showinfo("成功", f"已添加书签：{chapter_title}")
    
    def show_bookmarks(self):
        """显示书签窗口"""
        if not self.current_novel:
            messagebox.showwarning("警告", "请先选择一本小说")
            return
        
        novel_id = self.current_novel.get('id')
        bookmarks = self.manager.get_bookmarks(novel_id)
        
        if not bookmarks:
            messagebox.showinfo("提示", "当前小说没有书签")
            return
        
        # 创建书签窗口
        bookmark_window = tk.Toplevel(self.root)
        bookmark_window.title("书签列表")
        bookmark_window.geometry("500x400")
        
        # 书签列表
        list_frame = ttk.Frame(bookmark_window, padding="10")
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        bookmark_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, font=("微软雅黑", 10))
        bookmark_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=bookmark_listbox.yview)
        
        for i, bookmark in enumerate(bookmarks):
            chapter_title = bookmark.get('chapter_title', '未知章节')
            created_time = bookmark.get('created_time', '')
            if created_time:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(created_time)
                    time_str = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    time_str = created_time[:16] if len(created_time) > 16 else created_time
            else:
                time_str = ""
            display_text = f"{chapter_title} - {time_str}"
            bookmark_listbox.insert(tk.END, display_text)
        
        # 按钮
        button_frame = ttk.Frame(bookmark_window, padding="10")
        button_frame.pack(fill=tk.X)
        
        def jump_to_bookmark():
            selection = bookmark_listbox.curselection()
            if not selection:
                messagebox.showwarning("警告", "请选择要跳转的书签")
                return
            
            index = selection[0]
            bookmark = bookmarks[index]
            chapter_index = bookmark.get('chapter_index', 0)
            
            # 跳转到章节
            if chapter_index < len(self.current_chapters):
                self.current_chapter_index = chapter_index
                self.chapter_combo.current(chapter_index)
                self.load_chapter_content()
                self.update_display()
                bookmark_window.destroy()
        
        def delete_bookmark():
            selection = bookmark_listbox.curselection()
            if not selection:
                messagebox.showwarning("警告", "请选择要删除的书签")
                return
            
            if messagebox.askyesno("确认", "确定要删除选中的书签吗？"):
                index = selection[0]
                self.manager.delete_bookmark(novel_id, index)
                bookmark_listbox.delete(index)
                bookmarks.pop(index)
                if not bookmarks:
                    bookmark_window.destroy()
        
        ttk.Button(button_frame, text="跳转", command=jump_to_bookmark).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="删除", command=delete_bookmark).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="关闭", command=bookmark_window.destroy).pack(side=tk.RIGHT, padx=5)
        
        bookmark_listbox.bind('<Double-Button-1>', lambda e: jump_to_bookmark())
    
    def show_stats(self):
        """显示阅读统计"""
        if not self.current_novel:
            messagebox.showwarning("警告", "请先选择一本小说")
            return
        
        novel_id = self.current_novel.get('id')
        stats = self.manager.get_reading_stats(novel_id)
        
        # 创建统计窗口
        stats_window = tk.Toplevel(self.root)
        stats_window.title("阅读统计")
        stats_window.geometry("400x300")
        
        stats_frame = ttk.Frame(stats_window, padding="20")
        stats_frame.pack(fill=tk.BOTH, expand=True)
        
        total_time = stats.get('total_reading_time', 0.0)
        total_words = stats.get('total_words_read', 0)
        
        # 格式化时间
        hours = int(total_time // 3600)
        minutes = int((total_time % 3600) // 60)
        seconds = int(total_time % 60)
        time_str = f"{hours}小时{minutes}分钟{seconds}秒" if hours > 0 else f"{minutes}分钟{seconds}秒"
        
        # 显示统计信息
        ttk.Label(stats_frame, text="阅读统计", font=("微软雅黑", 14, "bold")).pack(pady=(0, 20))
        
        ttk.Label(stats_frame, text=f"总阅读时长: {time_str}", font=("微软雅黑", 11)).pack(pady=5, anchor=tk.W)
        ttk.Label(stats_frame, text=f"总阅读字数: {total_words:,} 字", font=("微软雅黑", 11)).pack(pady=5, anchor=tk.W)
        
        # 计算平均阅读速度
        if total_time > 0:
            words_per_minute = int(total_words / (total_time / 60))
            ttk.Label(stats_frame, text=f"平均阅读速度: {words_per_minute} 字/分钟", font=("微软雅黑", 11)).pack(pady=5, anchor=tk.W)
        
        last_update = stats.get('last_update_time')
        if last_update:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(last_update)
                update_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                update_str = last_update[:19] if len(last_update) > 19 else last_update
            ttk.Label(stats_frame, text=f"最后更新: {update_str}", font=("微软雅黑", 9), foreground="gray").pack(pady=10, anchor=tk.W)
        
        ttk.Button(stats_frame, text="关闭", command=stats_window.destroy).pack(pady=20)

    def start_download_monitor(self):
        """启动下载缓存监控"""
        if self.download_monitor_thread and self.download_monitor_thread.is_alive():
            return
        self.download_monitor_thread = threading.Thread(
            target=self._monitor_download_cache,
            daemon=True
        )
        self.download_monitor_thread.start()
        self.root.after(2000, self.process_download_queue)

    def _monitor_download_cache(self):
        """后台监控下载缓存目录"""
        observed_files = {}
        while not self.download_monitor_stop.is_set():
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
                    prev = observed_files.get(entry.path)
                    if prev and prev['signature'] == signature:
                        prev['stable_cycles'] += 1
                    else:
                        observed_files[entry.path] = {
                            'signature': signature,
                            'stable_cycles': 0
                        }
                        continue
                    if prev['stable_cycles'] >= 1:
                        if entry.path not in self.queued_downloads:
                            if not self.manager.is_download_processed(
                                entry.path, stat.st_size, stat.st_mtime
                            ):
                                self.download_queue.put(entry.path)
                                self.queued_downloads.add(entry.path)
                # 清理不存在的文件记录
                for tracked_path in list(observed_files.keys()):
                    if tracked_path not in current_paths:
                        observed_files.pop(tracked_path, None)
                        self.queued_downloads.discard(tracked_path)
                time.sleep(2)
            except Exception as exc:
                print(f"监控下载目录出错: {exc}")
                time.sleep(5)

    def process_download_queue(self):
        """处理监控线程发现的下载文件"""
        try:
            while True:
                file_path = self.download_queue.get_nowait()
                self.import_downloaded_file(file_path)
                self.queued_downloads.discard(file_path)
        except queue.Empty:
            pass
        finally:
            if not self.download_monitor_stop.is_set():
                self.root.after(2000, self.process_download_queue)

    def import_downloaded_file(self, file_path: str):
        """将缓存目录中的小说文件导入"""
        if not os.path.exists(file_path):
            return
        try:
            stat = os.stat(file_path)
            if self.manager.is_download_processed(file_path, stat.st_size, stat.st_mtime):
                return
            novel_info = self.fetcher.get_novel_info(file_path)
            if not novel_info:
                novel_info = {
                    'title': os.path.basename(file_path),
                    'author': '未知作者',
                    'description': '下载缓存小说',
                    'url': file_path,
                    'source': 'download_cache'
                }
            else:
                novel_info['source'] = 'download_cache'
                novel_info['url'] = file_path
            novel_id = self.manager.add_novel(novel_info)
            self.manager.mark_download_processed(file_path, stat.st_size, stat.st_mtime)
            self.refresh_novel_list()
            self.status_label.config(text=f"已导入下载小说：{novel_info['title']}")
            self.highlight_novel_in_list(novel_id)
        except Exception as exc:
            messagebox.showerror("错误", f"导入下载小说失败: {exc}")

    def highlight_novel_in_list(self, novel_id: str):
        """在列表中定位并选中新导入的小说"""
        novels = self.manager.get_all_novels()
        for idx, novel in enumerate(novels):
            if novel.get('id') == novel_id:
                self.novel_listbox.selection_clear(0, tk.END)
                self.novel_listbox.selection_set(idx)
                self.novel_listbox.see(idx)
                break

    def on_close(self):
        """程序关闭处理"""
        self.download_monitor_stop.set()
        if self.active_webview_process and self.active_webview_process.poll() is None:
            try:
                self.active_webview_process.terminate()
            except:
                pass
        self.stop_reading()
        self.root.destroy()
    
    def search_text(self):
        """搜索文本"""
        keyword = self.search_var.get().strip()
        if not keyword:
            messagebox.showwarning("警告", "请输入搜索关键词")
            return
        
        if not self.current_novel:
            messagebox.showwarning("警告", "请先选择一本小说")
            return
        
        # 获取当前章节内容
        content = self.content_text.get(1.0, tk.END)
        self.search_results = []
        
        # 搜索所有匹配项（不区分大小写）
        start = 1.0
        while True:
            pos = self.content_text.search(keyword, start, tk.END, nocase=True)
            if not pos:
                break
            end_pos = f"{pos}+{len(keyword)}c"
            self.search_results.append((pos, end_pos))
            start = end_pos
        
        if not self.search_results:
            messagebox.showinfo("提示", f"未找到关键词：{keyword}")
            self.current_search_index = -1
            return
        
        self.current_search_index = 0
        self.highlight_search_result()
        self.status_label.config(text=f"找到 {len(self.search_results)} 个匹配项")
    
    def on_search_key_release(self, event):
        """搜索框按键释放事件"""
        # 清除之前的搜索结果高亮
        self.content_text.tag_remove("search_highlight", 1.0, tk.END)
        self.search_results = []
        self.current_search_index = -1
    
    def search_next(self):
        """搜索下一个"""
        if not self.search_results:
            self.search_text()
            return
        
        if self.current_search_index < len(self.search_results) - 1:
            self.current_search_index += 1
        else:
            self.current_search_index = 0  # 循环到第一个
        
        self.highlight_search_result()
    
    def search_prev(self):
        """搜索上一个"""
        if not self.search_results:
            self.search_text()
            return
        
        if self.current_search_index > 0:
            self.current_search_index -= 1
        else:
            self.current_search_index = len(self.search_results) - 1  # 循环到最后一个
        
        self.highlight_search_result()
    
    def highlight_search_result(self):
        """高亮搜索结果"""
        if not self.search_results or self.current_search_index < 0:
            return
        
        # 清除之前的高亮
        self.content_text.tag_remove("search_highlight", 1.0, tk.END)
        
        # 高亮当前结果
        pos, end_pos = self.search_results[self.current_search_index]
        self.content_text.tag_add("search_highlight", pos, end_pos)
        self.content_text.see(pos)
        
        # 更新状态
        self.status_label.config(
            text=f"找到 {len(self.search_results)} 个匹配项，当前第 {self.current_search_index + 1} 个"
        )
    
    def update_reading_stats_periodically(self):
        """定期更新阅读统计"""
        if not self.current_novel:
            return
        
        if self.reading_start_time:
            current_time = time.time()
            elapsed = current_time - self.reading_start_time
            
            # 每30秒更新一次统计
            if not self.last_stats_update or (current_time - self.last_stats_update) >= 30:
                # 计算阅读的字数（简单估算：当前章节内容长度）
                content = self.content_text.get(1.0, tk.END)
                words_count = len(content.replace(' ', '').replace('\n', ''))
                
                self.manager.update_reading_stats(
                    self.current_novel.get('id'),
                    reading_time=elapsed,
                    words_read=words_count
                )
                
                # 更新统计显示
                stats = self.manager.get_reading_stats(self.current_novel.get('id'))
                total_time = stats.get('total_reading_time', 0.0)
                hours = int(total_time // 3600)
                minutes = int((total_time % 3600) // 60)
                if hours > 0:
                    self.stats_label.config(text=f"阅读时长: {hours}小时{minutes}分钟")
                else:
                    self.stats_label.config(text=f"阅读时长: {minutes}分钟")
                
                self.last_stats_update = current_time
                self.reading_start_time = current_time  # 重置开始时间
        
        # 30秒后再次调用
        self.root.after(30000, self.update_reading_stats_periodically)


def exception_handler(exc_type, exc_value, exc_traceback):
    """全局异常处理函数"""
    if issubclass(exc_type, KeyboardInterrupt):
        # 允许Ctrl+C正常退出
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    # 特别处理SystemExit，防止TTS导致的意外退出
    if issubclass(exc_type, SystemExit):
        print(f"警告: 捕获到SystemExit异常: {exc_value}")
        print("这可能是由TTS引擎引起的，已阻止程序退出")
        import traceback
        error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        print(f"SystemExit详情: {error_msg}")
        # 不调用sys.__excepthook__，防止程序退出
        return
    
    import traceback
    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    print(f"未捕获的异常: {error_msg}")
    
    # 尝试显示错误对话框（如果tkinter可用）
    try:
        import tkinter.messagebox as msgbox
        msgbox.showerror("程序错误", f"程序发生未预期的错误：\n{exc_type.__name__}: {exc_value}\n\n详细信息请查看控制台输出。")
    except:
        pass


def main():
    """主函数"""
    # 设置全局异常处理
    sys.excepthook = exception_handler
    
    # 设置线程异常处理
    import threading
    threading.excepthook = lambda args: exception_handler(args.exc_type, args.exc_value, args.exc_traceback)
    
    try:
        root = tk.Tk()
        app = NovelReaderApp(root)
        root.mainloop()
    except Exception as e:
        import traceback
        error_msg = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        print(f"主程序异常: {error_msg}")
        try:
            messagebox.showerror("程序错误", f"程序启动失败：\n{str(e)}")
        except:
            pass


if __name__ == "__main__":
    main()


