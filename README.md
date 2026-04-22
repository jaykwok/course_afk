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

建议先复制 `.env.example` 为 `.env`，然后填写你自己的真实参数。当前只需要保留 AI 相关配置：

```env
DASHSCOPE_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
DASHSCOPE_API_KEY=你的API Key
MODEL_NAME=qwen3.6-plus
AI_REQUEST_TYPE=responses
AI_ENABLE_WEB_SEARCH=0
AI_ENABLE_THINKING=0
# AI_REASONING_EFFORT=medium
```

AI 自动考试支持两种百炼 OpenAI 兼容请求方式：

- `AI_REQUEST_TYPE=responses`：走 `Responses API`
- `AI_REQUEST_TYPE=chat`：走 `Chat Completions API`

如果某个模型只支持其中一种，就把 `.env` 里的 `AI_REQUEST_TYPE` 切到对应值即可。

默认不启用联网搜索；如果希望模型在拿不准时自行补检索，可以在 `.env` 中额外加入：

```env
AI_ENABLE_WEB_SEARCH=1
```

联网搜索在两种请求方式里都会保留：

- `responses`：通过 `tools=[{"type": "web_search"}]`
- `chat`：通过 `extra_body={"enable_search": True}`

AI 请求现在统一改为流式调用，兼容只支持流式输出的模型。程序仍然只提取最终答案文本用于作答，不会把中间事件直接当作答案。

思考模式配置：

- `AI_ENABLE_THINKING=1`：统一开启思考模式
- `AI_REASONING_EFFORT=none|minimal|low|medium|high`：仅 `responses` 请求使用，优先级高于 `AI_ENABLE_THINKING`

具体规则：

- `AI_REQUEST_TYPE=responses`
  - 优先使用 `AI_REASONING_EFFORT`
  - 未设置 `AI_REASONING_EFFORT` 且 `AI_ENABLE_THINKING=1` 时，传 `extra_body={"enable_thinking": True}`
- `AI_REQUEST_TYPE=chat`
  - `AI_ENABLE_THINKING=1` 时，传 `extra_body={"enable_thinking": True}`
  - 当前不会把 `AI_REASONING_EFFORT` 传给 `chat`

可选浏览器配置：

```env
# Windows 默认就是这组配置，可不写
BROWSER_TYPE=chromium
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

- `DEBUG_MODE=1`：把控制台日志提升到 `DEBUG`，便于排查问题
- `SUPPRESS_STARTUP_BANNER=1`：只隐藏启动横幅，不影响其他日志输出
- `AI_ENABLE_WEB_SEARCH=0|1`：是否为 AI 考试开启联网搜索工具；默认关闭
- `AI_REQUEST_TYPE=responses|chat`：切换百炼 OpenAI 兼容 `Responses` 或 `Chat Completions` 请求方式
- `AI_ENABLE_THINKING=0|1`：是否开启思考模式；默认关闭
- `AI_REASONING_EFFORT=none|minimal|low|medium|high`：仅 `responses` 请求使用，优先级高于 `AI_ENABLE_THINKING`

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

## 推荐流程

1. 登录凭证不存在或超过 28 天时，统一入口会直接提示重新登录。
2. `学习链接.txt` 为空时，先选择“手动选择学习课程”。
3. 有学习链接后即可开始挂课。
4. 挂课结束后，如果没有考试链接，本次流程直接结束。
5. 如果生成了考试链接，继续进入 AI 自动考试。

## 手动选择学习课程

如果你没有现成的学习链接，可以在菜单里选择“手动选择学习课程”。

你可以直接粘贴两类链接：

1. 入口链接
2. 学习专区链接

如果检测到学习专区链接，程序会先询问你：

1. 全部学习：自动解析专区里的课程/主题链接并写入 `学习链接.txt`
2. 手动选择学习模块：照常打开页面，由你自己点击课程

对于需要手动处理的页面，你只需要：

1. 进入对应课程页面
2. 如有需要先报名
3. 点击“开始学习”

点击后新打开的真实学习链接会自动记录到 `学习链接.txt`。

输入支持多行混合文本，程序会自动提取其中的 URL 并去重。结束输入时，输入单独一行 `END` 即可，大小写都可以。

## 主要输出文件

- `cookies.json`：浏览器登录凭证
- `credential_meta.json`：登录凭证时间和账号信息
- `学习链接.txt`：待挂课的学习链接
- `学习课程考试链接.txt`：挂课后识别出的考试链接
- `人工考试链接.txt`：需要手动处理的考试链接
- `log.txt`：完整运行日志
