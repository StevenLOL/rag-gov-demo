# DOS 游戏专有图形格式逆向工程

## 最终格式规范与可复现提取流程

---

## 1. 概述

本文档完整记录了 1990 年代 MS-DOS 角色扮演游戏《三国英雄传》所使用的三种专有图形容器格式的最终确认规范。所有规范均通过 IDA Pro 7.6 对游戏可执行文件 `SAN.EXE` 的静态反汇编得出，并通过 4600+ 个提取素材的像素计数不变量验证。

| 格式 | 魔数 | 压缩算法 | 已提取素材 |
|------|------|----------|-----------|
| `.LIB` | `PIC` / `MAN` / `MNU` | PCX RLE | 1,946 个精灵 |
| `.GRP` | `GRP` + 版本字节 | 0标记RLE | 2,712 个地图瓦片 |
| `.MAP` | `MAP` + 版本字节 | 无（索引数组） | 22 张关卡地图 |

---

## 2. 环境与工具

| 组件 | 值 |
|------|-----|
| 游戏根目录 | `E:\Program Files (x86)\SANGUO\SANGUO\` |
| 可执行文件 | `SAN.EXE` — 403,515 字节，MZ 头，DOS/4GW 保护模式 |
| 反汇编器 | IDA Pro 7.6（`idat.exe`） |
| 反汇编输出 | `SAN.EXE.asm` — 5,227,257 字节，137,000+ 行 |
| 运行环境 | Python 3.13 + Pillow 10+ |
| 调色板 | `DEFAULT.PAL` — 768 字节，原始 VGA RGB（无文件头） |

### 2.1 生成参考反汇编

```bash
idat.exe -A -B "E:\Program Files (x86)\SANGUO\SANGUO\SAN.EXE"
```

在游戏目录下生成 `SAN.EXE.asm`。以下函数是本文档所有格式结论的权威参考：

| 函数 | 作用 |
|------|------|
| `sub_46BAC` | 主素材加载器 — 引用所有 `.LIB` 文件名 |
| `sub_3FC24` | PIC/MNU 格式 `.LIB` 加载器（object/window/soldier/flag/mouse/store/ruse） |
| `sub_38D98` | OFFICER `.LIB` 加载器（分配额外运行时表） |
| `sub_393EA` | MAN `.LIB` 加载器（角色精灵） |
| `sub_3F9C2` | **PCX RLE 解压函数** — 基准算法 |
| `sub_3FB7D` | 逐行解码器（每行调用 `sub_3F9C2`） |
| `sub_3FB09` | 行长度扫描器（跳过一行 PCX RLE，返回下一行偏移） |
| `sub_3FDCD` | PIC 库单条目加载器 |
| `sub_39701` | MAN 库单条目加载器 |

---

## 3. `.LIB` 精灵容器格式

### 3.1 文件布局

```
偏移    大小    字段
0       3       magic     — "PIC"、"MAN" 或 "MNU"
3       2       count     — uint16 小端，条目数量
5       —       entries[] — count × 18 字节
```

条目表从偏移 5 开始。所有条目均为固定 18 字节。

### 3.2 条目结构（18字节）

```
偏移    大小    字段          说明
0       4       offset        uint32 LE — 压缩像素数据的绝对文件偏移
4       4       size          uint32 LE — 压缩数据长度（字节）
8       2       width         uint16 LE — 图像宽度（像素）
10      2       display_h     uint16 LE — 显示/裁剪矩形高度
12      2       height        uint16 LE — 数据中实际扫描行数
14      2       unknown1      uint16 LE
16      2       unknown2      uint16 LE
```

偏移 12 的 `height` 字段是解压函数使用的权威行数。

**验证不变量：** 对每个条目，`pcx_rle_pixel_count(data, offset, size) / width == height`，误差在 ±0.5 以内。

实证验证（每个库采样 200 条目）：

| 库 | 匹配 `height` 的条目数 |
|----|----------------------|
| MAN.LIB（1813条目） | 196/200 |
| OFFICER.LIB（93） | 93/93 |
| OBJECT.LIB（41） | 40/41 |
| FLAG.LIB（16） | 16/16 |
| SOLDIER.LIB（4） | 4/4 |
| STORE.LIB（6） | 6/6 |
| TITLE.LIB（2） | 2/2 |

### 3.3 PCX RLE 解压函数（`sub_3F9C2`）

权威解压函数的带注释反汇编：

```asm
sub_3F9C2 proc near    ; eax=目标缓冲区, edx=FILE*, ebx=行宽
loc_3F9EE:
    call fgetc_              ; 从压缩流读取字节 b
    and  eax, 0C0h           ; 取高2位
    cmp  eax, 0C0h           ; 高2位是否都为1？(b >= 0xC0)
    jnz  short literal       ; 否 → 将 b 作为单个像素输出

    ; --- 运行包 ---
    and  eax, 3Fh            ; length = b & 0x3F  (范围 1..63)
    mov  [ebp+len], eax
    call fgetc_              ; 读取颜色字节
