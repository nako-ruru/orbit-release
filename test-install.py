import os
import platform
import subprocess
import sys
import threading
import urllib.request
import hashlib
import time

# 强行让 Windows 环境下的控制台支持 UTF-8 实时中文输出
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')


# ==========================================================
# 1. 核心测试：重定向链路追踪器 (Redirect Tracer)
# ==========================================================
class TraceRedirectHandler(urllib.request.HTTPRedirectHandler):
    """
    自定义重定向处理器，用于捕获并向控制台实时打印重定向轨迹
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        print(f"   🔄 [重定向触发] HTTP {code}: -> {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# 注册自定义的重定向追踪器，使其全局生效
opener = urllib.request.build_opener(TraceRedirectHandler)
urllib.request.install_opener(opener)

# ==========================================================
# 2. 入口环境变量检查与打印
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


def robust_download(url, filename, chunk_size=900 * 1024):
    """
    【兼容重定向与分片的高可靠下载器】
    1. 首次请求时，允许通过自定义的 TraceRedirectHandler 自动完成重定向，并捕获最终文件的真实下载地址。
    2. 针对最终下载地址（无论是 GitHub 还是 GitCode），进行 Range 分片下载，100% 免疫 1MB 掐断。
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    print(f"🛰️ 发起初始请求: {url}")
    actual_url = url
    total_size = 0

    try:
        # 发送一个 HEAD 或带有 Range 的请求，顺便完成重定向追踪
        test_req = urllib.request.Request(url, headers={**headers, 'Range': 'bytes=0-0'})
        with urllib.request.urlopen(test_req, timeout=15) as resp:
            # 获取重定向之后的最终真实 URL
            actual_url = resp.geturl()

            if resp.status != 206:
                print("⚠️ 警告: 最终存储服务器未返回 206 Partial Content，可能不支持分片下载。")
                raise ValueError("No range support")

            content_range = resp.getheader('Content-Range')
            if content_range:
                total_size = int(content_range.split('/')[-1])
                print(f"📊 架构验证成功！")
                print(f"   🔹 最终解析下载源: {actual_url}")
                print(f"   🔹 文件总大小: {total_size} 字节 (~{total_size / (1024 * 1024):.2f} MB)")
            else:
                raise ValueError("未获取到 Content-Range 请求头")

    except Exception as e:
        print(f"⚠️ 分片探测遇到限制 ({e})，将尝试使用常规单流下载...")
        # 降级方案
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as response:
            with open(filename, 'wb') as f:
                f.write(response.read())
            print(f"✅ 下载完成（常规模式），最终源自: {response.geturl()}")
        return True

    # 3. 如果支持 Range，开始使用最终真实 URL 进行安全分片拼接
    if os.path.exists(filename):
        os.remove(filename)

    start_byte = 0
    part_num = 1

    print(f"🧩 启动分片下载机制 (每片安全大小: {chunk_size // 1024} KB)...")
    with open(filename, 'wb') as f:
        while start_byte < total_size:
            end_byte = min(start_byte + chunk_size - 1, total_size - 1)
            range_str = f"bytes={start_byte}-{end_byte}"

            # 单个分片的重试逻辑
            success = False
            for attempt in range(1, 4):
                try:
                    # 注意：这里直接向最终实际地址 actual_url 请求分片，避免重复触发重定向判定，提高效率
                    req = urllib.request.Request(actual_url, headers={**headers, 'Range': range_str})
                    with urllib.request.urlopen(req, timeout=20) as resp:
                        data = resp.read()
                        f.write(data)
                        start_byte += len(data)
                        print(f"   📥 已完成分片 {part_num:02d}: {range_str} ({len(data)} 字节)")
                        success = True
                        break
                except Exception as e:
                    print(f"   ⚠️ 分片 {part_num} 遭遇抖动 (尝试 {attempt}/3): {e}，正在重试...")
                    time.sleep(2)

            if not success:
                raise RuntimeError(f"💥 分片 {part_num} 彻底下载失败，任务终止！")

            part_num += 1

    print("🎉 恭喜！所有分片下载并顺利拼接完成！")
    return True


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

# 4. 安全下载安装包（调用追踪重定向下载器）
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