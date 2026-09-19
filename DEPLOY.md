# 公网部署

推荐使用 Streamlit Community Cloud。它适合本项目的 Streamlit 结构，部署后会生成公网 HTTPS 地址，不需要用户电脑持续运行本地服务。

## 1. 上传到 GitHub

在 GitHub 新建一个仓库，例如 `inquiry-sentinel`，然后在项目目录执行：

```powershell
git add .
git commit -m "prepare public deployment"
git branch -M main
git remote add origin https://github.com/<your-account>/inquiry-sentinel.git
git push -u origin main
```

不要上传 `.env` 或真实 API Key。`.gitignore` 已经忽略 `.env`。

## 2. 创建公网应用

打开 [Streamlit Community Cloud](https://share.streamlit.io/)，使用 GitHub 登录，选择刚才的仓库：

- Repository：`<your-account>/inquiry-sentinel`
- Branch：`main`
- Main file path：`app.py`

点击 Deploy。平台会根据根目录的 `requirements.txt` 安装依赖。

## 3. 配置模型 Key

不配置 Key 也可以使用“演示模式”。如果要启用 DeepSeek，在应用的 Secrets 中填入：

```toml
DEEPSEEK_API_KEY = "sk-..."
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEEPSEEK_MODEL = "deepseek-chat"
```

通义千问配置：

```toml
DASHSCOPE_API_KEY = "sk-..."
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DASHSCOPE_MODEL = "qwen-plus"
```

## 4. 部署后检查

1. 选择“使用内置演示样例”。
2. 点击“开始多智能体分析”。
3. 确认能看到风险明细。
4. 上传 `data/demo_annual_report.txt` 测试文件解析。
5. 再上传真实年报 PDF。

公网版本仍然保留“AI生成”声明，不建议把涉密年报或真实 API Key 放入公开仓库。
