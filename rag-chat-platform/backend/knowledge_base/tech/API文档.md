# API 文档

问答接口为 POST /api/chat。请求体包含 message 和 config.api_key。

索引接口为 POST /api/index。上传接口为 POST /api/upload，必须带 department 字段。

服务默认监听 8000 端口。部署时先启动后端，再启动前端开发服务器。
