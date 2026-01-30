import feedparser
import os
from datetime import datetime, timedelta, timezone
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import yt_dlp
import config



def get_latest_videos(target_tag):
    """
    遍历指定分类的频道，获取过去24小时内的视频列表，并过滤掉直播内容
    target_tag: 'crypto' (币圈) 或 'stock' (美股)
    """
    if config.LOCAL_PROXY:
        os.environ["http_proxy"] = config.LOCAL_PROXY
        os.environ["https_proxy"] = config.LOCAL_PROXY
    latest_videos = []
    now = datetime.now(timezone.utc)
    time_threshold = now - timedelta(hours=config.Hg_HOURS)

    # 1. 筛选出属于当前分类的频道
    #target_channels = {k: v for k, v in config.CHANNELS.items() if v.get('tag') == target_tag}
    target_channels = {k: v for k, v in config.CHANNELS.items() }
    print(f"[*] 任务类型: [{target_tag.upper()}] | 开始检查 {len(target_channels)} 个频道的更新...")
    try:
        for name, info in target_channels.items():
            channel_id = info['id']
            # 补全 RSS URL
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            print(f"  [>] 正在尝试抓取: {name} (URL: {rss_url})")
            feed = feedparser.parse(rss_url)

            if not feed.entries:
                continue

            for entry in feed.entries:
                # RSS 发布时间转换
                pub_date = datetime.fromisoformat(entry.published)

                # 2. 时间筛选
                if pub_date > time_threshold:
                    # 3. 直播视频过滤 (通过标题和链接特征)
                    title_upper = entry.title.upper()
                    live_keywords = ["直播", "LIVE", "STREAM", "正在直播"]

                    # 判断逻辑：标题包含直播关键词 或 链接中包含 live 路径
                    is_live = any(kw in title_upper for kw in live_keywords) or "/live/" in entry.link

                    if is_live:
                        print(f"  [-] 跳过直播/回放: {name} - {entry.title}")
                        continue

                    video_info = {
                        "channel": name,
                        "title": entry.title,
                        "url": entry.link,
                        "video_id": entry.yt_videoid,
                        "pub_date": pub_date.strftime("%Y-%m-%d %H:%M"),
                        "tag": target_tag
                    }
                    latest_videos.append(video_info)
                    print(f"  [+] 发现新视频: {name} - {entry.title}")
    finally:
        # 任务结束后，务必清除代理，防止影响 Whisper 等本地逻辑
        if "http_proxy" in os.environ: del os.environ["http_proxy"]
        if "https_proxy" in os.environ: del os.environ["https_proxy"]
    print(f"[*] 检查完毕，[{target_tag.upper()}] 共有 {len(latest_videos)} 个新视频待处理。")
    return latest_videos


def get_video_content(video_id):
    """核心逻辑: 尝试获取字幕，失败则下载音频"""


    try:
        print(f"  [*] 开始下载音频: {video_id}")
        output_path = os.path.join(config.TEMP_DIR, f"{video_id}.mp3")

        if os.path.exists(output_path):
            os.remove(output_path)

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(config.TEMP_DIR, f"{video_id}.%(ext)s"),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
            'quiet': True,
            #'verbose': True,
            'no_warnings': True,
            'proxy': config.RESIDENTIAL_PROXY,
            'hls_prefer_native': True,
            'http_chunk_size': 1048576,
        }


        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])

        return {"type": "audio", "path": output_path}

    except Exception as e:
        print(f"  [X] 音频下载也失败了: {e}")
        return None