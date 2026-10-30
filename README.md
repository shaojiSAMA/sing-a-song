# 唱练 · 本地练歌工作室

上传一首歌，自动完成**云音乐缓存解密 → 人声/伴奏分离 → 歌词匹配 → 日语假名注音与罗马音**，
然后在浏览器里跟着伴奏练习：50%–150% 不变调变速、A/B 段落循环、录音跟唱、导出 MP3。

除歌词元数据查询外，所有处理（解密、分离、注音）全部在本机完成，**音频从不上传**。

## 功能

- **多格式导入**：mp3 / flac / m4a / wav 等常见格式，以及网易云 `.ncm`、QQ 音乐 `.qmc/.mflac/.mgg`、
  酷狗 `.kgm/.kgma`、酷我 `.kwm` 等加密缓存，上传后本地自动解密。
- **人声/伴奏分离**：内置 UVR MDX-Net 模型（ONNX Runtime / CPU），串行任务队列，
  结果落盘即生效，刷新、关页面、重启都不会丢状态，也不会重复计算。
- **歌词四源级联**：LRCLIB → 网易云音乐 → QQ 音乐 → 本地 `lrcs/` 兜底，
  按歌手、曲名、时长综合打分，自动剔除信息行/标签行。
- **日语注音**：fugashi + UniDic 形态分析 + cutlet 罗马音，离线生成 `漢字《かんじ》` 注音；
  歌词和注音都可以手动编辑。
- **练习页**：1% 精度不变调变速、当前句整行高亮、A/B 打点循环、伴奏/人声/原唱三轨切换、
  麦克风录音跟唱、一键导出伴奏 / 录音 / 混音 MP3（系统「另存为」自选目录）。

## 下载即用（Windows）

到 [Releases](../../releases) 下载 `唱练-v1.0-win64.zip`，解压后双击 **`唱练.exe`**，
数秒后浏览器自动打开 http://127.0.0.1:8178 。关闭黑色控制台窗口即退出。
如遇 SmartScreen：「更多信息」→「仍要运行」。

## 从源码运行（开发）

需要 Windows 10/11 x64、Python 3.12：

```bat
cd E:\singren
python -m venv venv
venv\Scripts\pip install -r requirements.txt

:: FFmpeg：把 ffmpeg.exe / ffprobe.exe 放到 bin\（或加入 PATH）
:: 分离模型：首次分离时自动下载到 models\（约 67MB），也可手动放入
::   UVR-MDX-NET-Inst_HQ_3.onnx

venv\Scripts\python server\app.py
```

或直接双击 `启动唱练(开发版).bat`（自动启动并打开浏览器）。

## 打包 Windows 发行版

```bat
venv\Scripts\pip install pyinstaller==6.22.3
venv\Scripts\pyinstaller --noconfirm build.spec
copy dist_extras\使用说明.txt dist\唱练\
```

产物在 `dist\唱练\`（PyInstaller onedir，含运行时、FFmpeg、模型、词典），
整个目录压缩即为绿色免安装包。

## 目录结构

```
server/           FastAPI 本地后端（仅监听 127.0.0.1:8178）
  app.py            HTTP 接口 / 歌词编辑 / 录音与音频文件
  ingest.py         上传与加密格式解密入口
  separator_svc.py  UVR 分离任务队列（worker 直接落盘回填）
  lyrics.py         LRCLIB / 网易云 / QQ 音乐 / 本地 四源匹配
  furigana.py       日语分词注音 + 罗马音
  ffmpegutil.py     FFmpeg 转码封装
  paths.py          开发态 / PyInstaller 封装态路径中心
  vendor/           第三方 music_unlock 解密库（MIT，含 LICENSE）
web/              纯静态前端（零构建），index.html + css + js
  vendor/lame.min.js  MP3 编码（lamejs, LGPL-3.0）
bin/              放 ffmpeg.exe / ffprobe.exe（不入库）
models/           分离模型（不入库，首启自动下载）
library/          用户歌曲项目（不入库）
lrcs/             本地歌词兜底目录
build.spec        PyInstaller 配置
launcher.py       发行版入口（选端口、播种模型、起服务、开浏览器）
```

## 隐私说明

- 解密、人声分离、注音、录音、MP3 编码均为**本机离线运算**；
- 仅在匹配歌词时，向 LRCLIB / 网易云 / QQ 音乐的公开接口发起网络请求，
  只携带歌曲名、歌手、时长这类元数据，不携带任何音频或个人信息；
- 不包含任何账号登录、统计 SDK 或遥测。

## 许可证

本项目代码以 **MIT License** 开源（见 [LICENSE](./LICENSE)）。
注意：发行包中捆绑的 FFmpeg（GPL/LGPL 构建）、分离模型权重、lamejs（LGPL-3.0）、
mutagen（GPL-2.0）等第三方组件遵循各自许可证，歌词版权归原权利人所有。

## 开源致谢

详见 [RELEASE_NOTES.md](./RELEASE_NOTES.md) 的开源组件清单，以及
`server/vendor/LICENSE`（music_unlock）。本项目仅用于学习与个人合法拥有音频的练习使用，
请勿用于侵权或绕过平台权益的用途。
