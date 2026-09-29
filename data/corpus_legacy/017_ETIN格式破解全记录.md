# ETIN（倚天屠龙记 DOS 版）资源格式破解与提取全记录

> 智冠科技 1994 年 RPG，基于 16 位 DOS 反汇编确认，2026-09-13



***

## 一、概述

ETIN（倚天屠龙记）使用自定义的 **GRP/IDX** 资源包格式存储游戏图片。IDX 是偏移索引表，GRP 是数据容器。每个 GRP 包含多张图片，图片使用两种不同的 RLE 压缩格式。

**核心发现**：游戏中存在**两种完全不同的图片编码格式**，不能用同一种解码器处理所有 GRP 文件。



***

## 二、游戏资源清单

游戏目录：`<游戏安装目录>\ETIN\`



| 类别   | 文件                 | 数量   | 尺寸     | 格式       | 说明          |
| ---- | ------------------ | ---- | ------ | -------- | ----------- |
| 头像   | M\_H.GRP/IDX       | 84   | 64×64  | 格式 A     | 人物大头像       |
| 小头像  | PASS.GRP/IDX       | 11   | 64×64  | 格式 A     | 角色通行证头像     |
| 地图瓦片 | EARTH01-09.GRP/IDX | 4607 | 37×55  | 格式 B     | 大地图地形瓦片     |
| 战斗瓦片 | WAR01-09.GRP/IDX   | 3591 | 37×55  | 格式 B     | 战斗场景瓦片      |
| 物体   | OBJS.GRP/IDX       | 60   | 30×30  | 格式 B     | 物品 / 道具图标   |
| 文字   | WORD.GRP/IDX       | 71   | 37× 可变 | 格式 B     | 图形文字        |
| 动画脚本 | ANI-01.GRP/IDX     | 332  | -      | 文本       | Big5 + 控制命令 |
| 定义数据 | DEFINE.GRP/IDX     | 474  | -      | 结构化      | w=0,h=0     |
| 对话   | TALK-1.GRP/IDX     | 1464 | -      | Big5 文本  | 中文对话        |
| 音乐   | MUS.GRP/IDX        | 38   | -      | 自定义      | 游戏音乐        |
| 音效   | VOC\_01.GRP/IDX    | 5    | -      | 8 位 PCM  | 音效          |
| 字体   | FONT.C16           | -    | -      | -        | 中文字体        |
| 调色板  | U7COLOR.COL        | -    | -      | VGA 6bit | 256 色调色板    |

> 注：EARTH03.GRP 不存在，EARTH 共 8 个文件。



***

## 三、GRP/IDX 容器格式

### 3.1 IDX 索引文件



```
uint32 offset\[0]    ← 第0张图片在GRP中的偏移

uint32 offset\[1]    ← 第1张图片在GRP中的偏移

...

uint32 offset\[N]    ← 结束偏移（=文件大小）
```



* 小端序，每个偏移 4 字节

* 第 i 张图片的数据范围：`GRP[offset[i] : offset[i+1]]`

### 3.2 GRP 子图头部

每张图片在 GRP 中的数据结构：



```
偏移  大小   字段

0     1byte  width        ← 图片宽度

1     1byte  height       ← 图片高度

2     2byte  first\_go     ← RLE数据起始偏移（相对于子图起始）

4     N×2   group\_offsets ← 组偏移表，N=(first\_go-4)/2组

first\_go  ...  RLE数据
```

**组偏移表**：每组对应 4 行像素，存储该组 RLE 数据的起始位置（相对于子图起始）。用于快速定位和随机访问。

示例（EARTH01 \[0]，37×55）：



```
first\_go = 30

N = (30-4)/2 = 13组

组偏移: \[34,38,42,46,50,54,58,62,66,110,218,364,456]

前9组每组仅4字节（全0xFF，空行）

第10组44字节（有实际像素）
```



***

## 四、两种图片编码格式

### 4.1 格式 A：跳过 / 复制 RLE（M\_H、PASS）

**编码规则**：



```
读字节b:

