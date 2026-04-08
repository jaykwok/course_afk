# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

基于 Playwright + 阿里云百炼 AI (DashScope/Qwen) 的在线学习平台 (`kc.zhixueyun.com`) 自动挂课工具。自动完成视频观看、文档阅读、AI答题等学习任务。

## 常用命令

```bash
# 环境安装
pip install -r requirements.txt
playwright install chromium

# 按顺序执行的5步流水线
python 1get_cookie.py          # 扫码登录，保存cookie
python 2get_urls.py            # 自动解析主题页面获取课程链接
python 点击按钮获取链接.py       # 或手动点击获取链接（二选一）
python 3afk.py                 # 主程序：自动挂课
python 4ai_examination.py      # AI自动考试
python 5examination.py         # 人工考试兜底
```

本项目无测试套件。

## 架构

### 执行流水线

```
登录(扫码) → 采集URL → 自动挂课 → AI考试 → 人工考试
1get_cookie   2get_urls    3afk      4ai_exam   5examination
```

### 核心模块 (`core/`)

- **`browser.py`** — 异步上下文管理器，从 `cookies.json` 加载cookie并启动 Chromium（MS Edge channel），完成认证跳转后 yield `(browser, context)`
- **`learning.py`** — 最大模块。两个主入口：`subject_learning(page)` 处理主题学习页（遍历课程/URL/考试/调研等类型）；`course_learning(page_detail, learn_item)` 处理单个课程页（按 `data-sectiontype` 分发到视频/文档/H5/考试处理器）
- **`exam_engine.py`** — AI考试引擎。检测单题/多题模式 → 提取题目 → 调用AI获取答案 → 选择答案 → 提交
- **`question_parser.py`** — 题型检测（单选/多选/判断/填空/排序/阅读理解）和选项提取
- **`file_ops.py`** — URL规范化、格式校验（`kc.zhixueyun.com/#/study/(course|subject)/detail/UUID`）、文件读写
- **`logging_config.py`** — 统一日志配置（控制台 + `log.txt`，DEBUG级别）

### 关键设计细节

- `1get_cookie.py` 使用 Playwright **同步** API，其余脚本均使用 **异步** API
- `3afk.py` 外层 `while True` 循环：处理失败的课程写入 `剩余未看课程链接.txt` 并自动重试，直到全部完成
- AI考试使用 OpenAI SDK 的兼容模式调用 DashScope，通过 `client.responses.create()` 接口
- 课程类型通过 DOM 元素的 `data-sectiontype` 属性判断：5/6=视频，1/2/3=文档，4=H5，9=考试
- 考试剩余次数 ≤3 时自动转入人工考试，避免次数耗尽

### 中间文件（运行时生成）

脚本运行过程中会生成多个 `.txt` 文件用于步骤间传递数据（考试链接、失败重试链接、人工处理链接等），均已被 `.gitignore` 排除。

## 配置

`.env` 文件包含：DashScope API 地址/密钥、模型名称、主题页面URL、起始页面URL。详见 README.md。

## 语言

所有交流和输出使用中文。
