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


def get_rapidapi_audio_nodes(video_id):
    """
    方法一：定义目前最稳的两个 API 节点池
    """
    v_id = str(video_id).strip()

    return [
        {
            "name": "YouTube-MP3-2025 (最新/最稳)",
            "url": "https://youtube-mp3-2025.p.rapidapi.com/v1/social/youtube/audio",
            "host": "youtube-mp3-2025.p.rapidapi.com",
            "params": {"id": v_id, "quality": "128kbps", "ext": "mp3"},
            "link_field": "linkDownload"
        },
        {
            "name": "MP36 (标准备选)",
            "url": "https://youtube-mp36.p.rapidapi.com/dl",
            "host": "youtube-mp36.p.rapidapi.com",
            "params": {"id": v_id},
            "link_field": "link"
        }
    ]



def get_video_content(video_id):
    """
    逻辑不动，修复 SSL EOF 错误并增加诊断日志
    """
    output_path = os.path.join(config.TEMP_DIR, f"{video_id}.mp3")
    if os.path.exists(output_path): os.remove(output_path)
    if not os.path.exists(config.TEMP_DIR): os.makedirs(config.TEMP_DIR)

    raw_keys = os.environ.get("RAPIDAPI_KEYS", "")
    # 将字符串转为列表
    api_keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
    
    if not api_keys:
        print("CRITICAL ERROR: No RapidAPI keys found in environment variables!")
        # 如果是在 GitHub Actions 运行，这会让任务报错停止，提醒你检查设置
        exit(1)
    if not api_keys:
        print("  [X] 错误：未配置任何 RAPIDAPI_KEY")
        return None

    proxy_str = str(config.PROXY_URL or "").strip()
    proxies = {"http": proxy_str, "https": proxy_str} if proxy_str else None
    nodes = get_rapidapi_audio_nodes(video_id)

    # --- 核心修复：引入 Session 提高 SSL 握手稳定性 ---
    session = requests.Session()
    session.proxies = proxies

    # --- 第一层：轮询 API Key ---
    for api_key in api_keys:
        print(f"  [*] 正在使用 API Key: {api_key[:8]}***")

        # --- 第二层：轮询 节点池 ---
        for node in nodes:
            print(f"    [*] 尝试节点: {node['name']}")
            try:
                headers = {
                    "x-rapidapi-key": api_key,
                    "x-rapidapi-host": node["host"].strip(),
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "application/json"
                }

                dlink = None
                # --- 第三层：轮询 转换状态 ---
                for attempt in range(5):
                    try:
                        response = session.get(
                            node["url"],
                            headers=headers,
                            params=node["params"],
                            timeout=45
                        )

                        if response.status_code == 429:
                            print(f"      [!] 当前 Key 额度已耗尽 (429)")
                            break

                        if response.status_code != 200:
                            print(f"      [!] API 响应异常: {response.status_code}")
                            break

                        data = response.json()
                        dlink = data.get(node["link_field"]) or data.get("linkDownload") or data.get("link")

                        if not dlink or "process" in str(data).lower():
                            print(f"      [.] 视频转换中/未就绪 (Attempt {attempt + 1})...")
                            time.sleep(15)
                            continue

                        if dlink: break

                    except (requests.exceptions.SSLError, requests.exceptions.ConnectionError) as ssl_err:
                        # 针对你遇到的 SSL EOF 错误进行捕获
                        print(f"      [!] 网络握手异常 (SSL/EOF)，5秒后重试... ({attempt+1}/5)")
                        time.sleep(5)
                        continue
                    except Exception as e:
                        print(f"      [!] 请求过程发生错误: {e}")
                        break

                if dlink:
                    print(f"      [+] 拿到直链，准备下载...")
                    time.sleep(10)

                    dl_headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Referer": "https://rapidapi.com/"
                    }

                    # 下载重试逻辑
                    for dl_retry in range(5):
                        try:
                            # 下载也复用 session
                            with session.get(dlink, headers=dl_headers, stream=True, timeout=180) as r:
                                if r.status_code == 200:
                                    with open(output_path, 'wb') as f:
                                        for chunk in r.iter_content(chunk_size=1024 * 1024):
                                            if chunk: f.write(chunk)

                                    f_size = os.path.getsize(output_path)
                                    if f_size > 102400:
                                        print(f"      [√] 落地成功: {f_size / 1024 / 1024:.2f} MB")
                                        return {"type": "audio", "path": output_path}
                                    else:
                                        print(f"      [!] 落地文件过小 ({f_size} bytes)，准备重试...")
                                        time.sleep(15)
                                elif r.status_code == 404:
                                    print(f"      [!] 下载 404，等待 15s 重试 ({dl_retry + 1}/5)...")
                                    time.sleep(15)
                                else:
                                    print(f"      [X] 下载响应失败，状态码: {r.status_code}")
                                    break
                        except Exception as dl_e:
                            print(f"      [!] 下载流异常: {dl_e}")
                            time.sleep(5)

            except Exception as e:
                print(f"      [!] 节点处理崩溃: {e}")
                continue

    print(f"  [X] 最终失败：所有 Key 及所有节点均无法获取音频。")
    return None
