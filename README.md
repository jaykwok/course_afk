# 中国电信挂课统一入口

基于 Playwright + 阿里云百炼 AI 的在线学习自动化工具。

当前项目已经整理为统一入口版本，不再依赖旧的编号脚本；推荐直接使用 `run.bat` 或 `python launcher.py`。

## 环境准备

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

默认配置会在 Windows 上直接调用系统自带的 Edge（`BROWSER_TYPE=chromium`，`BROWSER_CHANNEL=msedge`），因此通常不需要再执行 `playwright install chromium`。

如果你改成其他浏览器，再按下面补安装：

- `BROWSER_TYPE=chromium` 且 `BROWSER_CHANNEL=chrome`：使用本机 Chrome，一般也不需要额外安装 Playwright Chromium
- `BROWSER_TYPE=chromium` 且不设置 `BROWSER_CHANNEL`：使用 Playwright 自带 Chromium，需要执行 `playwright install chromium`
- `BROWSER_TYPE=webkit`：使用 Playwright WebKit（Safari 同内核，不是系统 Safari），需要执行 `playwright install webkit`
- `BROWSER_TYPE=firefox`：需要执行 `playwright install firefox`

建议先复制 `.env.example` 为 `.env`，然后填写你自己的真实参数。最少需要配置 AI 相关参数；浏览器和日志参数按需启用：

```env
OPENAI_COMPLETION_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
OPENAI_COMPLETION_API_KEY=你的API Key
MODEL_NAME=qwen3.6-plus
# AI 请求类型（可选值：chat / responses）
AI_REQUEST_TYPE=responses
# 可选：是否为 AI 考试启用联网搜索（0/1）；联网搜索，默认关闭
AI_ENABLE_WEB_SEARCH=0
# 可选：是否开启思考模式（0/1），默认关闭
AI_ENABLE_THINKING=0
# 可选值：none / minimal / low / medium / high
# AI_REASONING_EFFORT=medium
```

AI 自动考试支持两种百炼 OpenAI 兼容请求方式：

- `AI_REQUEST_TYPE=chat`：走 `Chat Completions API`
- `AI_REQUEST_TYPE=responses`：走 `Responses API`

如果某个模型只支持其中一种，就把 `.env` 里的 `AI_REQUEST_TYPE` 切到对应值即可。

`AI_ENABLE_WEB_SEARCH` 使用 `0/1` 开关，默认关闭。如果希望模型在拿不准时自行补检索，可以在 `.env` 中额外加入：

```env
AI_ENABLE_WEB_SEARCH=1
```

联网搜索在两种请求方式里都会保留：

- `responses`：通过 `tools=[{"type": "web_search"}]`
- `chat`：通过 `extra_body={"enable_search": True}`

AI 请求现在统一改为流式调用，兼容只支持流式输出的模型。程序仍然只提取最终答案文本用于作答，不会把中间事件直接当作答案。

思考模式配置：

- `AI_ENABLE_THINKING=0|1`：是否开启思考模式，默认关闭
- `AI_REASONING_EFFORT=none|minimal|low|medium|high`：仅 `responses` 请求使用，优先级高于 `AI_ENABLE_THINKING`

具体规则：

- `AI_REQUEST_TYPE=responses`
  - 优先使用 `AI_REASONING_EFFORT`
  - 未设置 `AI_REASONING_EFFORT` 且 `AI_ENABLE_THINKING=1` 时，传 `extra_body={"enable_thinking": True}`
- `AI_REQUEST_TYPE=chat`
  - 总是显式传 `extra_body={"enable_thinking": true|false}`，避免兼容接口使用服务端默认思考模式导致正文为空
  - 当前不会把 `AI_REASONING_EFFORT` 传给 `chat`

可选浏览器配置：

```env
# Windows 默认就是这组配置，可不写
# BROWSER_TYPE 可选值：chromium / webkit / firefox
BROWSER_TYPE=chromium
# BROWSER_CHANNEL 常用可选值：msedge / chrome / 空值
BROWSER_CHANNEL=msedge

# 如果以后改用 Chrome
# BROWSER_TYPE=chromium
# BROWSER_CHANNEL=chrome

# 如果以后改用 WebKit（Safari 同内核）
# BROWSER_TYPE=webkit
# BROWSER_CHANNEL=
```

学习专区链接、入口链接不再写在 `.env` 中；需要时直接在统一入口的“手动选择学习课程”里粘贴即可。

可选环境变量：

- `AI_REQUEST_TYPE=chat|responses`：切换百炼 OpenAI 兼容 `Chat Completions` 或 `Responses` 请求方式
- `AI_ENABLE_WEB_SEARCH=0|1`：是否为 AI 考试启用联网搜索；联网搜索，默认关闭
- `AI_ENABLE_THINKING=0|1`：是否开启思考模式，默认关闭
- `AI_REASONING_EFFORT=none|minimal|low|medium|high`：仅 `responses` 请求使用，优先级高于 `AI_ENABLE_THINKING`
- `BROWSER_TYPE=chromium|webkit|firefox`：浏览器类型；Windows 默认使用 `chromium`
- `BROWSER_CHANNEL=msedge|chrome|空值`：浏览器通道；通常只在 `chromium` 下使用
- `DEBUG_MODE=0|1`：是否输出 DEBUG 日志
- `SUPPRESS_STARTUP_BANNER=0|1`：是否隐藏启动横幅

