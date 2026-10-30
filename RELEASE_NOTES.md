# 唱练 v1.0 · 本地练歌工作室

上传一首歌，自动完成**云音乐缓存解密 → 人声/伴奏分离 → 歌词匹配 → 日语假名注音与罗马音**，
随后即可在浏览器中跟伴奏练唱。绿色免安装、解压即用，除歌词元数据查询外全程离线。

## 下载与安装

1. 下载 `唱练-v1.0-win64.zip`（约 560 MB，解压后约 1.35 GB）。
2. 解压到任意目录（建议纯英文路径），双击其中的 **`唱练.exe`**。
3. 数秒后浏览器会自动打开 http://127.0.0.1:8178 ；没有自动打开就手动访问该地址。
4. 使用期间不要关闭黑色控制台窗口；用完直接关窗即退出。
5. 如出现 Windows SmartScreen 蓝色提示：点击「更多信息」→「仍要运行」（未做付费代码签名，属正常现象）。

**系统要求**：Windows 10 / 11 64 位；首次分离一首 4 分钟歌曲在纯 CPU 上约需 1.5–3 分钟。

## 功能一览

- **云音乐缓存直接导入**：网易云 `.ncm`、QQ 音乐 `.qmc/.qmcflac/.mflac/.mgg`、酷狗 `.kgm/.kgma`、
  酷我 `.kwm/.vpr/.tkm`，以及 mp3/flac/m4a/wav/ape/wma 等常见格式，上传后本地自动解密/转码。
- **人声 / 伴奏分离**：UVR MDX-Net 模型（ONNX Runtime，CPU），任务串行队列；
  分离结果即时落盘——刷新页面、中途关闭、重启程序都不会丢状态或重复计算；
  若上次异常退出，再次点击会自动识别已完成的产物并恢复。
- **歌词四源级联匹配**：LRCLIB → 网易云音乐 → QQ 音乐 → 本地 `lrcs/` 兜底，
  以歌手、曲名、时长综合打分选版本，自动剔除作词作曲等信息行，显著改善日语歌命中率。
- **日语假名注音 + 罗马音**：fugashi + UniDic 离线形态分析，输出 `漢字《かんじ》|kanji` 对照；
  歌词与注音均支持手动编辑、重新匹配、重新注音。
- **练习页**：50%–150%、1% 精度**不变调**变速；当前句整行高亮并自动滚动；
  A/B 打点段落循环；伴奏 / 人声 / 原唱三轨切换；麦克风录音跟唱（录音自动回原速保证混音对齐）。
- **导出**：伴奏、录音、伴奏+录音混音均可一键导出为 192kbps MP3，
  通过系统「另存为」自选保存目录。
- **零账号、零遥测**：不登录、不收集任何信息。

## 隐私说明

- 解密、人声分离、注音、录音、MP3 编码全部在本机运算，**音频文件从不上传**。
- 只有"匹配歌词"会访问网络，且仅向 LRCLIB / 网易云音乐 / QQ 音乐的公开接口发送
  歌曲名、歌手名、时长这类元数据。
- 程序只监听 `127.0.0.1`，局域网和外网无法访问。

## 开源致谢

本项目站在众多优秀开源项目的肩膀上，按模块列明（版本为发行包实际内置版本）：

### 人声分离与模型

| 组件 | 用途 | 许可 | 主页 |
|---|---|---|---|
| audio-separator 0.47.1 | UVR 分离流水线封装 | MIT | https://github.com/jarredou/audio-separator |
| UVR-MDX-NET-Inst_HQ_3 | 人声分离模型权重 | UVR 社区模型许可 | https://github.com/Anjok07/ultimatevocalremovergui |
| MDX-Net | 分离网络架构（Kim 等） | 研究用途/社区授权 | https://github.com/kuielab/mdx-net |
| ONNX Runtime 1.31.1 | 模型推理引擎 | MIT | https://github.com/microsoft/onnxruntime |
| PyTorch 2.15.0 / torchvision 0.29.2 | 张量计算（模型转换与辅助） | BSD-3-Clause | https://pytorch.org |
| onnx2torch 1.6.0 | ONNX→Torch 兼容层 | Apache-2.0 | https://github.com/EN10/onnx2torch （py3.13 兼容分发） |
| rotary-embedding-torch 0.6.5 | 模型依赖 | MIT | https://github.com/lucidrains/rotary-embedding-torch |

### Web 服务与音频处理（Python）

| 组件 | 用途 | 许可 |
|---|---|---|
| FastAPI 0.162 / Starlette 1.10 / Uvicorn 0.54 | 本地 HTTP 服务 | MIT / BSD-3-Clause / BSD-3-Clause |
| Pydantic 2.14 | 数据校验 | MIT |
| python-multipart 0.0.32 | 文件上传解析 | Apache-2.0 |
| NumPy 2.5 / SciPy 1.18 | 数值计算 | BSD-3-Clause |
| librosa 1.0 | 音频分析 | ISC |
| pysoundfile 0.14 | 音频读写（libsndfile） | BSD-3-Clause |
| audioread 3.1 / lazy-loader 0.6 / pydub 0.25 | 音频解码辅助 | MIT / BSD-3-Clause / MIT |
| Pillow 12 | 图像依赖（torchvision） | HPND（MIT 类） |
| FFmpeg / FFprobe | 音频转码与解码 | LGPL-2.1-or-later（官方 Windows 构建为 GPL 版本） https://ffmpeg.org |

### 加密缓存解密

| 组件 | 用途 | 许可 |
|---|---|---|
| music_unlock（music-geshizhuanhuan） | NCM/QMC/KGM/KWM 解密，已随源码内置并保留其 LICENSE | MIT（见 `server/vendor/LICENSE`） |
| pycryptodome 4.2 | AES 等密码学原语 | BSD-2-Clause |
| mutagen 1.48 | 音频标签读写 | GPL-2.0-or-later |

### 日语分词、注音与罗马音

| 组件 | 用途 | 许可 |
|---|---|---|
| fugashi 1.5 | MeCab 的 Python 绑定 | MIT |
| MeCab | 日语形态分析引擎（工藤拓） | BSD-3-Clause / GPL 双许可 |
| UniDic / unidic-lite 1.0 | 日语词典（© NINJAL，unidic-lite 打包封装为 MIT） | BSD 类 / MIT |
| cutlet 0.5 | 日语→罗马音 | MIT |
| jaconv 0.5 | 假名/日文文字转换 | MIT |

### 前端

| 组件 | 用途 | 许可 | 主页 |
|---|---|---|---|
| lamejs | 浏览器内 MP3 编码（`web/vendor/lame.min.js`，基于 LAME） | LGPL-3.0-or-later | https://github.com/zhuker/lamejs |
| Python 3.12 | 运行时 | PSF License | https://www.python.org |

### 数据来源声明（在线服务，非捆绑软件）

- [LRCLIB](https://lrclib.net)：开放时间轴歌词库；
- 网易云音乐、QQ 音乐：仅在歌词缺失时调用其公开搜索接口获取歌词文本，不访问账号相关接口；
- 所有歌词版权归原作者及平台所有，本程序不对歌词内容做任何再分发主张。

## 免责声明

本软件仅供个人学习与声乐练习使用。请仅解密、处理你**合法拥有或有权使用**的本地音频文件；
请勿用于侵犯版权、绕过平台付费权益或任何商业用途。软件按"现状"提供，作者不对使用后果负责。