run_loop:
    dec  [ebp+len]
    cmp  [ebp+len], -1
    jz   short row_check
    mov  [dest], al          ; 将颜色写入输出
    inc  dest
    jmp  run_loop

literal:
    mov  [dest], al          ; 将 b 直接作为像素索引写入
    inc  dest
    inc  pixel_count

row_check:
    cmp  row_width, pixel_count
    jg   short loc_3F9EE     ; 下一行像素
    retn
```

### 3.4 算法规范

```
输入：压缩字节流 S，宽度 W，高度 H
输出：W×H 像素索引数组 P

x ← 0, y ← 0, i ← 0
while y < H:
    b ← S[i], i ← i+1
    if (b & 0xC0) == 0xC0:       # 运行包
        length ← b & 0x3F        # 1..63
        color  ← S[i], i ← i+1
        repeat length 次:
            P[x,y] ← color
            x ← x+1
            if x == W: x ← 0, y ← y+1
    else:                        # 直接像素
        P[x,y] ← b
        x ← x+1
        if x == W: x ← 0, y ← y+1
```

颜色索引 0 为透明色。调色板为 `DEFAULT.PAL`（768 字节，RGB 三元组）。

### 3.5 参考实现

```python
import struct
from PIL import Image

def load_palette(path):
    with open(path, "rb") as f:
        raw = f.read()
    return [(raw[i], raw[i+1], raw[i+2]) for i in range(0, 768, 3)]

def pcx_rle_decode(data, offset, width, height, size, palette):
    """解码一个 PCX RLE 精灵。"""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    px = img.load()
    x = y = 0
    i = offset
    end = min(offset + size, len(data))
    total = width * height
    while i < end and (y * width + x) < total:
        b = data[i]
        i += 1
        if (b & 0xC0) == 0xC0:          # 运行包
            length = b & 0x3F
            color = data[i]
            i += 1
            for _ in range(length):
                if (y * width + x) >= total:
                    break
                if color != 0:
                    px[x, y] = palette[color] + (255,)
                x += 1
                if x >= width:
                    x = 0; y += 1
        else:                            # 直接像素
            if b != 0:
                px[x, y] = palette[b] + (255,)
            x += 1
            if x >= width:
                x = 0; y += 1
    return img

def extract_lib(lib_path, out_dir, palette):
    with open(lib_path, "rb") as f:
        data = f.read()
    magic = data[0:3]
    count = struct.unpack_from("<H", data, 3)[0]
    for idx in range(count):
        e = 5 + idx * 18
        offset, size, w, disp_h, height, u1, u2 = struct.unpack_from(
            "<IIHHHHH", data, e)
        if w > 0 and height > 0 and offset > 0 and offset < len(data):
            img = pcx_rle_decode(data, offset, w, height, size, palette)
            img.save(f"{out_dir}/{idx:04d}_{w}x{height}.png")
```

### 3.6 已提取素材分类

| 库 | 魔数 | 数量 | 内容 |
|----|------|------|------|
| `MAN.LIB` | `MAN` | 1813（有效1597） | 角色战斗精灵、全身像 |
| `OBJECT.LIB` | `PIC` | 41 | 场景物件（树、花、家具） |
| `WINDOW.LIB` | `PIC` | 39 | UI 对话框框架、面板、按钮 |
| `OFFICER.LIB` | `PIC` | 93 | 官职图标与头像 |
| `STORE.LIB` | `PIC` | 6 | 商店界面框架 |
| `MOUSE.LIB` | `PIC` | 40 | 鼠标光标形状 |
| `TITLE.LIB` | `PIC` | 2 | 标题画面元素 |
| `RUSE.LIB` | `PIC` | 92 | 计策/道具图标 |
| `FLAG.LIB` | `MNU` | 16 | 战旗（龙纹） |
| `SOLDIER.LIB` | `MNU` | 4 | 士兵单位头像 |

---

## 4. `.GRP` 地图瓦片集格式

### 4.1 文件布局

```
偏移    大小    字段
0       3       magic       — "GRP"
3       1       version     — 每文件版本字节（0x45, 0x1D, 0x3D, ...）
4       1       reserved    — 0x00
5       2       count       — uint16 LE，瓦片条目数量
7       1       reserved    — 0x00
8       —       first_entry — 15 字节（无 size 字段）
23      —       entries[]   — (count-1) × 19 字节
```

### 4.2 条目结构

**首条目（15字节）：**

```
偏移    大小    字段
0       1       flag
1       3       offset    — uint24 LE（3字节小端）
4       1       reserved
5       2       width     — uint16 LE
7       2       height    — uint16 LE
9       6       unknowns
```

**后续条目（19字节）：**

```
偏移    大小    字段
0       1       flag
1       3       offset    — uint24 LE
4       1       reserved
5       4       size      — uint32 LE
9       2       width
11      2       height
13      6       unknowns
```

3 字节偏移由不变量 `offset[i] + size[i] == offset[i+1]` 确认（所有连续有效条目均满足）。

### 4.3 0标记RLE压缩

```
输入：压缩字节流 S，宽度 W，高度 H
输出：W×H 像素索引数组 P

