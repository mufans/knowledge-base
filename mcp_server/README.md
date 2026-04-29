# Knowledge Base MCP Server

搜索知识库的 MCP Server，供 CC、OpenClaw、OpenCode 等 agent 工具使用。

## 工具列表

| Tool | 说明 |
|------|------|
| `search_kb` | 全文搜索知识库，返回匹配的 wiki 页面及上下文高亮 |
| `get_entity` | 按 name 获取单个 wiki 页面详情（sections、related links） |
| `list_recent` | 列出最近更新的高分页面 |

## 安装 & 运行

```bash
cd mcp_server
uv run python server.py
```

使用 stdio 传输模式，启动后等待 JSON-RPC 输入。

## 配置示例

### Claude Code (`.claude/settings.json`)
```json
{
  "mcpServers": {
    "knowledge": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/Users/liujun/Nutstore Files/我的坚果云/knowledge/mcp_server",
        "python",
        "server.py"
      ]
    }
  }
}
```

> **注意**: Claude Code 的 stdio MCP 不支持 `cwd` 字段，需使用 `uv run --directory` 来指定工作目录。

### OpenClaw (`mcporter`)
```bash
mcporter add knowledge -s stdio -- uv run python server.py \
  --cwd "/Users/liujun/Nutstore Files/我的坚果云/knowledge/mcp_server"
```

### OpenCode / Cursor
```json
{
  "mcpServers": {
    "knowledge": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/Users/liujun/Nutstore Files/我的坚果云/knowledge/mcp_server",
        "python",
        "server.py"
      ]
    }
  }
}
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `KNOWLEDGE_BASE_PATH` | `/Users/liujun/Nutstore Files/我的坚果云/knowledge` | 知识库根目录 |

## 依赖

- Python 3.10+
- `mcp` (官方包)
- `rg` (ripgrep，用于全文搜索)
