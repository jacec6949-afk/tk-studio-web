# TK Studio Web Deploy

这是基于原版 TK Studio `index.html` 的网站部署包：不重新设计前端界面，GitHub Pages 托管网页，云端 Python 服务运行 `/api` 视频处理接口。

## 目录

- `index.html`：原版工作台前端
- `server.py`：视频处理后端
- `Dockerfile`：云端容器部署
- `render.yaml`：Render 部署配置
- `.env.example`：环境变量示例
- `github-pages-config.example.html`：前端 API 地址配置示例

## 当前仓库

[GitHub 仓库](https://github.com/jacec6949-afk/tk-studio-web)

## 重要说明

GitHub Pages 只能托管静态网页，不能运行 Python、FFmpeg 或 ASR。完整功能需要把 `server.py` 部署到支持 Docker/Python 的云服务。

## 部署后端（Render 示例）

1. 在 GitHub 新建一个仓库。
2. 上传本目录全部文件。
3. 在 Render 创建 New Web Service，连接该仓库。
4. 选择 Docker，使用根目录 `Dockerfile`。
5. 设置环境变量：
   - `ALLOWED_ORIGINS`：填 GitHub Pages 的来源，例如 `https://你的用户名.github.io`
   - `TK_MODEL`：默认 `qwen2.5vl:3b`
   - `TK_WHISPER`：默认 `small`
   - `MAX_UPLOAD_BYTES`：默认 `150000000`
6. 部署后打开 `https://你的后端域名/api/health`。
7. 返回 `ok: true` 才表示后端已上线。

## GitHub Pages 前端

将 `index.html` 放到 GitHub Pages 仓库。部署后，把以下标签放在 `<head>` 内，并替换为后端地址：

```html
<meta name="tk-api-base" content="https://你的后端域名/api">
```

本包已经包含空的配置标签。未填写时，页面在同源本地服务下使用 `/api`；放到 GitHub Pages 后必须填写云端 API 地址。

## 运行能力

后端安装 FFmpeg 后支持：

- TikTok 公开链接获取
- 本地视频上传
- 镜头检测
- 关键帧生成
- Whisper 时间戳字幕
- 本地视觉模型分析（需要可访问的 Ollama 与模型）
- Excel、SRT、JSON、ZIP 导出

不要把 AI 密钥、Cookie 或服务端凭证写入 `index.html` 或 GitHub 仓库。仅处理你有权下载和分析的素材。
