import feedparser
import os
from datetime import datetime, timedelta, timezone

import requests
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import yt_dlp
import config
from utils.ai import transcribe_audio

# 如果配置了代理，设置全局环境变量，这样 feedparser/requests 会自动跟随
if config.PROXY_URL:
    os.environ["http_proxy"] = config.PROXY_URL
    os.environ["https_proxy"] = config.PROXY_URL
    print(f"[*] 检测到代理配置，已启用: {config.PROXY_URL}")


def get_latest_videos(target_tag):
    """
    遍历指定分类的频道，获取过去24小时内的视频列表，并过滤掉直播内容
    target_tag: 'crypto' (币圈) 或 'stock' (美股)
    """
    latest_videos = []
    now = datetime.now(timezone.utc)
    time_threshold = now - timedelta(hours=config.Hg_HOURS)

    # 1. 筛选出属于当前分类的频道
    target_channels = {k: v for k, v in config.CHANNELS.items() if v.get('tag') == target_tag}

    print(f"[*] 任务类型: [{target_tag.upper()}] | 开始检查 {len(target_channels)} 个频道的更新...")

    for name, info in target_channels.items():
        channel_id = info['id']
        # 补全 RSS URL
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
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

    print(f"[*] 检查完毕，[{target_tag.upper()}] 共有 {len(latest_videos)} 个新视频待处理。")
    return latest_videos


def get_video_content(video_id):
    """
    保持原有逻辑：方案 A 官方字幕 -> 方案 B RapidAPI 中转音频
    """
    import os
    import requests
    import config

    try:
        output_path = os.path.join(config.TEMP_DIR, f"{video_id}.mp3")
        if os.path.exists(output_path): os.remove(output_path)

        api_key = os.environ.get("RAPIDAPI_KEY", "a143cc11d0mshb2a4d08b4de7745p13cf02jsnc55f99458f14")

        # 精确适配截图中的 API 结构
        api_configs = [
            {
                "name": "MP36",
                "url": "https://youtube-mp36.p.rapidapi.com/dl",
                "host": "youtube-mp36.p.rapidapi.com",
                "params": {"id": video_id}
            },
            {
                "name": "Audio-Video-Downloader",
                # 根据截图：ID 嵌入 URL 路径
                "url": f"https://youtube-mp3-audio-video-downloader.p.rapidapi.com/get_mp3_download_link/{video_id}",
                "host": "youtube-mp3-audio-video-downloader.p.rapidapi.com",
                "params": {"quality": "low", "wait_until_the_file_is_ready": "false"}
            }
        ]

        download_success = False
        for api in api_configs:
            print(f"    [*] 尝试中转节点: {api['name']}")
            try:
                headers = {
                    "x-rapidapi-key": api_key,
                    "x-rapidapi-host": api["host"]
                }
                response = requests.get(api["url"], headers=headers, params=api["params"], timeout=30)
                data = response.json()

                # 提取直链：API 1 通常在 'link'，API 2 可能在 'link' 或 'result'
                dlink = data.get('link') or data.get('result') or data.get('download_url')

                if dlink:
                    print(f"      [+] 拿到直链，正在落盘...")
                    audio_res = requests.get(dlink, stream=True, timeout=60)
                    with open(output_path, 'wb') as f:
                        for chunk in audio_res.iter_content(chunk_size=8192):
                            f.write(chunk)
                    download_success = True
                    break  # 成功则跳出循环
                else:
                    print(f"      [-] 节点解析未返回有效链接")
            except Exception as inner_e:
                print(f"      [!] 节点尝试异常: {inner_e}")
                continue

        if download_success:
            return {"type": "audio", "path": output_path}
        else:
            print(f"  [X] 所有 RapidAPI 中转节点均失败")
            return None

    except Exception as e:
        print(f"  [X] 音频下载流程严重异常: {e}")
        return None