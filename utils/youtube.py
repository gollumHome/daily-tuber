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
    方案：通过 RapidAPI 中转获取音频直链，并强制走代理下载，确保 GHA 不被拦截。
    """
    import os
    import requests
    import config
    import time

    try:
        # 1. 准备工作
        output_path = os.path.join(config.TEMP_DIR, f"{video_id}.mp3")
        if os.path.exists(output_path):
            os.remove(output_path)

        # 确保临时目录存在
        if not os.path.exists(config.TEMP_DIR):
            os.makedirs(config.TEMP_DIR)

        # 获取 API Key
        api_key = os.environ.get("RAPIDAPI_KEY", "a143cc11d0mshb2a4d08b4de7745p13cf02jsnc55f99458f14")

        # 2. 构造代理配置 (V2Ray 节点)
        dl_proxies = None
        if config.PROXY_URL:
            dl_proxies = {
                "http": config.PROXY_URL,
                "https": config.PROXY_URL
            }

        # 3. 备用 API 节点配置
        api_configs = [
            {
                "name": "MP36",
                "url": "https://youtube-mp36.p.rapidapi.com/dl",
                "host": "youtube-mp36.p.rapidapi.com",
                "params": {"id": video_id}
            },
            {
                "name": "Audio-Video-Downloader",
                "url": f"https://youtube-mp3-audio-video-downloader.p.rapidapi.com/get_mp3_download_link/{video_id}",
                "host": "youtube-mp3-audio-video-downloader.p.rapidapi.com",
                "params": {"quality": "low", "wait_until_the_file_is_ready": "false"}
            }
        ]

        final_file_path = None

        # 4. 轮询 API 节点
        for api in api_configs:
            print(f"    [*] 正在尝试中转节点: {api['name']}")
            try:
                headers = {
                    "x-rapidapi-key": api_key,
                    "x-rapidapi-host": api["host"]
                }

                # 获取中转直链 (这一步通常不需要代理，RapidAPI 响应很快)
                response = requests.get(api["url"], headers=headers, params=api["params"],proxies=dl_proxies, timeout=30)
                data = response.json()

                # 提取直链
                dlink = data.get('link') or data.get('result') or data.get('download_url')

                if dlink:
                    print(f"      [+] 拿到直链，准备下载音频流...")

                    # 模拟浏览器请求头，防止存储端识别
                    dl_headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                        "Accept": "audio/mpeg,audio/*;q=0.9",
                        "Referer": "https://www.y2mate.com/"
                    }

                    # --- 核心：通过代理下载文件 ---
                    audio_res = requests.get(
                        dlink,
                        headers=dl_headers,
                        proxies=dl_proxies,  # 走 V2Ray 代理
                        stream=True,
                        timeout=180
                    )

                    if audio_res.status_code == 200:
                        with open(output_path, 'wb') as f:
                            for chunk in audio_res.iter_content(chunk_size=1024 * 1024):
                                if chunk: f.write(chunk)

                        # 校验文件有效性
                        f_size = os.path.getsize(output_path)
                        if f_size > 1024 * 100:  # 必须大于 100KB
                            print(f"      [√] 音频落地成功: {f_size / 1024 / 1024:.2f} MB")
                            final_file_path = output_path
                            break  # 关键：下载成功，跳出 API 轮询
                        else:
                            print(f"      [!] 警告：下载文件过小 ({f_size} bytes)，疑似 403 页面，尝试下一节点")
                            if os.path.exists(output_path): os.remove(output_path)
                    else:
                        print(f"      [X] 下载响应失败，状态码: {audio_res.status_code}")
                else:
                    print(f"      [-] 节点解析未返回有效链接: {data.get('msg', 'no msg')}")

            except Exception as inner_e:
                print(f"      [!] 节点尝试异常: {inner_e}")
                continue

        # 5. 返回结果
        if final_file_path:
            return {"type": "audio", "path": final_file_path}
        else:
            print(f"  [X] 错误：所有中转节点及代理下载均已失败")
            return None

    except Exception as e:
        print(f"  [X] get_video_content 严重异常: {e}")
        return None