&#x20; b == 0xFF    → 行结束，移到下一行

&#x20; b & 0x80     → 透明跳过 (b & 0x7F) 个像素

&#x20; b < 0x80     → 复制接下来 b 个字面量字节
```

**解码伪代码**：



```
def rle\_skipcopy(data, w, h):

&#x20;   px = bytearray(w\*h)

&#x20;   pos = row = col = 0

&#x20;   while row < h and pos < len(data):

&#x20;       b = data\[pos]; pos += 1

&#x20;       if b == 0xFF:

&#x20;           row += 1; col = 0

&#x20;       elif b & 0x80:

&#x20;           col += b & 0x7F

&#x20;       else:

&#x20;           for \_ in range(b):

&#x20;               if col < w and pos < len(data):

&#x20;                   px\[row\*w+col] = data\[pos]

&#x20;                   pos += 1; col += 1

&#x20;   return px
```

**特点**：



* 0xFF 只在命令位置出现，字面量中的 0xFF 是像素值不是行结束

* 透明区域用跳过命令高效编码

* 适用于头像等有大面积透明的图片

### 4.2 格式 B：偏移 + 像素（EARTH、WAR、OBJS、WORD）

**编码规则**：



```
每行结构:

&#x20; 字节0: 左边透明偏移量（col起始位置）

&#x20; 字节1..N: 像素值（直接复制）

&#x20; 字节N+1: 0xFF（行结束）
```

**解码伪代码**：



```
def rle\_offset\_pixel(data, w, h):

&#x20;   px = bytearray(w\*h)

&#x20;   row = 0; pos = 0; col = 0

&#x20;   while row < h and pos < len(data):

&#x20;       b = data\[pos]; pos += 1

&#x20;       if b == 0xFF:

&#x20;           row += 1; col = 0

&#x20;           continue

&#x20;       col = b  # 左边透明偏移

&#x20;       while pos < len(data):

&#x20;           b = data\[pos]; pos += 1

&#x20;           if b == 0xFF:

&#x20;               row += 1; col = 0

&#x20;               break

&#x20;           if col < w:

&#x20;               px\[row\*w+col] = b

&#x20;           col += 1

&#x20;   return px
```

**特点**：



* 每行第一个字节是列偏移，不是 RLE 命令

* 像素值直接存储，无二次压缩

* 0xFF 严格作为行结束符

* 适用于地形瓦片等每行有固定起始位置的图片

### 4.3 格式区分方法



| 特征      | 格式 A（跳过 / 复制） | 格式 B（偏移 + 像素）       |
| ------- | ------------- | ------------------- |
| 首字节含义   | RLE 命令        | 列偏移                 |
| 0xFF 位置 | 命令位置          | 行结束                 |
| 组偏移间距   | 较大（268 字节）    | 较小（4-150 字节）        |
| 适用文件    | M\_H、PASS     | EARTH、WAR、OBJS、WORD |
| 图片类型    | 头像            | 瓦片 / 物体 / 文字        |



***

## 五、调色板

**文件**：`U7COLOR.COL`（768 字节，256×3 RGB）

**VGA 6 位色转 8 位**：



```
r = (r << 2) | (r >> 4)

g = (g << 2) | (g >> 4)

b = (b << 2) | (b >> 4)
```

**透明色**：调色板索引 0（黑色 0,0,0）为透明色，提取时应设为 alpha=0。

> 注意：不是 END0001.COL，游戏实际使用 U7COLOR.COL。



***

## 六、16 位 DOS 反汇编方法

### 6.1 解压 PKLite 压缩的 EXE

原始 ETIN.EXE 仅 60KB，是 PKLite 压缩的可执行文件。直接反汇编只能得到 6098 行且大部分是`db`原始字节。



```
\# 使用deark解压

deark.exe -m pklite ETIN.EXE -o ETIN\_unpacked.exe

\# 输出: ETIN\_unpacked.exe.000.exe (416KB完整EXE)
```

工具：`deark.exe`（需自行安装并加入 PATH）

### 6.2 计算代码段位置



```
\# 读取EXE头

