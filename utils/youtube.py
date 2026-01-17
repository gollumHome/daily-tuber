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


import os
import requests
import time
import config


def get_video_content(video_id):
    """
    针对 GHA 404 错误优化的音频提取方法
    """
    v_id = str(video_id).strip()
    v_url = f"https://www.youtube.com/watch?v={v_id}"
    output_path = os.path.join(config.TEMP_DIR, f"{v_id}.mp3")

    if os.path.exists(output_path): os.remove(output_path)
    if not os.path.exists(config.TEMP_DIR): os.makedirs(config.TEMP_DIR)

    api_key = str(os.environ.get("RAPIDAPI_KEY", "a143cc11d0mshb2a4d08b4de7745p13cf02jsnc55f99458f14")).strip()
    proxy_str = str(config.PROXY_URL or "").strip()
    proxies = {"http": proxy_str, "https": proxy_str} if proxy_str else None

    # 节点池
    nodes = [
        {
            "name": "YT-Audio-Video-V2 (新订阅)",
            "url": "https://youtube-audio-and-video-downloader.p.rapidapi.com/youtube",
            "host": "youtube-audio-and-video-downloader.p.rapidapi.com",
            "params": {"url": v_url, "type": "audio"},
            "link_keys": ["link", "downloadUrl", "url"]
        },
        {
            "name": "MP36",
            "url": "https://youtube-mp36.p.rapidapi.com/dl",
            "host": "youtube-mp36.p.rapidapi.com",
            "params": {"id": v_id},
            "link_keys": ["link"]
        },
        {
            "name": "Metatube-MP3",
            "url": "https://yt-download-metatube.p.rapidapi.com/mp3",
            "host": "yt-download-metatube.p.rapidapi.com",
            "params": {"id": v_id},
            "link_keys": ["url", "link"]
        }
    ]

    for node in nodes:
        print(f"    [*] 尝试节点: {node['name']}")
        try:
            headers = {
                "x-rapidapi-key": api_key,
                "x-rapidapi-host": node["host"].strip()
            }

            dlink = None
            # 1. 尝试获取直链 (增加轮询次数和时长)
            for attempt in range(5):
                try:
                    # 获取 API 响应 (增加超时)
                    res = requests.get(node["url"], headers=headers, params=node["params"], proxies=proxies, timeout=60)
                    if res.status_code != 200:
                        print(f"      [!] API 响应异常: {res.status_code}")
                        break

                    data = res.json()
                    data_str = str(data).lower()

                    if "process" in data_str or "wait" in data_str:
                        print(f"      [.] 转换中 (第{attempt + 1}次)...")
                        time.sleep(12)
                        continue

                    # 尝试从多个可能的键中寻找直链
                    for k in node["link_keys"]:
                        if data.get(k):
                            dlink = data[k]
                            break
                    if dlink: break

                    # 某些 API 返回的是列表
                    if isinstance(data.get('data'), list) and len(data['data']) > 0:
                        dlink = data['data'][0].get('url') or data['data'][0].get('link')
                        if dlink: break

                except Exception as node_e:
                    print(f"      [!] 请求 API 异常: {node_e}")
                    break

            # 2. 如果拿到直链，进入下载阶段
            if dlink:
                print(f"      [+] 拿到直链，准备下载...")
                dl_headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": f"https://{node['host']}/"
                }

                # 核心改进：针对 404 进行延迟重试下载
                success = False
                for dl_retry in range(3):
                    try:
                        # 下载时务必和 API 请求保持一致的代理配置
                        with requests.get(dlink, headers=dl_headers, proxies=proxies, stream=True, timeout=300) as r:
                            if r.status_code == 200:
                                with open(output_path, 'wb') as f:
                                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                                        if chunk: f.write(chunk)

                                if os.path.exists(output_path) and os.path.getsize(output_path) > 100 * 1024:
                                    print(f"      [√] 下载成功: {os.path.getsize(output_path) / 1024 / 1024:.2f} MB")
                                    success = True
                                    break
                            elif r.status_code == 404:
                                print(f"      [!] 下载返回 404，文件可能还在同步，等待 15s 后重试 ({dl_retry + 1}/3)...")
                                time.sleep(15)
                            else:
                                print(f"      [X] 下载失败，状态码: {r.status_code}")
                                break  # 其他错误（如403）直接换节点
                    except Exception as dl_e:
                        print(f"      [!] 下载流异常: {dl_e}")
                        time.sleep(5)

                if success:
                    return {"type": "audio", "path": output_path}
            else:
                print(f"      [-] 节点解析未返回链接")

        except Exception as e:
            print(f"      [!] 节点处理异常: {e}")
            continue

    print(f"  [X] 所有 API 节点及重试均已失败")
    return None