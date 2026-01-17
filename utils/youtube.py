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


import os
import requests
import config
import time

import os
import requests
import config
import time
import re


def clean_str(s):
    """清洗字符串，只保留 ASCII，防止 Header 报错"""
    if not s:
        return ""
    return str(s).encode('ascii', 'ignore').decode('ascii').strip()


def get_rapidapi_nodes(video_id):
    """
    配置所有可用的 RapidAPI 节点。
    只需在此处增加新节点，无需改动主逻辑。
    """
    # 确保 video_id 干净
    v_id = str(video_id).strip()
    v_url = f"https://www.youtube.com/watch?v={v_id}"
    return [
        {
            "name": "MP36",
            "url": "https://youtube-mp36.p.rapidapi.com/dl",
            "host": "youtube-mp36.p.rapidapi.com",
            "params": {"id": v_id},
            "link_field": "link"  # 该 API 返回结果中直链的键名
        },
        {
            "name": "Audio-Video-Downloader",
            "url": f"https://youtube-mp3-audio-video-downloader.p.rapidapi.com/get_mp3_download_link/{v_id}",
            "host": "youtube-mp3-audio-video-downloader.p.rapidapi.com",
            "params": {"quality": "low"},
            "link_field": "result"
        },
        {
            "name": "YT-Audio-Video-V2 (新)",
            "url": "https://youtube-audio-and-video-downloader.p.rapidapi.com/youtube",
            "host": "youtube-audio-and-video-downloader.p.rapidapi.com",
            "params": {"url": v_url, "type": "audio"},  # 该节点支持直接选 audio
            "link_field": "link"  # 通常该 API 返回的键名是 link
        },
    ]


def get_video_content(video_id):
    """
    针对 GHA 优化的音频提取主方法 (包含新节点轮询)
    """
    output_path = os.path.join(config.TEMP_DIR, f"{video_id}.mp3")
    if os.path.exists(output_path): os.remove(output_path)
    if not os.path.exists(config.TEMP_DIR): os.makedirs(config.TEMP_DIR)

    # 严格清洗 Key 和 代理，防止 latin-1 报错
    api_key = str(os.environ.get("RAPIDAPI_KEY", "a143cc11d0mshb2a4d08b4de7745p13cf02jsnc55f99458f14")).strip()
    proxy_str = str(config.PROXY_URL or "").strip()
    proxies = {"http": proxy_str, "https": proxy_str} if proxy_str else None

    nodes = get_rapidapi_nodes(video_id)

    for node in nodes:
        print(f"    [*] 尝试音频节点: {node['name']}")
        try:
            headers = {
                "x-rapidapi-key": api_key,
                "x-rapidapi-host": node["host"].strip()
            }

            dlink = None
            # 轮询 3 次等待云端转换
            for attempt in range(3):
                response = requests.get(
                    node["url"],
                    headers=headers,
                    params=node["params"],
                    proxies=proxies,
                    timeout=30
                )

                if response.status_code == 429:
                    print(f"      [!] 节点额度耗尽(429)")
                    break
                if response.status_code != 200:
                    break

                data = response.json()
                data_str = str(data).lower()

                # 如果还在处理中
                if "process" in data_str or "wait" in data_str:
                    print(f"      [.] 转换中，等待 10s...")
                    time.sleep(10)
                    continue

                # 尝试多种可能的链接键名 (增强兼容性)
                dlink = data.get(node["link_field"]) or data.get("link") or data.get("download_url") or data.get("url")
                if dlink: break

            if dlink:
                print(f"      [+] 拿到直链，正在下载...")
                dl_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://google.com/"
                }

                with requests.get(dlink, headers=dl_headers, proxies=proxies, stream=True, timeout=180) as r:
                    if r.status_code == 200:
                        with open(output_path, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=1024 * 1024):
                                if chunk: f.write(chunk)

                        if os.path.exists(output_path) and os.path.getsize(output_path) > 102400:
                            print(f"      [√] 成功落地: {os.path.getsize(output_path) / 1024 / 1024:.2f} MB")
                            return {"type": "audio", "path": output_path}
                    else:
                        print(f"      [X] 下载流失败，状态码: {r.status_code}")
        except Exception as e:
            print(f"      [!] 节点异常: {str(e)[:100]}")
            continue

    print(f"  [X] 所有节点均失败。")
    return None