header\_paragraphs = struct.unpack\_from('\<H', data, 8)\[0]  # =371

code\_seg\_offset = header\_paragraphs \* 16  # = 0x1730

\# 入口点

cs = struct.unpack\_from('\<H', data, 0x16)\[0]  # =0x0D36

ip = struct.unpack\_from('\<H', data, 0x14)\[0]  # =0x0800
```

### 6.3 capstone 16 位反汇编



```
from capstone import Cs, CS\_ARCH\_X86, CS\_MODE\_16

md = Cs(CS\_ARCH\_X86, CS\_MODE\_16)

code = exe\_data\[code\_seg\_offset:]

for insn in md.disasm(code, 0):

&#x20;   print(f"0x{insn.address:x}: {insn.mnemonic} {insn.op\_str}")
```

### 6.4 定位 RLE 函数的方法

搜索字节模式`3C FF`（`cmp al, 0xFF`），找到 8 处匹配。分析上下文确认 RLE 解码函数：



* **大函数**（文件偏移 0x212E4-0x21503）：带宽度计数器 bx 的完整 RLE 解码

* 关键指令：


  * `lodsb; cmp al, 0xFF; je` → 行结束判断

  * `test al, 0x80; je` → 透明跳过判断

  * `and ax, 0x7F; add di, ax` → 计算透明跳过

  * `movsb` → 字面量复制

  * `sub ax, 0x140` → 行结束时地址计算（320 宽屏幕）

### 6.5 反汇编的教训

`sub ax, 0x140`最初被误判为 "从下到上绘制"，导致 PASS/EARTH 等图片上下颠倒。实际上：



* 这是**屏幕绘制时**的地址计算（从目标位置向上绘制）

* RLE 数据本身的存储顺序是**从上到下**

* 数据存储顺序 ≠ 屏幕绘制顺序



***

## 七、提取脚本使用方法

### 7.1 最终提取脚本

`scripts/796_etin_extract_transparent.py`

### 7.2 运行



```
cd <项目根目录>
python scripts/796_etin_extract_transparent.py
```

### 7.3 输出



```
extracted/ETIN/images/

├── M\_H/          (84张 64×64 头像)

├── PASS/         (11张 64×64 小头像)

├── EARTH01/      (522张 37×55 地图瓦片)

├── EARTH02/      (762张)

├── EARTH04/      (380张)

├── EARTH05/      (782张)

├── EARTH06/      (807张)

├── EARTH07/      (678张)

├── EARTH08/      (424张)

├── EARTH09/      (252张)

├── WAR01/        (373张 37×55 战斗瓦片)

├── WAR02/        (401张)

├── WAR03/        (447张)

├── WAR04/        (447张)

├── WAR05/        (371张)

├── WAR06/        (379张)

├── WAR07/        (379张)

├── WAR08/        (379张)

├── WAR09/        (415张)

├── OBJS/         (60张 30×30 物体)

