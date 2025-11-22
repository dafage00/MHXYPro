# -*- coding: utf-8 -*-
"""
文本转语音管理器
支持男声和女声朗读
"""

import threading
import queue
import time
import subprocess
import sys
import tempfile
import os
from decimal import Decimal

# 尝试导入TTS库
try:
    import pyttsx3
    HAS_TTS = True
except ImportError:
    HAS_TTS = False
    pyttsx3 = None

# 尝试导入pythoncom用于COM初始化
try:
    import pythoncom
    HAS_PYTHONCOM = True
except ImportError:
    HAS_PYTHONCOM = False


class TTSManager:
    """文本转语音管理器"""
    
    def __init__(self):
        self.engine = None
        self.is_speaking = False
        self.is_paused = False
        self.stop_flag = False
        self.ps_process = None
        self.ps_lock = threading.Lock()
        self.voice_type = "female"  # "male" 或 "female"（兼容旧代码）
        self.selected_voice_name = None  # 当前选择的语音名称
        self.rate = 150  # 语速
        self.volume = 1.0  # 音量
        self.init_error = None
        self.word_callback = None
        self.current_mapping = []
        self.current_text = ""
        self.available_voice_names = []  # 所有可用语音名称列表
        
        if HAS_TTS:
            try:
                # 尝试使用Windows SAPI5驱动
                try:
                    self.engine = pyttsx3.init('sapi5')
                except:
                    # 如果失败，尝试默认驱动
                    self.engine = pyttsx3.init()
                
                # 设置初始参数
                self.engine.setProperty('rate', self.rate)
                self.engine.setProperty('volume', self.volume)
                
                # 注册语音事件
                try:
                    self.engine.connect('started-word', self._on_word)
                except Exception as event_error:
                    print(f"警告: 无法注册started-word事件: {event_error}")
                
                self._setup_voices()
                
                # 设置默认语音
                self.set_voice_type(self.voice_type)
            except Exception as e:
                self.init_error = str(e)
                print(f"TTS初始化失败: {e}")
                self.engine = None
        
        # 获取PowerShell可用语音列表
        self._load_powershell_voices()
    
    def _setup_voices(self):
        """设置可用语音"""
        if not self.engine:
            return
        
        try:
            voices = self.engine.getProperty('voices')
            self.available_voices = voices if voices else []
            
            # 尝试设置默认语音
            if self.available_voices:
                self.male_voice_id = None
                self.female_voice_id = None
                
                # Windows SAPI5 常见语音名称
                # 英文：David (男), Zira (女)
                # 中文：通常包含"Microsoft"和语音名称
                
                for voice in self.available_voices:
                    voice_name = voice.name.lower()
                    voice_id = voice.id
                    
                    # 识别女声 - 优先匹配
                    if not self.female_voice_id:
                        # 英文女声关键词
                        if any(keyword in voice_name for keyword in ['zira', 'female', 'woman', 'huihui', 'hanhan', 'xiaoxiao', 'yaoyao']):
                            self.female_voice_id = voice_id
                            print(f"识别到女声: {voice.name}")
                    
                    # 识别男声
                    if not self.male_voice_id:
                        # 英文男声关键词
                        if any(keyword in voice_name for keyword in ['david', 'mark', 'male', 'man']):
                            self.male_voice_id = voice_id
                            print(f"识别到男声: {voice.name}")
                
                # 如果通过关键词没找到，使用位置判断
                # Windows通常：第一个是男声(David)，第二个是女声(Zira)
                if not self.male_voice_id and len(self.available_voices) >= 1:
                    self.male_voice_id = self.available_voices[0].id
                    print(f"使用第一个语音作为男声: {self.available_voices[0].name}")
                
                if not self.female_voice_id:
                    if len(self.available_voices) >= 2:
                        self.female_voice_id = self.available_voices[1].id
                        print(f"使用第二个语音作为女声: {self.available_voices[1].name}")
                    elif len(self.available_voices) >= 1:
                        # 如果只有一个语音，也设置为女声备选
                        self.female_voice_id = self.available_voices[0].id
                        print(f"只有一个语音，设置为女声: {self.available_voices[0].name}")
                
                # 打印所有可用语音用于调试
                print(f"可用语音列表:")
                for i, voice in enumerate(self.available_voices):
                    print(f"  {i+1}. {voice.name} (ID: {voice.id})")
                print(f"选择的男声ID: {self.male_voice_id}")
                print(f"选择的女声ID: {self.female_voice_id}")
                
                # 检查是否只有一个语音
                if len(self.available_voices) == 1:
                    print("警告: 系统只有一个语音，男声和女声将使用同一个语音")
                    # 如果只有一个语音，确保男声和女声都指向它
                    if not self.male_voice_id:
                        self.male_voice_id = self.available_voices[0].id
                    if not self.female_voice_id:
                        self.female_voice_id = self.available_voices[0].id
        except Exception as e:
            print(f"设置语音失败: {e}")
            import traceback
            traceback.print_exc()
            self.available_voices = []
    
    def set_voice_type(self, voice_type: str):
        """设置语音类型：'male' 或 'female'"""
        if not self.engine:
            print("TTS引擎未初始化，无法设置语音类型")
            return False
        
        self.voice_type = voice_type
        
        try:
            voice_id = None
            voice_name = None
            
            if voice_type == "male":
                if hasattr(self, 'male_voice_id') and self.male_voice_id:
                    voice_id = self.male_voice_id
                    # 检查是否和女声是同一个（系统只有一个语音）
                    if hasattr(self, 'female_voice_id') and self.male_voice_id == self.female_voice_id:
                        print("警告: 系统只有一个语音，男声将使用女声语音")
                    print(f"设置男声: {voice_id}")
                else:
                    print("警告: 未找到男声，尝试使用第一个语音")
                    if self.available_voices:
                        voice_id = self.available_voices[0].id
                        voice_name = self.available_voices[0].name
            elif voice_type == "female":
                if hasattr(self, 'female_voice_id') and self.female_voice_id:
                    voice_id = self.female_voice_id
                    print(f"设置女声: {voice_id}")
                else:
                    print("警告: 未找到女声，尝试使用可用语音")
                    if len(self.available_voices) > 1:
                        voice_id = self.available_voices[1].id
                        voice_name = self.available_voices[1].name
                    elif self.available_voices:
                        voice_id = self.available_voices[0].id
                        voice_name = self.available_voices[0].name
            
            if voice_id:
                # 停止当前朗读（如果正在朗读）
                if self.is_speaking:
                    try:
                        self.engine.stop()
                        # 等待停止完成
                        time.sleep(0.1)
                    except:
                        pass
                
                # 设置语音 - 添加超时保护，避免卡住
                try:
                    self.engine.setProperty('voice', voice_id)
                    print(f"语音属性已设置: {voice_id}")
                except Exception as set_error:
                    print(f"设置语音属性错误: {set_error}")
                    raise
                
                # 验证设置 - 使用超时保护，避免getProperty卡住
                try:
                    # 不验证，因为getProperty可能卡住
                    # current_voice = self.engine.getProperty('voice')
                    # print(f"当前语音已设置为: {current_voice}")
                    print(f"当前语音已设置为: {voice_id}")
                except Exception as get_error:
                    print(f"获取语音属性错误（忽略）: {get_error}")
                    # 即使获取失败，也认为设置成功
                
                # 如果只有一个语音且选择男声，给出提示
                if voice_type == "male" and len(self.available_voices) == 1:
                    print("提示: 系统只有一个语音（可能是女声），男声功能可能无法正常工作")
                    print("建议: 请在Windows设置中安装男声语音包")
                
                return True
            else:
                print("错误: 无法找到合适的语音")
                return False
        except Exception as e:
            print(f"设置语音类型失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def set_rate(self, rate: int):
        """设置语速（50-300，默认150）"""
        if self.engine:
            try:
                self.rate = max(50, min(300, rate))
                self.engine.setProperty('rate', self.rate)
                # 验证设置
                current_rate = self.engine.getProperty('rate')
                print(f"语速已设置为: {self.rate} (当前引擎值: {current_rate})")
            except Exception as e:
                print(f"设置语速失败: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("TTS引擎未初始化，无法设置语速")
    
    def set_volume(self, volume: float):
        """设置音量（0.0-1.0）"""
        if self.engine:
            try:
                self.volume = max(0.0, min(1.0, volume))
                self.engine.setProperty('volume', self.volume)
            except Exception as e:
                print(f"设置音量失败: {e}")
    
    def set_word_callback(self, callback):
        """注册单词开始回调"""
        self.word_callback = callback
    
    def _map_to_original(self, index: int):
        if isinstance(index, Decimal):
            index = int(index)
        if not self.current_mapping:
            return None
        if index < 0:
            return None
        if index >= len(self.current_mapping):
            return self.current_mapping[-1] + 1
        return self.current_mapping[index]
    
    def _on_word(self, name, location, length):
        """pyttsx3 started-word 事件回调"""
        try:
            if not self.word_callback or not self.current_mapping:
                return
            if isinstance(location, Decimal):
                location = int(location)
            if isinstance(length, Decimal):
                length = int(length)
            if length <= 0:
                return
            start = self._map_to_original(location)
            end = self._map_to_original(location + length - 1)
            if start is None:
                return
            if end is None:
                end = start
            end += 1  # 转换为区间右边界
            self.word_callback(start, end)
        except Exception as e:
            print(f"处理started-word事件失败: {e}")
    
    def _load_powershell_voices(self):
        """加载PowerShell可用的所有语音"""
        if sys.platform != "win32":
            self.available_voice_names = []
            return
        
        try:
            ps_script = '''
Add-Type -AssemblyName System.Speech
$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voices = $speak.GetInstalledVoices()
foreach ($voice in $voices) {
    Write-Output $voice.VoiceInfo.Name
}
'''
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                timeout=5,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8'
            )
            
            if result.returncode == 0 and result.stdout:
                voices = [v.strip() for v in result.stdout.strip().split('\n') if v.strip()]
                self.available_voice_names = voices
                print(f"找到 {len(voices)} 个可用语音:")
                for i, voice in enumerate(voices, 1):
                    print(f"  {i}. {voice}")
            else:
                print("无法获取语音列表，使用默认语音")
                self.available_voice_names = []
        except Exception as e:
            print(f"加载语音列表失败: {e}")
            self.available_voice_names = []
    
    def get_available_voice_names(self):
        """获取所有可用的语音名称列表"""
        if not self.available_voice_names:
            self._load_powershell_voices()
        return self.available_voice_names.copy()
    
    def set_voice_by_name(self, voice_name: str):
        """通过语音名称设置语音"""
        if voice_name and voice_name in self.available_voice_names:
            self.selected_voice_name = voice_name
            print(f"已选择语音: {voice_name}")
            return True
        elif voice_name:
            print(f"警告: 语音 '{voice_name}' 不在可用列表中")
            # 仍然尝试设置，可能系统有新的语音
            self.selected_voice_name = voice_name
            return True
        else:
            self.selected_voice_name = None
            return False
    
    def _speak_with_powershell(self, text: str):
        """使用Windows PowerShell的TTS（主要方案，更稳定）"""
        if self.stop_flag:
            print("播放已被请求停止，跳过PowerShell TTS调用")
            return False

        text_file_path = None
        script_file_path = None
        try:
            # 优先使用直接选择的语音名称
            voice_name = self.selected_voice_name
            
            # 如果没有直接选择，则根据voice_type推断
            if not voice_name and hasattr(self, 'voice_type'):
                if self.voice_type == "male" and hasattr(self, 'male_voice_id') and self.male_voice_id:
                    # 从voice_id提取语音名称
                    voice_id_str = str(self.male_voice_id)
                    if "ZH-CN" in voice_id_str:
                        voice_name = "Microsoft Huihui Desktop - Chinese (Simplified)"
                    elif "EN-US" in voice_id_str:
                        voice_name = "Microsoft David Desktop - English (United States)"
                elif self.voice_type == "female" and hasattr(self, 'female_voice_id') and self.female_voice_id:
                    voice_id_str = str(self.female_voice_id)
                    if "ZH-CN" in voice_id_str:
                        voice_name = "Microsoft Huihui Desktop - Chinese (Simplified)"
                    elif "EN-US" in voice_id_str:
                        voice_name = "Microsoft Zira Desktop - English (United States)"
            
            # 设置语速和音量
            rate = getattr(self, 'rate', 150)
            volume = getattr(self, 'volume', 1.0)
            # pyttsx3的rate范围是50-300，PowerShell的Rate范围是-10到10
            # 转换公式：powershell_rate = (pyttsx3_rate - 150) / 10
            ps_rate = (rate - 150) / 10.0
            ps_rate = max(-10, min(10, ps_rate))  # 限制范围
            
            # 将朗读文本写入临时文件，避免命令长度限制
            with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode='w', encoding='utf-8') as text_file:
                text_file.write(text)
                text_file_path = text_file.name
            
            # PowerShell脚本，通过参数传递路径和设置
            ps_script = '''
param(
    [string]$TextPath,
    [string]$VoiceName,
    [double]$RateValue,
    [int]$VolumeValue
)
Add-Type -AssemblyName System.Speech
$speak = New-Object System.Speech.Synthesis.SpeechSynthesizer
if ($VoiceName -and $VoiceName.Trim().Length -gt 0) {
    try {
        $speak.SelectVoice($VoiceName)
    } catch {
        Write-Host "无法设置语音 $VoiceName"
    }
}
$speak.Rate = [int]$RateValue
$speak.Volume = [int]$VolumeValue
$text = Get-Content -Path $TextPath -Encoding UTF8 | Out-String
$speak.Speak($text)
'''
            with tempfile.NamedTemporaryFile(delete=False, suffix=".ps1", mode='w', encoding='utf-8') as script_file:
                script_file.write(ps_script)
                script_file_path = script_file.name
            
            print(f"执行PowerShell TTS，语速={rate}，音量={volume}")
            process = subprocess.Popen(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    script_file_path,
                    "-TextPath",
                    text_file_path,
                    "-VoiceName",
                    voice_name if voice_name else "",
                    "-RateValue",
                    str(ps_rate),
                    "-VolumeValue",
                    str(int(volume * 100))
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            with self.ps_lock:
                self.ps_process = process
            
            stderr_data = b""
            while True:
                try:
                    _, err = process.communicate(timeout=0.5)
                    stderr_data += err or b""
                    break
                except subprocess.TimeoutExpired:
                    if self.stop_flag:
                        print("检测到停止请求，终止PowerShell TTS进程")
                        self._terminate_ps_process(process)
                        return False
            
            return_code = process.returncode
            if return_code == 0:
                return True
            else:
                print(f"PowerShell TTS返回错误码: {return_code}")
                if stderr_data:
                    try:
                        print(f"PowerShell错误: {stderr_data.decode('utf-8', errors='ignore')}")
                    except Exception:
                        pass
                return False
                
        except subprocess.TimeoutExpired:
            print("PowerShell TTS超时")
            self._terminate_ps_process()
            return False
        except Exception as e:
            print(f"PowerShell TTS失败: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            if text_file_path and os.path.exists(text_file_path):
                try:
                    os.remove(text_file_path)
                except Exception:
                    pass
            if script_file_path and os.path.exists(script_file_path):
                try:
                    os.remove(script_file_path)
                except Exception:
                    pass
    
    def speak(self, text: str, callback=None):
        """朗读文本（异步）"""
        if not self.engine:
            error_msg = "TTS引擎未初始化"
            if self.init_error:
                error_msg += f": {self.init_error}"
            # 尝试使用PowerShell备选方案
            if sys.platform == "win32":
                print("TTS引擎不可用，尝试使用PowerShell TTS...")
                def ps_thread():
                    try:
                        success = self._speak_with_powershell(text)
                        if callback:
                            callback(success, "PowerShell TTS完成" if success else "PowerShell TTS失败")
                    except Exception as e:
                        if callback:
                            callback(False, f"PowerShell TTS错误: {e}")
                threading.Thread(target=ps_thread, daemon=True).start()
                return
            else:
                if callback:
                    callback(False, error_msg)
                return
        
        if not text:
            if callback:
                callback(False, "文本为空")
            return
        
        # 停止当前朗读
        self.stop()
        
        # 在新线程中执行
        def speak_thread():
            com_initialized = False
            try:
                # 检查engine是否仍然有效
                if not self.engine:
                    raise Exception("TTS引擎未初始化或已失效")
                
                # COM初始化 - 使用线程安全的模式
                if HAS_PYTHONCOM:
                    try:
                        # 尝试使用线程安全的COM初始化
                        try:
                            pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
                        except AttributeError:
                            # 如果COINIT_APARTMENTTHREADED不可用，使用默认初始化
                            pythoncom.CoInitialize()
                        com_initialized = True
                        print("COM初始化成功")
                    except Exception as com_error:
                        print(f"COM初始化警告: {com_error}")
                        # 继续执行，某些情况下可能不需要COM初始化
                        # 但记录错误以便调试
                        import traceback
                        traceback.print_exc()
                
                self.is_speaking = True
                self.is_paused = False
                self.stop_flag = False
                
                # 清理文本（移除特殊字符）
                print(f"开始清理文本，原始文本长度: {len(text)}")
                clean_text, mapping = self._clean_text(text)
                self.current_mapping = mapping
                self.current_text = text
                print(f"清理后文本长度: {len(clean_text) if clean_text else 0}")
                
                if not clean_text or len(clean_text.strip()) < 1:
                    self.is_speaking = False
                    error_msg = "清理后的文本为空，无法朗读。文本可能只包含特殊字符。"
                    print(error_msg)
                    if callback:
                        try:
                            callback(False, error_msg)
                        except Exception as cb_error:
                            print(f"回调函数执行错误: {cb_error}")
                    return
                
                # 显示清理后的文本前100个字符用于调试
                preview = clean_text[:100] if len(clean_text) > 100 else clean_text
                print(f"清理后文本预览: {preview}...")
                
                # 再次检查engine（可能在清理文本时被其他线程修改）
                if not self.engine:
                    raise Exception("TTS引擎在执行过程中失效")
                
                # 确保设置当前参数
                try:
                    self.engine.setProperty('rate', self.rate)
                    self.engine.setProperty('volume', self.volume)
                except Exception as prop_error:
                    print(f"设置TTS属性错误: {prop_error}")
                    # 继续执行，可能某些属性设置失败但不影响朗读
                
                # 朗读文本 - 使用更安全的方式
                try:
                    # 确保引擎状态正常
                    if not self.engine:
                        raise Exception("TTS引擎在执行过程中失效")
                    
                    # 先停止任何正在进行的朗读
                    try:
                        self.engine.stop()
                    except:
                        pass
                    
                    # 重新设置属性（确保设置生效）
                    try:
                        self.engine.setProperty('rate', self.rate)
                        self.engine.setProperty('volume', self.volume)
                    except Exception as prop_error2:
                        print(f"重新设置TTS属性错误: {prop_error2}")
                    
                    # 完全避免使用runAndWait()，直接使用PowerShell TTS（更稳定）
                    print("检测到pyttsx3引擎，但为避免崩溃，使用PowerShell TTS...")
                    
                    # 直接使用PowerShell TTS，更稳定可靠
                    if sys.platform == "win32":
                        print("使用PowerShell TTS播放...")
                        success = self._speak_with_powershell(clean_text)
                        if success:
                            print("PowerShell TTS播放完成")
                        elif self.stop_flag:
                            print("PowerShell TTS被手动停止")
                            self.is_speaking = False
                            return
                        else:
                            raise Exception("PowerShell TTS播放失败")
                    else:
                        raise Exception("非Windows系统，无法使用TTS")
                        
                except SystemExit as sys_exit:
                    # 捕获SystemExit，防止程序退出
                    print(f"警告: TTS执行触发了SystemExit: {sys_exit}")
                    raise Exception("TTS执行被系统中断")
                except Exception as speak_error:
                    # 如果runAndWait失败，尝试停止引擎
                    print(f"朗读过程出错: {speak_error}")
                    import traceback
                    traceback.print_exc()
                    try:
                        self.engine.stop()
                    except:
                        pass
                    raise speak_error
                
                if not self.stop_flag:
                    self.is_speaking = False
                    if callback:
                        try:
                            callback(True, "朗读完成")
                        except Exception as cb_error:
                            print(f"回调函数执行错误: {cb_error}")
            except Exception as e:
                self.is_speaking = False
                error_msg = str(e)
                import traceback
                print(f"TTS朗读异常: {error_msg}")
                print(f"异常堆栈: {traceback.format_exc()}")
                if callback:
                    try:
                        callback(False, f"朗读失败: {error_msg}")
                    except Exception as cb_error:
                        print(f"回调函数执行错误: {cb_error}")
            finally:
                if HAS_PYTHONCOM and com_initialized:
                    try:
                        pythoncom.CoUninitialize()
                    except Exception as uninit_error:
                        print(f"COM清理错误: {uninit_error}")
        
        # 包装speak_thread以捕获所有异常，包括SystemExit
        def safe_speak_thread():
            try:
                speak_thread()
            except SystemExit as sys_exit:
                # 捕获SystemExit，防止程序退出
                print(f"警告: TTS线程触发了SystemExit: {sys_exit}")
                import traceback
                error_msg = "".join(traceback.format_exception(type(sys_exit), sys_exit, sys_exit.__traceback__))
                print(f"TTS线程SystemExit详情: {error_msg}")
                self.is_speaking = False
                if callback:
                    try:
                        callback(False, f"TTS执行被系统中断")
                    except:
                        pass
            except Exception as thread_error:
                import traceback
                error_msg = "".join(traceback.format_exception(type(thread_error), thread_error, thread_error.__traceback__))
                print(f"TTS线程未捕获的异常: {error_msg}")
                self.is_speaking = False
                if callback:
                    try:
                        callback(False, f"线程异常: {str(thread_error)}")
                    except:
                        pass
        
        thread = threading.Thread(target=safe_speak_thread, daemon=True)
        thread.start()
    
    def test_voice(self, callback=None):
        """试听当前语音设置"""
        test_text = "这是语音测试，如果您听到这段声音，说明语音朗读功能正常工作。"
        self.speak(test_text, callback=callback)
    
    def _clean_text(self, text: str):
        """清理文本，移除不适合朗读的字符，同时返回索引映射"""
        if not text:
            return "", []
        
        import re
        original_length = len(text)
        cleaned_chars = []
        mapping = []
        i = 0
        last_appended_space = False
        while i < original_length:
            ch = text[i]
            if ch == '#':
                j = i + 1
                while j < original_length and re.match(r'[A-Za-z0-9]', text[j]):
                    j += 1
                i = j
                continue
            if ch in ('~', '='):
                # 将连续的特殊符号视为停顿，替换为单个空格
                if not last_appended_space:
                    cleaned_chars.append(' ')
                    mapping.append(i)
                    last_appended_space = True
                while i + 1 < original_length and text[i + 1] == ch:
                    i += 1
                i += 1
                continue
            cleaned_chars.append(ch)
            mapping.append(i)
            last_appended_space = ch.isspace()
            i += 1
        cleaned = ''.join(cleaned_chars)
        # 简单去除多余空格，但保持映射长度一致
        # 通过再次遍历来删除多余空格
        result_chars = []
        result_mapping = []
        for idx, ch in enumerate(cleaned):
            mapped_index = mapping[idx]
            if ch == ' ':
                if result_chars and result_chars[-1] == ' ':
                    continue
            result_chars.append(ch)
            result_mapping.append(mapped_index)
        cleaned = ''.join(result_chars)
        mapping = result_mapping
        cleaned = cleaned.strip()
        # 同步裁剪映射
        if cleaned:
            start_strip = 0
            while start_strip < len(result_chars) and result_chars[start_strip].isspace():
                start_strip += 1
            end_strip = len(result_chars) - 1
            while end_strip >= 0 and result_chars[end_strip].isspace():
                end_strip -= 1
            mapping = mapping[start_strip:end_strip + 1] if end_strip >= start_strip else []
            cleaned = ''.join(result_chars[start_strip:end_strip + 1])
        if not cleaned:
            print("警告: 文本清理后为空，回退到原始文本")
            cleaned = text
            mapping = list(range(len(text)))
        print(f"文本清理: 原始长度={original_length}, 清理后长度={len(cleaned)}")
        return cleaned, mapping
    
    def stop(self):
        """停止朗读"""
        self.stop_flag = True
        self._terminate_ps_process()
        if self.engine and self.is_speaking:
            try:
                self.engine.stop()
            except Exception as e:
                print(f"停止朗读失败: {e}")
        self.is_speaking = False
        self.is_paused = False
        self.current_mapping = []

    def _terminate_ps_process(self, process=None):
        """安全终止PowerShell TTS进程"""
        if process is None:
            with self.ps_lock:
                process = self.ps_process
                self.ps_process = None
        else:
            with self.ps_lock:
                if self.ps_process == process:
                    self.ps_process = None
        if not process:
            return
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
        except Exception as e:
            print(f"终止PowerShell TTS进程失败: {e}")
    
    def pause(self):
        """暂停朗读（pyttsx3不支持暂停，这里只是标记）"""
        # pyttsx3本身不支持暂停，但我们可以停止
        # 如果需要真正的暂停功能，需要使用其他TTS库
        self.is_paused = True
        self.stop()
    
    def resume(self):
        """恢复朗读"""
        # pyttsx3不支持恢复，需要重新开始
        self.is_paused = False
    
    def is_available(self) -> bool:
        """检查TTS是否可用"""
        return HAS_TTS and self.engine is not None
    
    def get_available_voices_info(self) -> list:
        """获取可用语音信息"""
        if not self.engine:
            return []
        
        try:
            voices = self.engine.getProperty('voices')
            if voices:
                return [{"id": v.id, "name": v.name} for v in voices]
        except:
            pass
        
        return []

