# WDXK (DreamRivakes) APK 素材提取 — 工作交接文档

> **交接日期**: 2026-09-11
> **状态**: 进行中（图片提取初步完成，音频/脚本待深入）
> **接手人**: 下一位逆向专家
> **目标**: 从 `wdxk_259504.apk` 提取图片/音频/脚本/动画等全部素材

---

## 一、项目基本信息

| 项 | 值 |
|---|---|
| 游戏 APK | `E:\Downloads\wdxk_259504.apk` |
| APK 大小 | 925 MB (969,908,563 字节) |
| 文件总数 | 21,271 个 ZIP 条目 |
| 内部代号 | **DreamRivakes**（从 Lua 文件路径发现） |
| 签名标识 | **DIANHUN_**（META-INF/DIANHUN_.SF） |
| 游戏风格 | 水墨国风武侠（从提取图片判断） |

---

## 二、技术栈确认

### 2.1 引擎
- **Unity Engine**（确认：有 globalgamemanagers / level0-6 / sharedassets）
- **IL2CPP** 编译（libil2cpp.so 46MB）
- **xLua** 热更新框架（libxlua.so，大量 .lua 脚本）

### 2.2 音频
- **FMOD Studio** 音频引擎（libfmod.so / libfmodstudio.so）
- **88 个 .bank 文件**（FMOD FEV 格式，共 104MB）

### 2.3 第三方 SDK
- 腾讯 MSDK（libMSDKCore.so）
- 腾讯云语音 GVoice（libGVoice.so / libgcloud.so）
- Bugly 崩溃上报
- 腾讯安全（libtersafe.so / libtgpa.so）

---

## 三、目录结构

### 3.1 APK 顶层
| 目录 | 文件数 | 说明 |
|---|---|---|
| assets/ | 20,599 | 核心资源 |
| res/ | 571 | Android 资源 |
| lib/ | 66 | 原生库（arm64-v8a / armeabi-v7a） |
| META-INF/ | 32 | 签名信息 |

