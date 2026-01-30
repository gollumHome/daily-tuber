import re
import site

import google.generativeai as genai
from faster_whisper import WhisperModel
from google.api_core import exceptions

import config
import time
import os


# 初始化 Gemini
genai.configure(api_key=config.GEMINI_API_KEY)


def init_whisper_model():
    """
    统一使用 CPU + int8 模式，兼顾本地稳定性和 GitHub Actions
    """
    print("[*] 正在加载 Whisper Medium 模型 (CPU 优化模式)...")
    # 1. 屏蔽环境变量，防止它去抓取系统代理
    if "http_proxy" in os.environ: del os.environ["http_proxy"]
    if "https_proxy" in os.environ: del os.environ["https_proxy"]

    # 2. 强制 HuggingFace 离线
    os.environ["HF_HUB_OFFLINE"] = "1"
    # int8 是 CPU 运行的黄金配置，内存占用约 2.2GB，准确率极高
    return WhisperModel("medium", device="cpu", compute_type="int8")


# 初始化
whisper_model = init_whisper_model()


def transcribe_audio(audio_path):
    try:
        print(f"  [*] 开始本地转写 (开启 VAD 过滤): {audio_path}")
        start_time = time.time()

        # --- 关键参数调整 ---
        segments, info =whisper_model.transcribe(
            audio_path,
            beam_size=2,
            language="zh",
            vad_filter=True,
            condition_on_previous_text=False
        )

        full_text = ""
        for segment in segments:
            # 过滤掉过短且重复的无效片段
            text = segment.text.strip()
            print(f"    [T] {segment.start:.1f}s -> {segment.text}")
            if len(text) > 1:  # 忽略单个标点或单字
                full_text += text + " "

        # 如果感叹号依然很多，我们不报错，直接清洗掉它
        if full_text.count('!') > 20 or full_text.count('！') > 20:
            print("  [!] 检测到部分幻听内容，正在进行清洗...")
            full_text = re.sub(r'[!！]{2,}', ' ', full_text)

        duration = time.time() - start_time
        print(f"  [+] 转写完成，耗时: {duration:.2f}s")
        return full_text.strip()
    except Exception as e:
        print(f"  [X] 本地转写失败: {e}")
        return None



def summarize_content(content_data):
    """
    分段分析全量内容，彻底解决长文本 429 问题
    """
    model = genai.GenerativeModel('gemini-flash-latest')

    # 1. 获取并清洗文本
    if content_data['type'] == 'text':
        full_text = content_data['content']
    else:
        full_text = transcribe_audio(content_data['path'])
        if not full_text: return "错误: 转写失败"

    # 清洗掉 Whisper 的幻听乱码
    full_text = re.sub(r'([!！?？\.。*])\1{2,}', r'\1', full_text)
    full_text = re.sub(r'\s+', ' ', full_text).strip()

    # 2. 设定分段逻辑
    # 5000字一段比较保险，既能保留上下文，又不容易触发 TPM 限制
    CHUNK_SIZE = 5000
    chunks = [full_text[i:i + CHUNK_SIZE] for i in range(0, len(full_text), CHUNK_SIZE)]

    if len(chunks) == 1:
        # 如果内容不长，直接走单次总结
        return call_gemini_with_retry(model, full_text, "simple")

    # 3. 分段提取核心信息 (Map 阶段)
    print(f"  [*] 内容过长，正在分 {len(chunks)} 段进行深度分析...")
    chunk_summaries = []

    for idx, chunk in enumerate(chunks):
        print(f"    - 正在分析第 {idx + 1}/{len(chunks)} 段...")
        chunk_prompt = f"这是长视频转录稿的第 {idx + 1} 部分。请提取该部分涉及的所有币种、点位、行情判断和核心逻辑。不需要格式化，请列出要点："

        summary = call_gemini_with_retry(model, chunk, chunk_prompt)
        chunk_summaries.append(summary)

        # 关键：每段之间强制休息，防止触发 429
        # 如果依然报 429，请把这个时间调长到 15-20
        time.sleep(30)

    # 4. 聚合最终报告 (Reduce 阶段)
    print("  [*] 正在聚合所有分段信息，生成最终简报...")
    final_input = "\n\n".join(chunk_summaries)
    final_prompt = """
    你是一个专业的技术与内容分析师。下面是同一段长视频的各部分要点提取。
    请将这些信息整合成一份逻辑严密的中文简报。

    输出格式要求 (Markdown):
    ### 📝 一句话总结
    (50字以内概括核心)

    ### 💡 核心观点
    * (列出所有关键点位和逻辑)

    ### 📖 详细内容/教程
    (列出细节)
    """

    return call_gemini_with_retry(model, final_input, final_prompt)


def call_gemini_with_retry(model, text, task_type):
    """
    封装的通用调用函数，带重试逻辑
    """
    # 在发起网络请求前，临时设置本地代理
    if config.LOCAL_PROXY:
        os.environ["http_proxy"] = config.LOCAL_PROXY
        os.environ["https_proxy"] = config.LOCAL_PROXY

    if task_type == "simple":
        prompt = "你是一个专业的技术与内容分析师。请根据输入的内容，用中文输出一份简报（一句话总结、核心观点、详细细节）。内容如下：\n\n"
    else:
        prompt = task_type  # 传入自定义 prompt

    max_retries = 3
    for i in range(max_retries):
        try:
            response = model.generate_content(
                prompt + "\n\n" + text,
                request_options={"timeout": 120}
            )
            return response.text
        except exceptions.ResourceExhausted:
            wait_time = (i + 1) * 30
            print(f"      [!] 触发限额，等待 {wait_time} 秒后重试...")
            time.sleep(wait_time)
        except Exception as e:
            return f"调用出错: {str(e)}"
        finally:
            # 结束后清除环境变量，保持环境纯净
            if "http_proxy" in os.environ: del os.environ["http_proxy"]
            if "https_proxy" in os.environ: del os.environ["https_proxy"]
    return "多次尝试后 API 依然拒绝请求。"


