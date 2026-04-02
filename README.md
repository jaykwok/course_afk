# 自用自动化挂课

基于 Playwright 浏览器自动化 + 阿里云百炼 AI 大模型的在线学习平台自动挂课工具。

## 环境准备

### 依赖安装

```bash
pip install -r requirements.txt
playwright install chromium
```

### 配置 .env 文件

在项目根目录创建 `.env` 文件，配置以下内容：

```env
# OpenAI兼容模式的API地址
DASHSCOPE_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
# 阿里云百炼 API Key
DASHSCOPE_API_KEY=你的API Key
# 模型名称
MODEL_NAME=qwen3.6-plus

# 2get_urls.py 主题学习页面链接
TOPIC_URL="主题学习页面的完整URL"
# 点击按钮获取链接.py 起始页面链接
START_URL="点击获取链接的起始页面URL"
```

> 链接变动时只需修改 `.env` 文件，无需改动代码，`.env` 已被 `.gitignore` 忽略。

## 运行步骤

### 1. 获取 Cookie

```bash
python 1get_cookie.py
```

启动浏览器后扫码登录，登录成功后自动保存 Cookie 到 `cookies.json`。

### 2. 获取学习链接（二选一）

**方式一：自动解析主题页面**

```bash
python 2get_urls.py
```

从 `.env` 中配置的 `TOPIC_URL` 页面解析所有课程链接，保存到以页面标题命名的文本文件中。

**方式二：手动点击获取**

```bash
python 点击按钮获取链接.py
```

从 `.env` 中配置的 `START_URL` 页面启动，手动点击课程按钮，自动捕获弹出页面的链接并保存到 `学习链接_点击按钮.txt`。

### 3. 自动挂课

将需要学习的链接粘贴到 `学习链接.txt` 文件中，然后运行：

```bash
python 3afk.py
```

自动处理视频（等待播放完毕）、文档（等待进度同步）等课程类型，考试链接保存到 `学习课程考试链接.txt`。

### 4. AI 自动考试

```bash
python 4ai_examination.py
```

读取 `学习课程考试链接.txt`，通过 AI 大模型自动答题。考试未通过或遇到无法处理的题型时，链接写入 `人工考试链接.txt`。

> 限定考试剩余次数 <=3 次的自动转入人工考试，避免次数超限。

### 5. 人工考试

```bash
python 5examination.py
```

逐个打开 `人工考试链接.txt` 中的链接，等待手动完成考试。
