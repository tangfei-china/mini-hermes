# Mini Hermes Agent

一个很小的 Hermes 学习版，只保留核心闭环：

```text
用户输入
  -> 发送 messages + tools 给模型
  -> 模型返回 tool_calls
  -> 执行工具
  -> 把 tool result 放回 messages
  -> 再次调用模型
  -> 输出最终回答
```

## 运行

```bash
cd mini-hermes-agent
uv sync
uv run python -m unittest -v
```

## 提交身份

这个仓库的提交作者应使用：

```bash
git config user.name "tangfei-china"
git config user.email "tangfeizz@outlook.com"
```

提交前可以用下面命令确认，避免把其他全局 Git 身份写进历史：

```bash
git config user.name
git config user.email
git log -1 --format='%an <%ae> | %cn <%ce>'
```

## Web 可视化版本

这个项目现在包含一个本地 Web 版本，可以用页面对话，并实时查看 agent 的执行过程：

```bash
uv run mini-hermes-web
```

如果 `8787` 已被占用，可以换端口：

```bash
MINI_HERMES_WEB_PORT=8788 uv run mini-hermes-web
```

然后打开：

```text
http://127.0.0.1:8787
```

Web 页面支持：

- 多轮对话，同一个 session 会保留上下文。
- 真实模型流式输出，回答会边生成边显示。
- 工具调用可视化，例如 `read_file`、`list_files`、`run_shell`。
- Skills 自动加载和可视化：模型可通过 `skills_list` / `skill_view` 自己选择 skill，右侧会显示本轮实际激活的 skill。
- Skills 管理页：顶部 `Skills` tab 可以新增、编辑、删除自定义 skill，也可以上传新的 `SKILL.md` 导入到 `skills/custom/`。
- 右侧 Trace 面板展示 `messages`、模型响应、工具调用、工具结果和最终回答。
- `New Chat` 可以创建新的会话。
- `Fake` 模式可以不使用 API key，直接学习工具调用流程。

Web 和 CLI 使用同一套 `MiniAgent.run_turn()` 对话循环，不是两套实现。

## Skills

Skills 放在 `skills/**/SKILL.md`，格式参考 Hermes：顶部是简单 frontmatter，正文是要注入给 agent 的指导内容。

查看当前可用 skills：

```bash
uv run mini-hermes --list-skills
```

Skills 默认自动启用：`MiniAgent` 会把 skill catalog 放进系统提示，并把 `skills_list` / `skill_view` 暴露成工具；模型判断相关时会先调用 `skill_view` 加载完整指导内容。加载后，trace 里会发出 `skills_loaded` 事件，Web 右侧 `Active Skills` 会显示本轮实际使用的 skill。

Web 顶部的 `Skills` tab 可以直接维护 skills：

- 选择一个 skill 后会读取它的 `SKILL.md`。
- 修改后点击 `Save` 会写回原文件。
- 上传一个 Markdown 文件会按 frontmatter 的 `name` 生成 slug，并保存到 `skills/custom/<slug>/SKILL.md`。
- 删除只允许删除 `skills/custom/` 下的自定义 skill，避免误删内置示例 skill。

## 真实模型配置

使用真实 OpenAI-compatible 接口前，复制并编辑 `.env`：

```bash
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL
```

CLI 会默认读取当前目录的 `.env`。也可以继续使用 shell 环境变量，已有环境变量会优先于 `.env`。

## CLI 版本

单轮执行：

```bash
uv run mini-hermes "看一下 README.md 里写了什么"
```

多轮对话：

```bash
uv run mini-hermes --chat "你好"
```

在 `--chat` 模式中：

- 输入 `/reset` 清空当前上下文。
- 输入 `/exit` 或 `/quit` 退出。

无 API key 学习工具流程：

```bash
uv run mini-hermes --fake "读一下 README.md"
```

## 推荐断点

1. `mini_hermes/agent.py:MiniAgent.run()`  
   看整个对话循环。

2. `mini_hermes/agent.py:_build_api_kwargs()`  
   看发给模型的 `messages` 和 `tools`。

3. `mini_hermes/agent.py:_call_model()`  
   看模型调用返回值。

4. `mini_hermes/agent.py:_execute_tool_call()`  
   看模型选了哪个工具、参数是什么。

5. `mini_hermes/tools.py:ToolRegistry.dispatch()`  
   看工具名如何分发到真实 Python 函数。

## 和 Hermes 的对应关系

| Mini Hermes | Hermes |
|---|---|
| `MiniAgent.run()` | `AIAgent.run_conversation()` |
| `ToolRegistry` | `tools/registry.py` |
| `SkillLoader` + `skills_list` / `skill_view` | `tools/skills_tool.py` + `agent/skill_commands.py` 的轻量学习版 |
| `get_tool_schemas()` | `model_tools.get_tool_definitions()` |
| `_execute_tool_call()` | `_execute_tool_calls()` |
| `dispatch()` | `handle_function_call()` + `registry.dispatch()` |
