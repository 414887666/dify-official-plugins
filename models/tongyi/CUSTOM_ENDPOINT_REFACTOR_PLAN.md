# 通义插件公司 AI 网关改造方案

## 1. 背景

当前通义插件的普通模型调用使用 DashScope SDK，默认连接阿里云官方 DashScope Endpoint；LLM 文档上传场景使用 OpenAI-compatible `/files` 接口，当前代码中也硬编码了官方 compatible-mode Endpoint。

企业环境中需要通过公司 AI 网关访问模型服务。网关侧可能为 DashScope 协议和 OpenAI-compatible 协议创建不同 API，也可能使用同一个 base URL 和 key 承载两种协议。因此插件需要允许用户显式填写网关地址，并为 compatible 文件上传提供可选覆盖能力。

## 2. 改造目标

将通义插件改造成显式接入公司 AI 网关：

- `dashscope_endpoint_url` 必填，用于普通 DashScope SDK 调用。
- `compatible_endpoint_url` 选填，用于 LLM 文档上传；不填时复用 `dashscope_endpoint_url`。
- `compatible_api_key` 选填，用于 LLM 文档上传；不填时复用 `dashscope_api_key`。
- 不再依赖官方 HTTP Endpoint 作为默认 fallback。
- Speech-to-Text 不新增独立字段，复用 `dashscope_endpoint_url` 和 `dashscope_api_key`。

## 3. 字段设计

在 `models/tongyi/provider/tongyi.yaml` 的 `provider_credential_schema` 和 `model_credential_schema` 中新增字段。

### `dashscope_api_key`

必填。默认用于所有通义调用。

### `dashscope_endpoint_url`

必填。用于 DashScope SDK 调用。

覆盖范围：

- 普通 LLM 文本对话
- 图片/多模态 LLM 调用
- Text Embedding
- Rerank
- TTS
- Speech-to-Text

### `compatible_endpoint_url`

选填。用于 OpenAI-compatible API 调用，主要覆盖 LLM 文档上传场景。

不填写时，插件使用 `dashscope_endpoint_url` 作为 compatible endpoint，但该 fallback 地址必须是 `http://` 或 `https://`。

### `compatible_api_key`

选填。用于 OpenAI-compatible 文件上传调用。

不填写时，插件使用 `dashscope_api_key`。

## 4. 执行规则

普通模型调用：

```text
endpoint = dashscope_endpoint_url
key      = dashscope_api_key
```

LLM 文档上传：

```text
endpoint = compatible_endpoint_url or dashscope_endpoint_url
key      = compatible_api_key or dashscope_api_key
```

其中 `endpoint` 必须是 HTTP URL。如果 `dashscope_endpoint_url` 被配置为 `ws://` 或 `wss://` 且没有填写 `compatible_endpoint_url`，文档上传应校验失败。

文档上传完成后，插件将返回的 `file_id` 转为 `fileid://xxx`，再继续通过 DashScope SDK 调用 LLM。

Speech-to-Text：

```text
endpoint = dashscope_endpoint_url
key      = dashscope_api_key
```

Speech-to-Text 不使用 `compatible_endpoint_url` 或 `compatible_api_key`。如果公司网关使用同一个 URL 承载 HTTP DashScope 调用和 ASR WebSocket/流式调用，则插件侧只需要配置同一个 `dashscope_endpoint_url`。

如果公司网关使用同一个 URL 和 key 同时承载 DashScope 协议和 OpenAI-compatible 协议，则用户只需要填写：

```text
dashscope_endpoint_url
dashscope_api_key
```

如果网关侧为两种协议提供不同 API 或不同 key，则用户可以额外填写：

```text
compatible_endpoint_url
compatible_api_key
```

## 5. 实现大纲

### Provider 配置

修改 `models/tongyi/provider/tongyi.yaml`：

- 在 provider 级凭据中新增 `dashscope_endpoint_url`、`compatible_endpoint_url`、`compatible_api_key`。
- 在 customizable model 级凭据中新增相同字段。
- 移除或弱化 `use_international_endpoint`，避免和必填的公司网关 endpoint 产生歧义。

