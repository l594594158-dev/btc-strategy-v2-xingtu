# HEARTBEAT.md

```markdown
# 检查项：微信通知队列

每次心跳检查是否有待发送的微信通知：
- 文件: /root/.openclaw/workspace/btc-strategy-task/databases/notify_queue.json
- 如果有待发送的通知（sent=false），立即使用 message 工具发送到微信
- 发送成功后更新 sent=true
```

