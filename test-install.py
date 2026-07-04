import os
import platform
import subprocess
import sys
import urllib.request

# 1. 自动识别系统与架构，配置卸载路径与下载地址
sys_os = platform.system()
arch = platform.machine().lower()

uninstaller = ""
url = ""
filename = ""

if sys_os == "Windows":
    # 兼容处理 Windows 下可能带或不带 .exe 后缀的情况
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

# 2. 如果卸载程序存在，先执行卸载
if uninstaller and os.path.exists(uninstaller):
    print(f"检测到旧版本，正在执行卸载: {uninstaller}")
    try:
        subprocess.run([uninstaller], check=True)
        print("旧版本卸载完毕。")
    except subprocess.CalledProcessError as e:
        print(f"卸载失败，错误码: {e.returncode}", file=sys.stderr)
    except Exception as e:
        print(f"运行卸载程序时发生异常: {e}", file=sys.stderr)
else:
    print("未检测到旧版本或无需卸载，跳过此步骤。")

# 3. 下载对应的安装包
print(f"正在下载 ({sys_os}/{arch}): {url}")
try:
    urllib.request.urlretrieve(url, filename)
    if sys_os != "Windows":
        os.chmod(filename, 0o755)  # 针对 Mac/Linux 赋予执行权限
    print("下载完成。")
except Exception as e:
    print(f"下载失败: {e}", file=sys.stderr)
    sys.exit(1)

# 4. 以普通形式执行安装程序
print(f"正在启动安装程序: {filename}...")
try:
    exec_cmd = [filename] if sys_os == "Windows" else [f"./{filename}"]
    subprocess.run(exec_cmd, check=True)
    print("安装程序执行完毕。")
except subprocess.CalledProcessError as e:
    print(f"安装程序执行失败，错误码: {e.returncode}", file=sys.stderr)
except Exception as e:
    print(f"运行安装程序时发生异常: {e}", file=sys.stderr)