### 公共 Helper

修改 `models/tongyi/models/_common.py`：

- 新增 `get_dashscope_base_address(credentials)`。
- 新增 `get_compatible_base_url(credentials)`。
- 新增 `get_compatible_api_key(credentials)`。
- Endpoint 做标准化：去除首尾空格、去掉末尾 `/`。
- `dashscope_endpoint_url` 允许 `http://`、`https://`、`ws://`、`wss://`，因为 Speech-to-Text 会复用该字段。
- `compatible_endpoint_url` 仅允许 `http://` 或 `https://`，因为 OpenAI-compatible `/files` 调用是 HTTP API。
- `get_ws_base_address(credentials)` 改为复用 `get_dashscope_base_address(credentials)`，不再回退官方 WebSocket Endpoint。

### LLM

修改 `models/tongyi/models/llm/llm.py`：

- 普通 LLM 调用使用 `get_dashscope_base_address(credentials)`。
- `_upload_file_to_tongyi()` 使用 `get_compatible_base_url(credentials)` 和 `get_compatible_api_key(credentials)`。
- 移除硬编码的官方 compatible-mode Endpoint。

### Embedding、Rerank、TTS

这些模型类型已经通过公共 HTTP base address helper 获取 endpoint。公共 helper 改造后，它们会自动使用 `dashscope_endpoint_url`。

### Speech-to-Text

修改 `models/tongyi/models/speech2text/speech2text.py` 依赖的公共 helper 行为：

- Speech-to-Text 仍调用 `get_ws_base_address(credentials)`。
- `get_ws_base_address(credentials)` 内部复用 `dashscope_endpoint_url`。
- 不新增 `dashscope_ws_endpoint_url`。
- 不使用 `compatible_endpoint_url`。

注意：DashScope ASR SDK 原本期望 WebSocket endpoint。若公司网关提供的是普通 HTTP base URL，则需要网关侧负责将该入口正确转发到 ASR WebSocket/流式后端；否则 Speech-to-Text 可能失败。

## 6. 测试计划

最小验证场景：

- 缺少 `dashscope_endpoint_url` 时，凭据校验失败。
- `compatible_endpoint_url` 为空时，文档上传复用 `dashscope_endpoint_url`。
- `compatible_endpoint_url` 为空且 `dashscope_endpoint_url` 是 WebSocket URL 时，文档上传 endpoint 校验失败。
- `compatible_api_key` 为空时，文档上传复用 `dashscope_api_key`。
- `dashscope_endpoint_url` 不是 `http://`、`https://`、`ws://` 或 `wss://` 时，凭据校验失败。
- `compatible_endpoint_url` 不是 `http://` 或 `https://` 时，凭据校验失败。
- 普通 LLM 调用使用 `dashscope_endpoint_url`。
- LLM 文档上传使用 compatible fallback 规则。
- Speech-to-Text 使用 `dashscope_endpoint_url`，且不读取 compatible 字段。
- Provider 级凭据和自定义模型凭据均可配置新字段。

推荐测试：

- 单元测试覆盖 endpoint/key helper。
- mock `Generation.call()` 验证普通 LLM 的 `base_address`。
- mock `OpenAI(...)` 和 `files.create()` 验证文档上传的 endpoint/key。
- mock `Recognition.call()` 验证 Speech-to-Text 的 `base_address` 使用 `dashscope_endpoint_url`。
- 使用公司 AI 网关进行普通文本对话、文档上传和 Speech-to-Text 联调。

## 7. 版本维护方案

使用 fork 分支维护企业定制版本：

```text
main
  跟随官方 upstream/main

feature/tongyi-custom-endpoint
  保存通义公司 AI 网关改造
```

官方更新后的同步流程：

```bash
git fetch upstream
git checkout main
git merge --ff-only upstream/main
git checkout feature/tongyi-custom-endpoint
git merge main
```

如出现冲突，优先检查通义插件相关文件，解决后重新执行测试，再发布企业定制插件版本。
