import requests
import json
import re
import config


class WeChatNotifier:
    def __init__(self):
        self.webhook_url = config.WECOM_WEBHOOK_URL

    def _clean_markdown_to_text(self, text):
        """
        将 Markdown 转换为适合在普通微信查看的纯文本
        """
        if not text: return ""

        # 1. 去除标题 (#, ##, ###)
        text = re.sub(r'#+\s', '', text)

        # 2. 去除加粗 (**text**) -> text
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)

        # 3. 处理链接 [文本](链接) -> 文本: 链接
        text = re.sub(r'\[(.*?)\]\((.*?)\)', r'\1: \2', text)

        # 4. 去除多余空行
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text.strip()

    def _push_payload(self, content, msg_type="markdown"):
        """
        底层发送逻辑 (即你提供的代码)
        """
        if not self.webhook_url:
            print("⚠️ 未配置 Webhook，跳过推送。")
            return

        headers = {"Content-Type": "application/json"}
        data = {}

        if msg_type == "markdown":
            # 只有企业微信APP能看到渲染效果
            data = {
                "msgtype": "markdown",
                "markdown": {"content": content}
            }
        else:
            # 🔥 降级模式：清洗 markdown 为纯文本
            clean_content = self._clean_markdown_to_text(content)
            data = {
                "msgtype": "text",
                "text": {
                    "content": clean_content
                    # 可以在这里 @all
                    # "mentioned_mobile_list": ["@all"]
                }
            }

        try:
            response = requests.post(self.webhook_url, headers=headers, data=json.dumps(data))
            if response.status_code != 200:
                print(f"  [X] 推送失败: {response.text}")
            else:
                print("  [v] 推送成功")
        except Exception as e:
            print(f"  [X] 网络错误: {e}")

    def send(self, title, summary, link, author):
        """
        高级接口：组装内容并发送
        """
        # 组装 Markdown 内容
        # 注意：企微 Markdown 不支持 HTML 标签，只能用特定语法
        content = (
            f"**📺 {title}**\n"
            f"> UP主: {author}\n"
            f"{summary}\n\n"
            f"[👉 点击观看视频]({link})"
        )

        # 策略选择：
        # 如果你希望在普通微信也能看到内容，必须用 msg_type="text"。
        # 但这样会丢失 Markdown 格式（如加粗、列表）。
        # 建议：默认用 Markdown，如果发现经常在微信看，可以手动改为 "text"

        # 此处调用底层发送
        self._push_payload(content, msg_type="text")