## 启动方式

- 双击 `run.bat`（优先使用当前目录的 `.venv\Scripts\python.exe`；如果没有，则回退到 `PATH` 里的 `python`）
- 或在已激活虚拟环境后执行 `python launcher.py`

## 统一入口能力

- 统一的主菜单、状态面板、结果汇总和等待进度展示
- 自动检查登录凭证是否存在，以及是否超过 28 天
- 展示当前登录账号
- 手动选择学习课程并自动记录真实学习链接
- 自动挂课
- AI 自动考试
- 人工考试兜底

## 浏览器关闭行为

- 挂课时会保留一个 `https://www.mylearning.cn/p5/index.html` 首页标签页作为常驻主控页。
- 对于直接学习的 `course` 链接，手动关闭当前课程标签页会跳过当前课程，并继续下一个学习链接。
- 对于 `subject` 页面里弹出的课程标签页，手动关闭当前课程标签页会跳过当前课程，并继续同一主题下一个课程。
- 手动关闭整个浏览器窗口会直接退出程序。
- 通过 `Ctrl+C` 终止时，程序也会直接退出，且不会保存当前和剩余待处理学习链接。
- AI 自动考试和人工考试批处理时，关闭单个考试标签页会跳过当前考试并继续下一条；关闭整个浏览器窗口或通过 `Ctrl+C` 终止时，会把当前和剩余考试链接写回对应队列后退出。

## 推荐流程

1. 登录凭证不存在或超过 28 天时，统一入口会直接提示重新登录。
2. `课程链接.txt` 为空时，先选择“手动选择学习课程”。
3. 有学习链接后即可开始挂课。
4. 挂课结束后，如果没有考试链接，本次流程直接结束。
5. 如果生成了考试链接，继续进入 AI 自动考试。

进入 AI 自动考试前，程序会询问一次“是否自动交卷”，默认 `Y`。

如果考试过程中检测到填空题或其他无法可靠自动作答的题目，程序会自动切换为手动交卷，并把需要人工处理的链接继续保留到对应文件中。

## 手动选择学习课程

如果你没有现成的学习链接，可以在菜单里选择“手动选择学习课程”。

你可以直接粘贴两类链接：

1. 入口链接
2. 学习专区链接

如果检测到学习专区链接，程序会先询问你：

1. 全部学习：自动解析专区里的课程/主题链接并写入 `课程链接.txt`
2. 手动选择学习模块：照常打开页面，由你自己点击课程

对于需要手动处理的页面，你只需要：

1. 进入对应课程页面
2. 如有需要先报名
3. 点击“开始学习”

点击后新打开的真实学习链接会自动记录到 `课程链接.txt`。

输入支持多行混合文本，程序会自动提取其中的 URL 并去重。结束输入时，输入单独一行 `END` 即可，大小写都可以。

## 主要输出文件

- `cookies.json`：浏览器登录凭证
- `credential_meta.json`：登录凭证时间和账号信息
- `课程链接.txt`：待挂课的学习链接
- `剩余未看课程链接.txt`：中断后保留下来的剩余课程链接
- `考试链接.json`：待 AI 自动考试的考试链接队列，并记录每条链接已未通过的 AI 模型配置列表（模型名、请求方式、联网搜索、思考模式、推理强度）
- `人工考试链接.txt`：需要手动处理的考试链接
- `考试次数超限链接.txt`：因考试次数限制而跳过的考试链接
- `无权限资源链接.txt`：无权限访问的学习资源链接
- `不合规链接.txt`：不符合预期格式的链接
- `URL类型链接.txt`：识别为 URL 学习类型的链接
- `h5课程类型链接.txt`：识别为 H5 课程类型的链接
- `调研类型链接.txt`：识别为调研类型的链接
- `未知类型链接.txt`：暂未识别出具体学习类型的链接
- `非课程及考试类学习类型链接.txt`：非课程/考试类的其他学习链接
- `log.txt`：完整运行日志

`考试链接.json` 示例：

```json
[
  {
    "url": "https://kc.zhixueyun.com/#/study/course/detail/...",
    "ai_failed_model_configs": [
      {
        "model": "qwen3.6-max-preview",
        "request_type": "chat",
        "web_search": false,
        "thinking": false,
        "reasoning_effort": null
      }
    ]
  }
]
```

AI 自动考试跳过逻辑按整组配置匹配：同一链接如果当前模型名、`AI_REQUEST_TYPE`、`AI_ENABLE_WEB_SEARCH`、`AI_ENABLE_THINKING`、`AI_REASONING_EFFORT` 都已记录为未通过，会提示更换模型或人工考试并跳过；只要其中一项不同，例如开启联网搜索、开启思考模式、切换请求方式或调整推理强度，就会继续尝试考试。如果再次未通过，会把新的配置追加到该链接的 `ai_failed_model_configs`。
