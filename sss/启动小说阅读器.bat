@echo off
chcp 65001 >nul
echo 正在启动小说阅读器...
py -3.10 novel_reader_qt.py
if errorlevel 1 (
    echo.
    echo 启动失败！请确保已安装Python并安装了所需依赖。
    echo 建议运行: pip install -r requirements.txt
    pause
)



