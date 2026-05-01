# IDM Clone — 多线程下载器

类 IDM 的多线程下载工具，带 Chrome/Edge 浏览器插件，支持视频嗅探。

## 功能

| 功能 | 说明 |
|------|------|
| 多线程分片下载 | 默认 8 线程，1-32 可配置，速度倍增 |
| 断点续传 | 意外中断后继续下载，不重头来过 |
| 浏览器插件 | 自动拦截浏览器下载，无缝发送到下载器 |
| 视频嗅探 | YouTube、B站、抖音等 1000+ 网站，via yt-dlp |
| 文件类型过滤 | 自定义捕获哪些扩展名 |
| 大小过滤 | 小于 N MB 的文件让浏览器自己处理 |
| 站点黑名单 | 屏蔽指定域名，不捕获其下载 |
| 系统代理 | 自动读取 Windows 代理设置，兼容 Clash/V2Ray |

## 快速开始

### 方式一：下载 Release（推荐）

1. 前往 [Releases](../../releases) 下载最新版本
2. 解压 `IDMClone-Windows.zip`，运行 `IDMClone.exe`
3. 解压 `IDMClone-Extension.zip`，在浏览器加载扩展（见下方）

### 方式二：从源码运行

```bash
# 克隆仓库
git clone https://github.com/your-username/idm-clone.git
cd idm-clone/downloader

# 安装依赖
pip install -r requirements.txt

# 运行
python main.py
```

## 安装浏览器插件

1. 打开 Chrome/Edge，进入 `chrome://extensions`
2. 右上角开启「**开发者模式**」
3. 点击「**加载已解压的扩展程序**」
4. 选择 `extension/` 文件夹（或解压后的 zip 内容）
5. 插件图标显示 🟢 绿点 = 已连接下载器

## 从源码编译（GitHub Actions）

推送 tag 即可自动触发编译：

```bash
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions 会自动：
- 在 Windows 上用 PyInstaller 编译 `.exe`
- 打包浏览器插件为 `.zip`
- 创建 Release 并附上下载链接

## 项目结构

```
idm-clone/
├── .github/workflows/build.yml   # 自动编译
├── downloader/
│   ├── main.py                   # 入口
│   ├── engine.py                 # 下载引擎
│   ├── server.py                 # 本地 API (Flask)
│   ├── config_manager.py         # 配置管理
│   ├── requirements.txt
│   ├── IDMClone.spec             # PyInstaller 配置
│   └── gui/
│       ├── main_window.py        # 主界面
│       ├── add_url_dialog.py     # 新建下载对话框
│       └── settings_dialog.py   # 设置面板
└── extension/
    ├── manifest.json
    ├── background.js             # 拦截下载 + 嗅探
    ├── content.js                # 页面注入脚本
    ├── popup.html / popup.js     # 插件弹窗
    └── icons/
```

## 配置说明

设置面板（`Ctrl+,`）中可配置：

**下载设置**
- 默认保存路径
- 单任务线程数（1-32）
- 最大同时下载数

**捕获过滤**
- 捕获的文件类型（如 `mp4 zip exe`）
- 最小文件大小（小于此值让浏览器处理）
- 站点黑名单

**代理设置**
- 系统代理（自动读取 Windows 设置）
- 自定义代理（如 `http://127.0.0.1:7890`）
- 不使用代理

## 本地 API

下载器在 `localhost:16800` 启动 HTTP 服务，浏览器插件通过此接口通信：

| 接口 | 方法 | 说明 |
|------|------|------|
| `/ping` | GET | 健康检查 |
| `/add` | POST | 添加普通下载任务 |
| `/add_video` | POST | 添加视频嗅探任务 |
| `/status` | GET | 获取任务列表和统计 |
| `/config` | GET | 获取过滤配置 |

## License

MIT
