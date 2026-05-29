"""chat-cc-bot 跨渠道共享核心。

各渠道（飞书 webhook / 飞书 WS / 微信桥）复用这里的：
  - config   配置加载(.env 权威) + prompt 构造
  - runner   run_claude(cli/sdk 可切换引擎) + 单飞 Slots + 会话 Sessions
  - security 白名单 fail-closed
  - dedup    事件幂等去重
  - chunking 长消息分段
"""