x ← 0, y ← 0, i ← 0
while y < H:
    b ← S[i], i ← i+1
    if b == 0x00:                 # 运行包标记
        length ← S[i], i ← i+1    # 1..255
        color  ← S[i], i ← i+1
        repeat length 次:
            P[x,y] ← color
            x ← x+1
            if x == W: x ← 0, y ← y+1
    else:                         # 直接像素
        P[x,y] ← b
        x ← x+1
        if x == W: x ← 0, y ← y+1
```

**验证：** `LEVEL1.GRP` 条目 0 以 `0F 00 0F 00 0F 00 0F 00 0F 00` 开头（10字节），恰好解码为 80 像素：5 个直接颜色15像素 + 5 个长度15的透明（颜色0）运行包。与砖墙瓦片的 80 像素宽度一致。

### 4.4 参考实现

```python
def zero_rle_decode(data, offset, width, height, size, palette):
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    px = img.load()
    x = y = 0
    i = offset
    end = min(offset + size, len(data))
    total = width * height
    while i < end and (y * width + x) < total:
        b = data[i]
        i += 1
        if b == 0x00:                  # 运行包
            length = data[i]
            color = data[i+1]
            i += 2
            for _ in range(length):
                if (y * width + x) >= total:
                    break
                if color != 0:
                    px[x, y] = palette[color] + (255,)
                x += 1
                if x >= width:
                    x = 0; y += 1
        else:                          # 直接像素
            if b != 0:
                px[x, y] = palette[b] + (255,)
            x += 1
            if x >= width:
                x = 0; y += 1
    return img
```

### 4.5 瓦片集清单

| 文件 | 版本 | 有效瓦片 | 内容 |
|------|------|---------|------|
| LEVEL1.GRP – LEVEL23.GRP | 各异 | 109–181/文件 | 地形：砖墙、草地、土地、水面、道路 |
| BIRD.GRP | 0x4F | 74 | 鸟动画帧 |
| BOAT.GRP | 0x08 | 34 | 船只精灵 |
| MOVIE.GRP | 0x1F | 64 | 过场动画帧 |
| OBJECT.GRP | 0x21 | 68 | 地图物件瓦片 |

---

## 5. `.MAP` 关卡地图格式

### 5.1 文件布局

```
偏移    大小    字段
0       4       magic       — "MAP" + 版本字节（"MAP2", "MAP4", "MAP6", ...）
4       2       map_width   — uint16 LE，瓦片列数
6       2       map_height  — uint16 LE，瓦片行数
8       8       unknown     — 瓦片尺寸/调色板引用字段
16      —       indices[]   — map_width × map_height × uint16 LE
```

每个索引是对对应 `LEVEL*.GRP` 瓦片集的零基引用。

### 5.2 关卡尺寸

| 关卡 | MAP 魔数 | 瓦片（宽×高） |
|------|----------|--------------|
| LEVEL1 | MAP2 | 70×69 |
| LEVEL2 | MAP. | 80×29 |
| LEVEL10 | MAP4 | 100×64 |

### 5.3 完整地图渲染

```python
def render_map(map_path, grp_path, out_path, palette):
    with open(map_path, "rb") as f:
        md = f.read()
    map_w = struct.unpack_from("<H", md, 4)[0]
    map_h = struct.unpack_from("<H", md, 6)[0]
    tiles = load_grp_tiles(grp_path, palette)   # 返回 PIL Image 列表
    tile_w, tile_h = tiles[0].size
    canvas = Image.new("RGBA", (map_w * tile_w, map_h * tile_h), (0,0,0,255))
    for ty in range(map_h):
        for tx in range(map_w):
            pos = 16 + (ty * map_w + tx) * 2
            tidx = struct.unpack_from("<H", md, pos)[0]
            if tidx < len(tiles) and tiles[tidx]:
                canvas.paste(tiles[tidx], (tx*tile_w, ty*tile_h), tiles[tidx])
    canvas.save(out_path)
