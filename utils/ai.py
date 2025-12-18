import google.generativeai as genai
import config
import time
import os

if config.PROXY_URL:
    print(f"  [DEBUG] 正在设置 Gemini 代理: {config.PROXY_URL}")
    os.environ['http_proxy'] = config.PROXY_URL
    os.environ['https_proxy'] = config.PROXY_URL
    os.environ['HTTP_PROXY'] = config.PROXY_URL
    os.environ['HTTPS_PROXY'] = config.PROXY_URL
# 初始化 Gemini
genai.configure(api_key=config.GEMINI_API_KEY)


def summarize_content(content_data):
    """
    调用 Gemini 进行总结
    content_data: 字典, 包含 type ('text' 或 'audio') 和对应内容
    """
    model = genai.GenerativeModel('gemini-2.0-flash')

    prompt = """
    你是一个专业的技术与内容分析师。请根据输入的内容（视频字幕或音频），用中文输出一份简报。

    输出格式要求 (Markdown):
    ### 📝 一句话总结
    (50字以内概括核心)

    ### 💡 核心观点
    * (列出3-5个关键点)

    ### 📖 详细内容/教程
    (如果是教程，列出步骤；如果是新闻，列出细节)
    """

    try:
        if content_data['type'] == 'text':
            # 纯文本模式
            print("  [*] Gemini 正在分析文本...")
            response = model.generate_content(prompt + "\n\n原始内容:\n" + content_data['content'])
            return response.text

        elif content_data['type'] == 'audio':
            # 音频模式 (多模态)
            file_path = content_data['path']
            print(f"  [*] 上传音频至 Gemini: {file_path}")

            # 1. 上传文件
            audio_file = genai.upload_file(path=file_path, display_name="Video Audio")

            # 2. 等待文件处理完成 (大文件可能需要几秒)
            while audio_file.state.name == "PROCESSING":
                time.sleep(2)
                audio_file = genai.get_file(audio_file.name)

            if audio_file.state.name == "FAILED":
                raise ValueError("Gemini 文件处理失败")

            print("  [*] Gemini 正在听取并分析音频...")
            response = model.generate_content([prompt, audio_file])

            # 3. 清理：删除 Gemini 云端文件 (虽然会自动过期，但主动删是个好习惯)
            # 注意：本地文件在 main.py 中清理
            genai.delete_file(audio_file.name)

            return response.text

    except Exception as e:
        return f"AI 分析过程中出错: {str(e)}"
    return "无法处理的内容"