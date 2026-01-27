import os
import random
import sys

from utils import youtube, ai
from utils.notify import WeChatNotifier
import time

from utils.youtube import get_latest_videos


def main():
    print("=== YouTube 每日抓取任务开始 ===")

    notifier = WeChatNotifier()
    category = "stock"
    if len(sys.argv) > 1:
        category = sys.argv[1].lower()

    if category not in ["crypto", "stock"]:
        print("错误: 参数必须是 crypto 或 stock")
        return

    # 获取对应分类的视频
    videos = get_latest_videos(category)

    if not videos:
        print("[-] 过去 24 小时没有新视频发布。")
        return

    print(f"[*] 待处理视频数量: {len(videos)}")

    # 获取视频总数，用于判断是否是最后一个
    total_videos = len(videos)
    # 使用 enumerate 获取索引，方便判断是否是最后一个视频
    for index, video in enumerate(videos):
        print(f"\n>>> 正在处理: {video['title']}")

        # 2.1 获取内容 (字幕 or 音频)
        content_data = youtube.get_video_content(video['video_id'])

        if not content_data:
            print("  [X] 跳过：无法获取内容")
            continue

        # 2.2 AI 总结
        summary = ai.summarize_content(content_data)

        print(summary)

        # 2.3 推送
        notifier.send(
            title=video['title'],
            summary=summary,
            link=video['url'],
            author=video['channel']
        )

        #2.4 清理本地临时文件 (如果是音频下载模式)
        if content_data['type'] == 'audio' and os.path.exists(content_data['path']):
            os.remove(content_data['path'])
            print("  [-] 临时音频已删除")

        # ================= 限流逻辑 =================
        # 如果不是最后一个视频，就休息 20 秒
        if index < total_videos - 1:
            # 设置随机等待时间的范围（单位：秒）
            min_seconds = 120  # 2分钟
            max_seconds = 300  # 5分钟

            # 在设定的范围内生成一个随机整数
            wait_seconds = random.randint(min_seconds, max_seconds)

            print(f"  [⏳] 冷却中... 随机休息 {wait_seconds} 秒（约 {wait_seconds // 60} 分钟），避免触发 API 限制")
            time.sleep(wait_seconds)

    print("\n=== 任务完成 ===")


if __name__ == "__main__":
    main()