└── WORD/         (71张 37×可变 文字)
```

所有图片为**RGBA PNG**，黑色背景（索引 0）已设为透明。



***

## 八、提取成果示例

### 8.1 M\_H 人物头像（格式 A，64×64）



![M\_H头像](images/etin/sample_mh_0000.png)

### 8.2 PASS 小头像（格式 A，64×64）



![PASS头像](images/etin/sample_pass_0000.png)

### 8.3 EARTH 地图瓦片（格式 B，37×55）



![EARTH01瓦片](images/etin/sample_earth01_0100.png)



![EARTH02瓦片](images/etin/sample_earth02_0100.png)

### 8.4 WAR 战斗瓦片（格式 B，37×55）



![WAR01瓦片](images/etin/sample_war01_0050.png)

### 8.5 OBJS 物体图标（格式 B，30×30）



![OBJS物体](images/etin/sample_objs_0010.png)

### 8.6 WORD 图形文字（格式 B，37×40）



![WORD文字](images/etin/sample_word_0000.png)



***

## 九、统计汇总



| 指标         | 数值                            |
| ---------- | ----------------------------- |
| 图片总数       | **8424 张**                    |
| M\_H 头像    | 84                            |
| PASS 小头像   | 11                            |
| EARTH 地图瓦片 | 4607                          |
| WAR 战斗瓦片   | 3591                          |
| OBJS 物体    | 60                            |
| WORD 文字    | 71                            |
| 格式 A 文件    | 2 个（M\_H、PASS）                |
| 格式 B 文件    | 18 个（EARTH×8、WAR×9、OBJS、WORD） |
| 输出格式       | RGBA PNG（透明背景）                |



***

## 十、经验教训

### 10.1 不要假设所有 GRP 用相同格式

M\_H 的 "跳过 / 复制"RLE 完全不适用于 EARTH 等文件。EARTH 用的是 "偏移 + 像素" 格式，每行首字节是列偏移而非 RLE 命令。

**验证方法**：检查组偏移表。EARTH 前 9 组每组仅 4 字节（全 0xFF 空行），第 10 组突然 44 字节 —— 这暴露了格式 B 的结构（空行只有一个 0xFF）。

### 10.2 16 位 DOS 反汇编的正确姿势



1. **先解压**：PKLite/UPX 压缩的 EXE 必须先解压，否则反汇编全是 db

2. **算准代码段偏移**：`header_paragraphs × 16`

3. **用 16 位模式**：capstone `CS_MODE_16`，不是 32 位

4. **搜索特征字节**：`3C FF`（cmp al,0xFF）快速定位 RLE 函数

### 10.3 数据存储顺序 ≠ 屏幕绘制顺序

反汇编中`sub ax, 0x140`是屏幕绘制时从目标位置向上绘制，不代表 RLE 数据存储顺序。所有图片数据都是从上到下存储的。

### 10.4 字面量中的 0xFF 不是行结束

在格式 A 中，只有命令位置的 0xFF 才是行结束符。字面量复制阶段遇到的 0xFF 是像素值，不应当作行结束。

### 10.5 透明色处理

调色板索引 0（黑色）是 DOS 游戏常用的透明色。提取时应保存为 RGBA PNG，将索引 0 像素的 alpha 设为 0。



***

## 十一、未完成项



| 资源                     | 状态  | 说明                              |
| ---------------------- | --- | ------------------------------- |
| ANI-01.GRP             | 未提取 | 332 帧动画脚本（Big5 文本 + 控制命令），非像素数据 |
| DEFINE.GRP             | 未提取 | 474 条结构化定义（w=0,h=0）             |
| TALK-1.GRP             | 未提取 | 1464 条 Big5 中文对话                |
| MUS.GRP                | 未提取 | 38 首自定义音乐                       |
| VOC\_01.GRP            | 未提取 | 5 条 8 位 PCM 音效                  |
| FONT.C16               | 未提取 | 中文字体文件                          |
| *.MMM/*.VT/*.DDD/*.MAP | 未提取 | 地图 / 界面 / 事件数据                  |
| *.DAT/*.TAB/\*.IMG     | 未提取 | 其他数据文件                          |



***

## 十二、相关文件



| 文件                                        | 说明                       |
| ----------------------------------------- | ------------------------ |
| `docs/017_ETIN格式破解全记录.md`                 | 本文档                      |
| `scripts/796_etin_extract_transparent.py` | 最终提取脚本（带透明通道）            |
| `scripts/795_etin_extract_v2.py`          | 提取脚本 v2（无透明通道）           |
| `scripts/786-794_*.py`                    | 反汇编分析和 RLE 调试脚本（10 个）    |
| `work/wdxk/etin/ETIN_unpacked.exe`        | PKLite 解压后的 416KB 完整 EXE |
| `extracted/ETIN/images/`                  | 8424 张提取图片               |



***

*git 提交: bf936ea（初版）→ 7effd13（修正行顺序）→ 3ac43af（透明通道）*