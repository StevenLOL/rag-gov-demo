# 11 SANGUO 游戏素材提取报告

> 文档编号：11
> 文档概述：从已安装的 DOS 游戏《三国英雄传》(SANGUO) 目录中提取游戏素材
> 提取时间：2026-09-07
> 游戏目录：`E:\Program Files (x86)\SANGUO\SANGUO`
> 输出目录：`C:\src\trsmobile\others\sanguo_assets\`

---

## 一、提取成果总览

| 类别 | 数量 | 大小 | 格式 | 说明 |
|------|------|------|------|------|
| 图片 | 49 张 | 11.95 MB | PNG | PCX 转换，640×480 |
| 音效 | 135 个 | 1.12 MB | WAV | 直接复制 |
| 音乐 | 91 首 | 0.85 MB | MIDI | XMI 转换 |
| 对话文本 | 22 个 | 0.01 MB | TXT | TLK 提取（GBK） |
| 动画 | 2 个 | 1.47 MB | FLC | 直接复制 |
| 字体 | 16 个 | 2.76 MB | 原格式 | 直接复制 |
| 调色板 | 1 个 | <0.01 MB | PAL | 直接复制 |
| **总计** | **316 个** | **18.19 MB** | | |

---

## 二、图片素材（49 张）

全部为 640×480 分辨率，从 PCX 格式转换为 PNG，使用 PCX 文件内嵌调色板。

### 2.1 分类清单

| 分类 | 文件 | 数量 | 说明 |
|------|------|------|------|
| 标题画面 | TITLE.png | 1 | 红色背景+金色"三国英雄传"标题+箭头装饰 |
| 关卡剧情 | LEVEL01~20.png | 20 | 各关剧情插画（桃园结义、怒鞭督邮等） |
| 城池场景 | HOUSE02~20.png | 19 | 城池/内政画面（等距视角中式建筑） |
| 商店画面 | STORE01~05.png | 5 | 武器店/药店等商店界面 |
| 结局画面 | SUCC1/2.png | 2 | 通关画面 |
| 失败画面 | FAIL.png | 1 | 游戏失败画面 |
| 安装画面 | INSTALL.png | 1 | 安装程序画面 |

### 2.2 关键图片预览

- **TITLE.png**：游戏主标题，红色纹理背景，金色立体"三国英雄传"字样，金色横贯箭头
- **LEVEL01.png**：桃园三结义，刘备/关羽/张飞在桃花园中结拜
- **STORE01.png**：药店画面，中药柜+草药+葫芦+石纹标题栏+龙纹装饰
- **HOUSE02~20.png**：城池内政场景，等距视角中式建筑

---

## 三、音效素材（135 个 WAV）

位于 `sounds/` 目录，命名规则：
- `A000~A128.WAV`：A 组音效（攻击、技能等）
- `B000~B117.WAV`：B 组音效
- `C000~C106.WAV`：C 组音效
- `D000~D102.WAV`：D 组音效
- `E000~E104.WAV`：E 组音效
- `F000~F103.WAV`：F 组音效
- `G000.WAV`、`G100.WAV`：G 组
- `LOGO.WAV`：Logo 音效

均为 8-bit/11kHz 单声道 WAV（DOS 时代标准）。

---

## 四、音乐素材（91 首 MIDI）

从 XMI（Miles Sound System MIDI）格式转换为标准 MIDI（.mid）。

### 4.1 XMI 格式解析

XMI 文件结构（已逆向分析）：
```
FORM/XDIR/INFO + CAT /FORM/XMID/TIMB(音色表) + EVNT(MIDI事件)
```
- `TIMB` 块：音色映射表
- `EVNT` 块：标准 MIDI 事件流（带运行状态）
- 转换方式：提取 EVNT 块，包装为 MThd+MTrk 标准 MIDI

### 4.2 音乐分类

| 分类 | 文件 | 数量 | 说明 |
|------|------|------|------|
| 标题音乐 | TITLE.mid, TT.mid | 2 | 标题画面背景音乐 |
| 游戏音乐 | GAME.mid, GAME3.mid | 2 | 战场/游戏中音乐 |
| 城池音乐 | HOUSE01~20.mid | 20 | 各城池背景音乐 |
| 关卡音乐 | PASS01~20.mid | 20 | 各关卡过场音乐 |
| 对战音乐 | VS001~022.mid, VS101~122.mid | 44 | 武将对战音乐 |
| 其他 | NEW.mid, OLD.mid, FAIL.mid | 3 | 新旧版/失败音乐 |

---

## 五、对话文本（22 个 TLK 提取）

从 DATA/LEVEL*.TLK 中提取 GBK 编码的中文对话文本。

| 关卡 | 文本段数 | 关卡 | 文本段数 |
|------|----------|------|----------|
| LEVEL1 | 5 | LEVEL12 | 2 |
| LEVEL2 | 5 | LEVEL13 | 4 |
| LEVEL3 | 5 | LEVEL14 | 6 |
| LEVEL4 | 3 | LEVEL15 | 3 |
| LEVEL5 | 3 | LEVEL16 | 3 |
| LEVEL6 | 3 | LEVEL17 | 7 |
| LEVEL7 | 8 | LEVEL18 | 3 |
| LEVEL8 | 5 | LEVEL19 | 4 |
| LEVEL9 | 3 | LEVEL20 | 3 |
| LEVEL10 | 3 | LEVEL21 | 3 |
| LEVEL11 | 3 | LEVEL22 | 4 |

共 22 个关卡对话文件，83 段文本。

---

## 六、动画与字体

### 6.1 动画（2 个 FLC）
- `LOGO.FLC`（1058 KB）：Logo 动画
- `REDANTS.FLC`（446 KB）：红蚂蚁动画（可能是过场动画）

FLC 是 Autodesk FLIC 动画格式，DOS 时代常用。

### 6.2 字体（16 个）
位于 `fonts/` 目录：
- `ASCFONT.15F/.16/.24/.24F`：ASCII 字体（多种字号）
- `SPCFONT.15F/.16/.24/.24F`：特殊字符字体
- `SPCFSUPP.15F/.16/.24/.24F`：特殊字符补充
- `STDFONT.15F/.16/.24/.24F`：标准字体（含中文）

---

## 七、技术备注与 Bug 修复

### 7.1 提取脚本
- 文件：`scripts/05_提取SANGUO游戏素材.py`
- 依赖：Pillow（conda 环境）

### 7.2 Bug 修复记录（规则8/9）

**Bug 1：XMI 转换全部失败**
- 现象：91 首 XMI 全部报"未找到 MIDI 块"
- 原因：XMI 格式中 MIDI 事件在 `EVNT` 块中，而非 `MIDI` 块
- 修复：将搜索标记从 `b"MIDI"` 改为 `b"EVNT"`
- 举一反三：逆向未知格式时，应先 hex dump 分析真实结构，不可凭假设编码

**Bug 2：PCX 图片颜色错乱**
- 现象：标题画面显示为蓝绿色调，而非红色背景
- 原因：用外部 DEFAULT.PAL 覆盖了 PCX 文件内嵌的调色板，两者颜色映射不同
- 修复：移除外部调色板覆盖逻辑，让 Pillow 自动读取 PCX 内嵌调色板（PCX 末尾 `0C` + 768 字节）
- 举一反三：自带调色板的图像格式（PCX/GIF/BMP）不应强制使用外部调色板

**Bug 3：docstring 转义序列警告**
- 现象：`SyntaxWarning: invalid escape sequence '\P'`
- 原因：docstring 中 Windows 路径 `\P` 被解析为转义序列
- 修复：将路径中的反斜杠改为正斜杠

### 7.3 未提取的专有格式

以下格式因缺乏格式规范未做深度解析，保留原始文件供后续研究：
- `.GRP`：图形数据包（关卡图形，可能含多个 sprite）
- `.LIB`：资源库文件（FLAG.LIB、OBJECT.LIB、SOLDIER.LIB 等）
- `.MAP`：关卡地图数据
- `.OBJ`：关卡对象数据
- `.HUM`：人物数据
- `.SHP`：图形形状文件（BUSINESS.SHP）
- `.TBL`：表格数据（BOAT.TBL）
- `.KND`：种类数据（MAN.KND）
- `.TPE`：类型数据（SOLDIER.TPE）
- `.OFF`：偏移数据（HUMAN.OFF）

---

## 八、文件结构

```
others/sanguo_assets/
├── images/           # 49张PNG图片
│   ├── TITLE.png
│   ├── LEVEL01~20.png
│   ├── HOUSE02~20.png
│   ├── STORE01~05.png
│   └── ...
├── sounds/           # 135个WAV音效
├── music/            # 91首MIDI音乐
├── text/             # 22个对话文本TXT
├── animations/       # 2个FLC动画
├── fonts/            # 16个字体文件
├── palette/          # DEFAULT.PAL调色板
└── asset_manifest.json  # 素材清单
```

---

## 九、信源

1. 游戏本体：`E:\Program Files (x86)\SANGUO\SANGUO\`（智冠《三国英雄传》DOS 版）
2. XMI 格式参考：Miles Sound System XMI 格式逆向分析（本报告 hex dump 实证）
3. PCX 格式参考：PCX 文件末尾 0C + 768 字节 VGA 调色板（标准规范）