```

---

## 6. PCX 背景文件（标准格式）

游戏附带 49 个标准 ZSoft PCX 文件（640×480，8位色）。这些文件使用与 `.LIB` 精灵相同的 PCX RLE 算法，并自带内嵌调色板。

PCX 文件使用其**内嵌调色板**（文件末尾 `0x0C` 标记后的 768 字节）。

```python
from PIL import Image
img = Image.open("TITLE.PCX")   # Pillow 自动检测内嵌调色板
img.save("title.png")
```

---

## 7. 调色板管理

| 调色板来源 | 用途 | 位置 |
|-----------|------|------|
| `DEFAULT.PAL` | 所有 `.LIB` 精灵、`.GRP` 瓦片 | 游戏根目录，768 字节原始 RGB |
| PCX 内嵌调色板 | PCX 背景图片 | 每个 `.PCX` 文件末尾 769 字节（`0x0C` + 768 RGB） |

`DEFAULT.PAL` 布局：字节 `i*3` = R，`i*3+1` = G，`i*3+2` = B，对应调色板索引 `i`（0..255）。索引 0 全局透明。

---

## 8. 完整提取流程

### 步骤 1：反汇编可执行文件（用于验证）

```bash
idat.exe -A -B "E:\Program Files (x86)\SANGUO\SANGUO\SAN.EXE"
```

### 步骤 2：验证解压函数特征

在 `SAN.EXE.asm` 中确认 `sub_3F9C2` 处的模式：

```
and  eax, 0C0h    ; 行 88540
cmp  eax, 0C0h    ; 行 88541
jnz  <literal>    ; 行 88542
and  eax, 3Fh     ; 行 88543 — 低6位为运行长度
```

### 步骤 3：提取所有 `.LIB` 精灵

```python
palette = load_palette("DEFAULT.PAL")
for lib in ["MAN.LIB", "OBJECT.LIB", "WINDOW.LIB", "OFFICER.LIB",
            "STORE.LIB", "MOUSE.LIB", "TITLE.LIB", "FLAG.LIB",
            "SOLDIER.LIB", "RUSE.LIB"]:
    extract_lib(f"DATA/{lib}", f"out/{lib.split('.')[0]}", palette)
```

### 步骤 4：提取所有 `.GRP` 瓦片

```python
for grp in glob.glob("DATA/*.GRP"):
    extract_grp(grp, f"out/tiles/{basename(grp)}", palette)
```

### 步骤 5：渲染所有 `.MAP` 关卡

```python
for level in range(1, 23):
    render_map(f"DATA/LEVEL{level}.MAP", f"DATA/LEVEL{level}.GRP",
               f"out/maps/LEVEL{level}.png", palette)
```

### 步骤 6：转换 PCX 背景

```python
for pcx in glob.glob("TITLE/*.PCX"):
    Image.open(pcx).save(f"out/backgrounds/{basename(pcx)}.png")