### 3.2 assets/ 二级目录
| 目录 | 文件数 | 大小 | 说明 |
|---|---|---|---|
| assets/bin/Data/ | 20,394 | 3.15 GB | **Unity 资源核心目录** |
| assets/GCloudVoice/ | 8 | 17.4 MB | 腾讯语音资源 |
| assets/share/ | 24 | 6.6 MB | 分享图片（周末活动等） |
| assets/*.bank | 88 | 104 MB | FMOD 音频银行 |

### 3.3 assets/bin/Data/ 文件类型
| 类型 | 数量 | 大小 | 说明 |
|---|---|---|---|
| 无扩展名 (Asset Bundle) | 20,307 | 3.16 GB | Unity Asset Bundle，哈希命名 |
| .resource | 55 | 45.3 MB | Unity 流式资源数据 |
| .dat | 5 | 9.0 MB | 数据文件 |
| globalgamemanagers | 1 | 20.9 MB | Unity 全局管理器 |
| level0 ~ level6 | 7 | 0.5 MB | 关卡文件 |
| sharedassets0~6.assets | 7 | 0.1 MB | 共享资源 |

---

## 四、已完成的工作

### 4.1 图片提取（✅ 初步完成）

**输出位置**: `extracted\WDXK\images\`

**数量**: **853 张 PNG**

**方法**:
1. 用 UnityPy 1.25.3 读取 Asset Bundle
2. 遍历所有对象，提取 Texture2D
3. 用 `tex.image` 导出为 PNG
4. 文件名格式: `{bundle前缀}_t{path_id}_{名称}.png`

**已验证的图片风格**:
- 水墨国风背景（竹林、山水、古建筑）
- 游戏 UI 元素（按钮、图标）
- 特效贴图（粒子、烟雾）
- 场景物件（画舫、屋顶）

**处理范围**: 100KB - 5MB 的 bundle 各 1000 个 + 5-50MB 的 12 个

### 4.2 原始 PNG 提取（✅ 完成）

**输出位置**: `extracted\WDXK\png_raw\`

**数量**: 360 个 PNG 文件

**说明**: APK 中直接存在的 PNG 文件（非 Unity 资源）

### 4.3 FMOD .bank 文件（✅ 已提取，未解析）

**输出位置**: `extracted\WDXK\banks\`

**数量**: 88 个 .bank 文件，共 104 MB

**格式**: RIFF 头，FEV FMFT 标识（标准 FMOD FEV）

**命名规律**:
- `stroy_part*.bank` — 剧情语音
- `skillcall_*.bank` — 技能语音
- `baiyimojun_part*.bank` — 白衣魔君相关
- `baiyijiao.bank` — 白衣教相关
- `loulan_music.bank` — 楼兰音乐
- `jiuguan_music.bank` — 九关音乐
- `amb.bank` — 环境音
- `UI.bank` — UI 音效

### 4.4 Lua 脚本 / TextAsset（⚠️ 部分完成）

**输出位置**: `extracted\WDXK\lua_scripts\`

**数量**: 2369 个文件
- 1988 个 .lua（大部分 0 字节）
- 186 个 .skel（Spine 骨骼动画）
- 186 个 .atlas（Spine 图集）

**问题**: 大部分 Lua 文件是 0 字节，因为是**流式资源**，实际数据在 .resource 文件中，需要正确加载 Unity 环境才能读取。

**已确认有内容的文件**:
- `util.lua` (6.3KB) — xLua 工具库
- `tdr.lua` (3.3KB)
- `TB_AbilityModifier.lua` (1.1KB)

---

## 五、未解决的问题

### 5.1 FMOD 音频提取（❌ 未完成）

**现状**: 88 个 .bank 文件已提取，但未解析出单个音频文件。

**原因**: 需要 FMOD 解码库或专门工具。

**建议方案**:
1. 下载 **fsbext**（FSB 提取工具）
2. 或安装 **FMOD Studio Bank Processor**
3. 或用 Python 解析 FEV/FSB 格式

### 5.2 流式资源读取（❌ 未完成）

**现状**: 大部分 Texture2D 和 TextAsset 是流式的，数据在 .resource 文件中。

**原因**: UnityPy 单独读取 bundle 时，找不到对应的 .resource 文件，导致数据为空。

**建议方案**:
1. 把所有 .resource 文件放到 UnityPy 的加载路径中
2. 或用 AssetStudio GUI 工具打开整个 Data 目录
3. 或修改 UnityPy 加载逻辑，关联 bundle 和对应的 .resource

### 5.3 Spine 动画（❌ 未处理）

**现状**: 186 个 .skel + 186 个 .atlas 文件已提取（但大部分 0 字节）。

**说明**: Spine 骨骼动画数据，需要 Spine 编辑器或 DragonBones 工具查看。

---

## 六、环境与工具

### 6.1 Python
- 路径: `E:\Users\Administrator\miniconda3\python.exe`
- 已安装: UnityPy 1.25.3, Pillow

### 6.2 脚本清单
| 脚本 | 功能 |
|---|---|
| 219_wdxk_probe.py | 探查 APK 结构，确认 Unity 引擎 |
| 220_wdxk_extract_bundles.py | 提取小 bundle (0-100KB) |
| 221_wdxk_png_banks.py | 提取原始 PNG + .bank 文件 |
| 222_wdxk_extract_v2.py | 提取中 bundle (100KB-5MB) |
| 223_wdxk_game_info.py | 分析游戏身份/SDK |
| 224_wdxk_debug_tex.py | 调试 Texture2D API |
| 225_wdxk_tex_props.py | 查看 Texture2D 属性 |
| 226_wdxk_extract_v3.py | 提取中 bundle（修正文件名） |
| 227_wdxk_extract_v4.py | 提取大 bundle (5-50MB) |
| 228_wdxk_debug_text.py | 调试 TextAsset API |
| 229_wdxk_extract_lua.py | 批量提取所有 TextAsset |

---

## 七、文件速查表

| 用途 | 路径 |
|---|---|
| 原始 APK | `E:\Downloads\wdxk_259504.apk` |
| 工作目录 | `C:\src\InformationSecurity\dosgames\work\wdxk\` |
| 输出根目录 | `C:\src\InformationSecurity\dosgames\extracted\WDXK\` |
| 图片 | `extracted\WDXK\images\` (853 张) |
| 原始 PNG | `extracted\WDXK\png_raw\` (360 张) |
| FMOD banks | `extracted\WDXK\banks\` (88 个) |
| Lua 脚本 | `extracted\WDXK\lua_scripts\` (2369 个) |
| 音频输出 | `extracted\WDXK\audio\` (空) |
| 分析脚本 | `scripts\219~229_wdxk_*.py` |

---

## 八、下一步建议（按优先级）

### 优先级 1：用 AssetStudio 批量导出
AssetStudio 是 GUI 工具，能正确处理流式资源和 .resource 文件，比 UnityPy 手动写脚本更可靠。
- 下载 AssetStudio：https://github.com/Perfare/AssetStudio
- 打开整个 `assets/bin/Data/` 目录
- 批量导出所有 Texture2D / AudioClip / TextAsset

### 优先级 2：FMOD 音频提取
- 下载 fsbext 或 FSB Extractor
- 解析 88 个 .bank 文件，提取 WAV/OGG 音频
- 按剧情/技能/音乐分类

### 优先级 3：完善图片提取
- 处理剩余的 15,000+ 小 bundle
- 处理 .resource 流式资源中的图片
- 导出 Sprite 图集（SpriteAtlas）

---

> **交接人备注**: 这是一个腾讯系的 Unity+IL2CPP+xLua 武侠手游，内部代号 DreamRivakes。图片已初步提取 853 张，质量很好（水墨国风）。音频都在 FMOD .bank 里需要专门工具。Lua 脚本大部分是流式资源，需要 AssetStudio 这类成熟工具才能完整提取。建议接手人优先用 AssetStudio 打开整个 Data 目录，效率最高。
