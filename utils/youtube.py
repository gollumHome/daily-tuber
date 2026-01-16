import feedparser
import os
from datetime import datetime, timedelta, timezone
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
import yt_dlp
import config

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
    """核心逻辑: 尝试获取字幕，失败则下载音频"""

    # 构造代理字典
    tx_proxies = None
    if config.PROXY_URL:
        tx_proxies = {"https": config.PROXY_URL, "http": config.PROXY_URL}

    # --- 方案 A: 获取字幕 (升级版 API) ---
    print(f"  [*] 尝试获取字幕: {video_id}")
    try:
        # 1. 获取该视频所有可用的字幕列表
        # list_transcripts 能获取到 "自动生成" 和 "手动上传" 的所有字幕
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id, proxies=tx_proxies)

        # 2. 智能筛选语言
        # 优先找中文(简/繁)，如果没有，找英文
        # find_transcript 会自动在列表中寻找匹配的语言
        try:
            transcript = transcript_list.find_transcript(['zh-Hans', 'zh-CN', 'zh-Hant', 'zh-TW', 'en', 'en-US'])
        except NoTranscriptFound:
            # 如果没找到指定语言，尝试翻译成中文（这是 list_transcripts 的强大功能）
            # 或者直接取第一个可用的（通常是原声）
            print("    - 未找到指定语言字幕，尝试获取原声...")
            transcript = list(transcript_list)[0]

        # 3. 下载并拼接
        result = transcript.fetch()
        full_text = " ".join([t['text'] for t in result])

        return {"type": "text", "content": full_text}

    except (TranscriptsDisabled, NoTranscriptFound):
        print("  [!] 该视频未开启字幕功能。")
    except Exception as e:
        print(f"  [!] 字幕获取异常 ({e})，准备切换到音频...")

    # --- 方案 B: 下载音频 (保持不变) ---
    try:
        print(f"  [*] 开始下载音频: {video_id}")
        output_path = os.path.join(config.TEMP_DIR, f"{video_id}.mp3")

        if os.path.exists(output_path):
            os.remove(output_path)

        ydl_opts = {
            #'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
            'cookiefile':None,
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(config.TEMP_DIR, f"{video_id}.%(ext)s"),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }],
            'quiet': True,
            'no_warnings': True,
            # 2. 增加随机等待时间，进一步模拟人类
            'sleep_interval_requests': 10,
            'extractor_args': {
                'youtube': {
                     'player_client': ['ios'],
                    'player_skip': ['webpage', 'configs', 'js'],
                    'include_live_dash': False,
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
            }
            }
        if config.PROXY_URL:
            ydl_opts['proxy'] = config.PROXY_URL

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])

        return {"type": "audio", "path": output_path}

    except Exception as e:
        print(f"  [X] 音频下载也失败了: {e}")
        return None