@echo off
chcp 65001 >nul
echo 正在安装Python依赖包...
echo.

REM 尝试使用py命令（Windows Python Launcher）
py -m pip install requests beautifulsoup4 lxml pyttsx3 2>nul
if %errorlevel% equ 0 (
    echo 安装成功！
    goto :end
)

REM 尝试使用python命令
python -m pip install requests beautifulsoup4 lxml pyttsx3 2>nul
if %errorlevel% equ 0 (
    echo 安装成功！
    goto :end
)

REM 尝试使用python3命令
python3 -m pip install requests beautifulsoup4 lxml pyttsx3 2>nul
if %errorlevel% equ 0 (
    echo 安装成功！
    goto :end
)

echo.
echo 无法找到Python或pip命令！
echo 请确保已安装Python，并且已添加到系统PATH环境变量中。
echo.
echo 如果已安装Python，可以手动运行以下命令：
echo   py -m pip install requests beautifulsoup4 lxml pyttsx3
echo   或
echo   python -m pip install requests beautifulsoup4 lxml pyttsx3
echo.
echo 注意：即使不安装这些依赖，程序也可以使用本地文件阅读功能。
echo 只有在线获取小说功能需要这些依赖。

:end
pause


