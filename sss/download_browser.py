import argparse
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
import os
import json


CONFIG_FILE = os.path.join(os.path.dirname(__file__), "download_sites.json")


def parse_args():
    parser = argparse.ArgumentParser(description="下载小说辅助窗口")
    parser.add_argument("--url", default="https://www.biquge66.net/", help="默认打开的网址")
    parser.add_argument("--download-dir", default="", help="提示用户的下载目录")
    return parser.parse_args()


class DownloadBrowserHelper:
    def __init__(self, default_url: str, download_dir: str):
        self.default_url = default_url
        self.download_dir = download_dir
        self.root = tk.Tk()
        self.root.title("下载小说")
        # 加宽窗口，避免底部三个按钮文字被截断
        self.root.geometry("760x420")
        self.root.resizable(False, False)

        # 预置常用网站
        self.default_sites = [
            {"name": "起点小说", "url": "https://www.qidian.com/"},
            {"name": "鸠摩小说", "url": "https://www.jiumosoushu.cc/"},
            {"name": "书旗小说", "url": "https://ognv.shuqi.com/"},
            {"name": "微信读书", "url": "https://weread.qq.com/"},
            {"name": "QQ阅读小说", "url": "https://book.qq.com/"},
        ]
        # 自定义网站（可持久化）
        self.custom_sites = []
        self.load_custom_sites()

        self.create_widgets()

    # ---------- UI ----------
    def create_widgets(self):
        container = ttk.Frame(self.root, padding=15)
        container.pack(fill=tk.BOTH, expand=True)

        info_text = (
            "1. 输入或粘贴小说网站地址，点击“打开网站”将在默认浏览器中打开。\n"
            "2. 下载 TXT 文件后，请保存到程序提示的下载缓存目录：\n"
            f"{self.download_dir}\n"
            "3. 文件保存完成后，主程序会自动导入该小说。"
        )
        info_label = ttk.Label(container, text=info_text, justify=tk.LEFT, wraplength=730)
        info_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        # 地址输入
        entry_frame = ttk.Frame(container)
        entry_frame.grid(row=1, column=0, columnspan=2, sticky="we", pady=(0, 8))
        entry_frame.columnconfigure(1, weight=1)

        ttk.Label(entry_frame, text="网址：").grid(row=0, column=0, sticky="w")
        self.url_var = tk.StringVar(value=self.default_url)
        url_entry = ttk.Entry(entry_frame, textvariable=self.url_var)
        url_entry.grid(row=0, column=1, padx=(5, 5), sticky="we")
        url_entry.focus()
        ttk.Button(entry_frame, text="打开网站", command=self.open_url, width=10).grid(row=0, column=2, sticky="e")

        # 固定常用网站按钮
        quick_frame = ttk.LabelFrame(container, text="常用网站（点击按钮即可在浏览器中打开）")
        quick_frame.grid(row=2, column=0, columnspan=2, sticky="we", pady=(5, 5))

        for idx, site in enumerate(self.default_sites):
            ttk.Button(
                quick_frame,
                text=site["name"],
                width=14,
                command=lambda u=site["url"]: self.open_quick_site(u),
            ).grid(row=0, column=idx, padx=3, pady=5)

        # 自定义网站区域
        custom_frame = ttk.LabelFrame(container, text="自定义常用网站")
        custom_frame.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(5, 5))
        container.rowconfigure(3, weight=1)
        custom_frame.columnconfigure(0, weight=1)

        # 列表
        list_frame = ttk.Frame(custom_frame)
        list_frame.grid(row=0, column=0, columnspan=3, sticky="nsew", pady=(5, 2))
        custom_frame.rowconfigure(0, weight=1)

        self.site_listbox = tk.Listbox(list_frame, height=5)
        self.site_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.site_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.site_listbox.config(yscrollcommand=scrollbar.set)

        # 填充已有自定义站点
        self.refresh_custom_listbox()

        # 添加/删除表单
        form_frame = ttk.Frame(custom_frame)
        form_frame.grid(row=1, column=0, columnspan=3, sticky="we", pady=(5, 2))
        form_frame.columnconfigure(1, weight=1)
        form_frame.columnconfigure(3, weight=1)

        ttk.Label(form_frame, text="名称：").grid(row=0, column=0, sticky="w")
        self.custom_name_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.custom_name_var).grid(row=0, column=1, sticky="we", padx=(0, 8))

        ttk.Label(form_frame, text="网址：").grid(row=0, column=2, sticky="w")
        self.custom_url_var = tk.StringVar()
        ttk.Entry(form_frame, textvariable=self.custom_url_var).grid(row=0, column=3, sticky="we")

        button_frame = ttk.Frame(custom_frame)
        button_frame.grid(row=2, column=0, columnspan=3, sticky="e", pady=(5, 5))

        ttk.Button(button_frame, text="添加到常用", command=self.add_custom_site).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="打开选中", command=self.open_selected_custom).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="删除选中", command=self.delete_selected_custom).pack(side=tk.LEFT, padx=5)

        # 底部：打开缓存目录
        ttk.Button(
            container,
            text="打开下载缓存目录",
            command=self.open_download_folder,
        ).grid(row=4, column=0, columnspan=2, sticky="we", pady=(5, 0))

    # ---------- 常用站点持久化 ----------
    def load_custom_sites(self):
        if not os.path.exists(CONFIG_FILE):
            self.custom_sites = []
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.custom_sites = data.get("custom_sites", [])
        except Exception:
            self.custom_sites = []

    def save_custom_sites(self):
        data = {"custom_sites": self.custom_sites}
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def refresh_custom_listbox(self):
        self.site_listbox.delete(0, tk.END)
        for site in self.custom_sites:
            name = site.get("name", "")
            url = site.get("url", "")
            self.site_listbox.insert(tk.END, f"{name} - {url}")

    # ---------- 业务逻辑 ----------
    def format_url(self, url: str) -> str:
        url = url.strip()
        if not url:
            raise ValueError("请输入要访问的网址")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        return url

    def open_url(self):
        try:
            url = self.format_url(self.url_var.get())
            webbrowser.open(url)
        except ValueError as exc:
            messagebox.showwarning("提示", str(exc))
        except Exception as exc:
            messagebox.showerror("错误", f"无法打开浏览器：{exc}")

    def open_quick_site(self, url: str):
        self.url_var.set(url)
        self.open_url()

    def open_download_folder(self):
        if not self.download_dir:
            messagebox.showinfo("提示", "主程序尚未提供下载缓存目录。")
            return
        try:
            if not os.path.exists(self.download_dir):
                os.makedirs(self.download_dir, exist_ok=True)
            os.startfile(self.download_dir)
        except Exception as exc:
            messagebox.showerror("错误", f"无法打开目录：{exc}")

    def add_custom_site(self):
        name = self.custom_name_var.get().strip()
        url = self.custom_url_var.get().strip()
        if not name or not url:
            messagebox.showwarning("提示", "请填写名称和网址。")
            return
        try:
            url = self.format_url(url)
        except ValueError as exc:
            messagebox.showwarning("提示", str(exc))
            return

        self.custom_sites.append({"name": name, "url": url})
        self.save_custom_sites()
        self.refresh_custom_listbox()
        self.custom_name_var.set("")
        self.custom_url_var.set("")

    def _get_selected_custom_index(self):
        selection = self.site_listbox.curselection()
        if not selection:
            return None
        return selection[0]

    def open_selected_custom(self):
        idx = self._get_selected_custom_index()
        if idx is None:
            messagebox.showwarning("提示", "请先选择一个自定义网站。")
            return
        site = self.custom_sites[idx]
        self.url_var.set(site.get("url", ""))
        self.open_url()

    def delete_selected_custom(self):
        idx = self._get_selected_custom_index()
        if idx is None:
            messagebox.showwarning("提示", "请先选择要删除的网站。")
            return
        if not messagebox.askyesno("确认", "确定要删除选中的常用网站吗？"):
            return
        self.custom_sites.pop(idx)
        self.save_custom_sites()
        self.refresh_custom_listbox()

    def run(self):
        self.root.mainloop()


def main():
    args = parse_args()
    helper = DownloadBrowserHelper(args.url, args.download_dir)
    helper.run()


if __name__ == "__main__":
    main()

