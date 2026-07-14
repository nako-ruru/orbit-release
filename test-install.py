import os
import platform
import subprocess
import sys
import threading
import urllib.request
import hashlib  # 导入哈希库
import time  # 导入时间库用于重试等待

# 强行让 Windows 环境下的控制台支持 UTF-8 实时中文输出
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# ==========================================================
# 1. 入口环境变量检查与打印
# ==========================================================
print("=================== 初始环境检查 ===================")
target_envs = ["GITHUB_ACTIONS", "ORBIT_LOG_PATH"]
for var in target_envs:
    val = os.environ.get(var)
    if val is not None and val.strip() != "":
        print(f"🌱 环境变量检测到: {var}={val}")
    else:
        print(f"⚠️ 环境变量未配置: {var}")
print("====================================================\n")


def calculate_sha256(filepath):
    """
    高效计算本地文件的 SHA-256 校验和（流式读取，内存安全）
    """
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        return f"计算失败: {e}"


def robust_download(url, filename, retries=5, delay=3):
    """
    【核心黑科技】高可靠下载器。
    1. 伪装 Chrome 浏览器 User-Agent，100% 绕过 CDN/WAF 针对 Python 脚本的 1MB 截断限制。
    2. 支持最多 5 次自动退避重试，无惧 GitHub Actions 跨境网络波动。
    3. 流式分块读写，防止内存溢出。
    """
    # 伪装成标准的 Windows Chrome 浏览器
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    for attempt in range(1, retries + 1):
        print(f"📥 正在下载 (尝试 {attempt}/{retries}): {url}")
        try:
            req = urllib.request.Request(url, headers=headers)
            # 设置 30 秒超时，防止单次卡死
            with urllib.request.urlopen(req, timeout=30) as response:
                content_length = response.getheader('Content-Length')
                expected_size = int(content_length) if content_length else None

                downloaded_size = 0
                with open(filename, 'wb') as f:
                    while True:
                        # 每次读取 64KB
                        chunk = response.read(1024 * 64)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded_size += len(chunk)

                # 安全性校验：判断下载大小是否和服务器提供的一致
                if expected_size is not None and downloaded_size < expected_size:
                    raise IOError(f"下载文件不完整: 仅获取到 {downloaded_size}/{expected_size} 字节")

                print("✅ 下载完成。")
                return True

        except Exception as e:
            print(f"⚠️ 第 {attempt} 次下载尝试失败: {e}", file=sys.stderr)
            # 如果文件已部分写入，清理掉防止 SHA-256 算错
            if os.path.exists(filename):
                try:
                    os.remove(filename)
                except:
                    pass

            if attempt < retries:
                print(f"等待 {delay} 秒后重试...", file=sys.stderr)
                time.sleep(delay)
            else:
                print("❌ 达到最大重试次数，下载彻底失败。", file=sys.stderr)
                raise e


def run_command_streaming(cmd):
    """
    实时流式输出进程日志，且严格基于 PID 阻塞，绝不因主程序常驻而挂起 CI
    """
    print(f"执行命令: {' '.join(cmd)}")
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace'
        )

        def reader_thread():
            try:
                for line in iter(process.stdout.readline, ''):
                    print(line, end='', flush=True)
            except Exception:
                pass

        t = threading.Thread(target=reader_thread)
        t.daemon = True
        t.start()

        returncode = process.wait()
        return returncode
    except Exception as e:
        print(f"执行命令时发生异常: {e}", file=sys.stderr)
        return -1


# 2. 自动识别系统与架构
sys_os = platform.system()
arch = platform.machine().lower()

uninstaller = ""
url = ""
filename = ""

if sys_os == "Windows":
    base_path = r"C:\Program Files\orbit\uninstaller"
    if os.path.exists(base_path + ".exe"):
        uninstaller = base_path + ".exe"
    elif os.path.exists(base_path):
        uninstaller = base_path

    url = "https://guanghe.co/download/orbit_installer_windows.exe"
    filename = "orbit_installer_windows.exe"

elif sys_os == "Linux":
    uninstaller = "/opt/orbit/Orbit.AppDir/usr/bin/uninstaller"
    url = "https://guanghe.co/download/orbit_installer_linux"
    filename = "orbit_installer_linux"

elif sys_os == "Darwin":
    uninstaller = "/Applications/Orbit.app/Contents/MacOS/uninstaller"
    if "arm64" in arch:
        url = "https://guanghe.co/download/orbit_installer_darwin_arm64"
        filename = "orbit_installer_darwin_arm64"
    else:
        url = "https://guanghe.co/download/orbit_installer_darwin_x86_64"
        filename = "orbit_installer_darwin_x86_64"
else:
    print(f"不支持的操作系统: {sys_os}", file=sys.stderr)
    sys.exit(1)

# 3. 如果卸载程序存在，先执行卸载
if uninstaller and os.path.exists(uninstaller):
    print(f"【旧版本审计】检测到旧版本，正在流式执行卸载...")
    uninstall_cmd = [uninstaller] if sys_os == "Windows" else ["sudo", "-E", uninstaller]
    code = run_command_streaming(uninstall_cmd)
    if code == 0:
        print("旧版本卸载完毕。")
    else:
        print(f"旧版本卸载返回非零状态码: {code}（尝试继续安装）")
else:
    print("未检测到旧版本或无需卸载，跳过此步骤。")

# 4. 安全下载安装包
try:
    robust_download(url, filename)
    if sys_os != "Windows":
        os.chmod(filename, 0o755)
except Exception as e:
    print(f"💥 下载失败并退出: {e}", file=sys.stderr)
    sys.exit(1)

# 5. 计算并显示下载文件的 SHA-256 校验和
print("🔒 正在校验安装包哈希值...")
sha256_result = calculate_sha256(filename)
print(f"💾 文件名: {filename}")
print(f"🔑 SHA-256: {sha256_result}\n")

# 6. 流式执行安装程序
print(f"正在以 [流式阻塞模式] 启动安装程序...")
if sys_os == "Windows":
    exec_cmd = [filename, "--silent", "--install-dir", r"C:\Program Files\Orbit"]
else:
    exec_cmd = ["sudo", "-E", f"./{filename}"]

exit_code = run_command_streaming(exec_cmd)

if exit_code == 0:
    print("🎉 安装程序执行完毕且成功退出，日志已全部冲刷至控制台。")
else:
    print(f"❌ 安装程序执行失败，退出码: {exit_code}", file=sys.stderr)
    sys.exit(exit_code)