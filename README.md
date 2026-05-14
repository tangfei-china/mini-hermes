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

## Web 可视化版本

这个项目现在包含一个本地 Web 版本，可以用页面对话，并实时查看 agent 的执行过程：

```bash
uv run mini-hermes-web
```

然后打开：

```text
http://127.0.0.1:8787
```

Web 页面支持：

- 多轮对话，同一个 session 会保留上下文。
- 真实模型流式输出，回答会边生成边显示。
- 工具调用可视化，例如 `read_file`、`list_files`、`run_shell`。
- 右侧 Trace 面板展示 `messages`、模型响应、工具调用、工具结果和最终回答。
- `New Chat` 可以创建新的会话。
- `Fake` 模式可以不使用 API key，直接学习工具调用流程。

Web 和 CLI 使用同一套 `MiniAgent.run_turn()` 对话循环，不是两套实现。

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
| `get_tool_schemas()` | `model_tools.get_tool_definitions()` |
| `_execute_tool_call()` | `_execute_tool_calls()` |
| `dispatch()` | `handle_function_call()` + `registry.dispatch()` |
