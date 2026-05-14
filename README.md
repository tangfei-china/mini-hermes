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

使用真实 OpenAI-compatible 接口：

```bash
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL
uv run mini-hermes "看一下 README.md 里写了什么"
```

CLI 会默认读取当前目录的 `.env`。也可以继续使用 shell 环境变量，已有环境变量会优先于 `.env`。

无 API key 学习工具流程：

```bash
uv run mini-hermes --fake "读一下 README.md"
```

启动 Web 可视化页面：

```bash
uv run mini-hermes-web
```

然后打开 `http://127.0.0.1:8787`。页面会默认读取 `.env`，使用真实模型执行，并展示每一步 `messages`、模型响应、工具调用和工具结果。

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
