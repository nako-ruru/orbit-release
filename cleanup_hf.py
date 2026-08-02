import argparse
import datetime
import os
import sys
from huggingface_hub import HfApi


def cleanup_hf_repo(repo_id, token, max_age_hours=24):
    """清理 Hugging Face Dataset 中指定目录下超过 max_age_hours 的旧发布资产"""
    print(
        f"🧹 开始扫描 Hugging Face 仓库: [{repo_id}] (保留时间: {max_age_hours} 小时)..."
    )
    api = HfApi(token=token)

    try:
        files_info = api.list_files_info(repo_id=repo_id, repo_type="dataset")
    except Exception as e:
        print(f"❌ 获取仓库文件列表失败: {e}")
        return

    now = datetime.datetime.now(datetime.timezone.utc)
    deleted_count = 0

    for file_info in files_info:
        path = file_info.rpath
        # 只清理 releases/ 目录下的过往构建资产
        if path.startswith("releases/"):
            last_modified = file_info.last_modified
            age_hours = (now - last_modified).total_seconds() / 3600

            if age_hours > max_age_hours:
                print(
                    f"🗑️ 删除过期文件: {path} (已存在 {age_hours:.1f} 小时)"
                )
                try:
                    api.delete_file(
                        path_in_repo=path, repo_id=repo_id, repo_type="dataset"
                    )
                    deleted_count += 1
                except Exception as e:
                    print(f"⚠️ 删除文件失败 {path}: {e}")

    print(
        f"✅ 清理完成！仓库 [{repo_id}] 共删除 {deleted_count} 个过期资产。\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Hugging Face 资产过期自动清理工具"
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("HF_TOKEN"),
        help="Hugging Face Access Token",
    )
    parser.add_argument(
        "--hours", type=int, default=24, help="资产保留小时数 (默认 24 小时)"
    )
    args = parser.parse_args()

    if not args.token:
        print("❌ 错误: 未提供 HF_TOKEN 环境变量或 --token 参数！")
        sys.exit(1)

    # 1. 清理公开 Dataset
    cleanup_hf_repo(
        repo_id="nako-ruru/orbit",
        token=args.token,
        max_age_hours=args.hours,
    )
    # 2. 清理私有 Dataset
    cleanup_hf_repo(
        repo_id="nako-ruru/orbit-private",
        token=args.token,
        max_age_hours=args.hours,
    )