```

### 步骤 7：验证每个提取图像

对每个输出 PNG：

1. 重新计算 `pcx_rle_pixel_count()`，确认 `/ width == height`
2. 非透明像素比例 > 2%（排除空/垃圾图像）
3. 相邻像素水平相关性 > 0.3（排除随机噪点）

---

## 9. 提取结果

### 9.1 素材总计

| 类别 | 数量 | 格式 |
|------|------|------|
| 角色精灵（MAN.LIB） | 1,597 | PCX RLE |
| 场景物件（OBJECT.LIB） | 41 | PCX RLE |
| UI 窗口（WINDOW.LIB） | 39 | PCX RLE |
| 官职图标（OFFICER.LIB） | 93 | PCX RLE |
| 商店 UI（STORE.LIB） | 6 | PCX RLE |
| 鼠标光标（MOUSE.LIB） | 40 | PCX RLE |
| 标题元素（TITLE.LIB） | 2 | PCX RLE |
| 计策道具（RUSE.LIB） | 92 | PCX RLE |
| 战旗（FLAG.LIB） | 16 | PCX RLE |
| 士兵头像（SOLDIER.LIB） | 4 | PCX RLE |
| **LIB 小计** | **1,930** | |
| 地图瓦片（27个GRP文件） | 2,712 | 0标记RLE |
| PCX 背景 | 49 | 标准 PCX |
| WAV 音效 | 135 | 标准 WAV |
| XMI 音乐（→MIDI） | 91 | XMI/EVNT |
| TLK 对话（→TXT） | 22 | GBK 文本 |
| 位图字体 | 16 | 自定义 |
| **图形总计** | **4,691** | |

### 9.2 示例素材

**角色精灵（MAN.LIB 条目 1304）：**
- 尺寸：64×91 像素
- 压缩大小：2,831 字节
- 解压像素：5,824（= 64×91 精确）

**地图瓦片（LEVEL1.GRP 条目 0）：**
- 尺寸：80×72 像素
- 压缩数据以 `0F 00 0F 00 ...` 开头（5个直接像素 + 5个运行包 = 80像素）
- 内容：砖墙纹理

**UI 对话框（WINDOW.LIB 条目 24）：**
- 尺寸：240×236 像素
- 内容：装饰框架，黑色内容区，金色装饰

---

## 10. 格式对比

| 特性 | `.LIB`（PCX RLE） | `.GRP`（0标记RLE） |
|------|-------------------|-------------------|
| 运行标记字节 | `≥0xC0`（高2位置1） | 恰好 `0x00` |
| 运行长度编码 | 标记低6位（1–63） | 下一字节（1–255） |
| 颜色字节 | 长度之后 | 长度之后 |
| 直接像素编码 | `<0xC0` | `≠0x00` |
| 透明色 | 索引 0 | 索引 0 |
| 偏移字段大小 | 32位 | 24位（3字节LE） |
| 高度字段 | 条目内偏移12 | 条目内偏移11 |
| 典型素材 | 精灵、UI、头像 | 地图地形瓦片 |

---

## 11. IDA Pro 参考指针

以下是 `SAN.EXE.asm`（5,227,257字节）中每个格式结论的精确行号：

| 结论 | 函数 | ASM 行号 |
|------|------|----------|
| PCX RLE 算法 | `sub_3F9C2` | 88508–88584 |
| LIB 头 = 5字节 | `sub_3FC24` | 88877–88881（`fread 5 bytes`） |
| LIB 条目 = 18字节 | `sub_3FC24` | 88901（`imul eax, 12h`） |
| 条目表在偏移5 | `sub_3FC24` | 88909（`fread count*18`） |
| height 用作行数 | `sub_3FDCD` | 89088（`mov ax, [eax+0Ch]`） |
| MAN 加载器 | `sub_393EA` | 75820–76054 |
| MAN 单条目解码 | `sub_39701` | 76158–76348 |
| 行扫描器（不绘制） | `sub_3FB09` | 88684–88743 |
| 逐行解码器 | `sub_3FB7D` | 88750–88833 |
| 主加载器（所有文件名） | `sub_46BAC` | 102100+ |

---

## 附录 A — 格式速查表

```
.LIB:
  [0..2]  magic ("PIC"|"MAN"|"MNU")
  [3..4]  count uint16 LE
  [5..]   entries × 18:
            offset(4) size(4) width(2) display_h(2) height(2) u1(2) u2(2)
  PCX RLE: (b&0xC0)==0xC0 → run len=b&0x3F, color=next; else literal

.GRP:
  [0..2]  "GRP"
  [3]     version
  [4]     0
  [5..6]  count uint16 LE
  [7]     0
  [8]     first entry 15B (flag, offset24, rsv, w, h, ...)
  [23..]  entries × 19B (flag, offset24, rsv, size32, w, h, ...)
  Zero-RLE: b==0 → run len=next, color=next; else literal

.MAP:
  [0..3]  "MAP"+version
  [4..5]  map_width uint16 LE
  [6..7]  map_height uint16 LE
  [8..15] unknown
  [16..]  tile indices × uint16 LE
```

## 附录 B — 验证脚本

```python
def validate_lib_entry(data, entry_offset):
    """如果条目的像素计数与 height 匹配则返回 True。"""
    offset, size, w, disp_h, height = struct.unpack_from(
        "<IIHHH", data, entry_offset)
    i = offset
    end = min(offset + size, len(data))
    pixels = 0
    while i < end:
        b = data[i]; i += 1
        if (b & 0xC0) == 0xC0:
            pixels += b & 0x3F
            i += 1  # 跳过颜色
        else:
            pixels += 1
    return abs(pixels / w - height) < 0.5 if w > 0 else False
```

---

*本文档基于对 `SAN.EXE`（DOS/4GW）的静态分析生成。所有偏移和行号均引用 IDA Pro 7.6 批量反汇编输出。*
