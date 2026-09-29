# Stoneshard 游戏资源提取

> 游戏：Stoneshard（石质碎片）  
> 引擎：GameMaker Studio  
> 日期：2026-09-13  
> 输出目录：`C:\src\InformationSecurity\dosgames\extracted\Stoneshard\extracted_assets\`

---

## 一、成果总览

| 资源类型 | 数量 | 大小 |
|---------|------|------|
| 纹理页 (Texture Pages) | 160 个 | ~140MB |
| 精灵 (Sprites) | 17,043 个 / 152,001 帧 | 251MB |
| 音频 (OGG) | 1,085 个 | 120MB |
| **总计** | | **516.5MB** |

---

## 二、文件结构

### 2.1 EXE 自解压

Stoneshard.exe（521.4MB）是自解压 RAR 包：
- PE 部分：715KB（偏移 0xAEA00 之前）
- Overlay：520.7MB，RAR5 签名 `52 61 72 21 1a 07 01 00`

截取 overlay 为 `.rar`，7z 解压得到 57 个文件 / 895MB。

### 2.2 核心文件

```
Stoneshard/
├── data.win          (107MB)  — GameMaker 数据文件
├── audiogroup1.dat   (57.8MB)
├── audiogroup3.dat   (26.8MB)
├── audiogroup4.dat   (210.7MB)
├── audiogroup5.dat   (10.5MB)
├── audiogroup6.dat   (3.9MB)
├── audiogroup7.dat   (3.8MB)
├── StoneShard.exe    (166MB)
├── fonts/            — 中文17.7MB + 日文18.5MB
└── *.mp3             — 22首原声带
```

### 2.3 data.win 块结构

FORM 容器，GEN8 版本字段 = 4353 (0x1101)：

| 块名 | 含义 | 数量 |
|------|------|------|
| SPRT | 精灵 | 17,044 |
| SOND | 声音 | 2,573 |
| ROOM | 房间 | 1,065 |
| OBJT | 对象 | 9,584 |
| SCPT | 脚本 | 9,885 |
| BGND | 背景 | 17 |
| FONT | 字体 | 5 |
| STRG | 字符串 | 42,304 |
| TPAG | 纹理项描述符 | 152,037 |
| TXTR | 纹理页 | 160 |

---

## 三、纹理页格式

### 3.1 TXTR 块

```
TXTR块:
├── uint32 count = 160              ← 纹理页数量
├── uint32[160] desc_ptrs          ← 描述符指针数组
└── 纹理页描述符 (28字节 = 7×uint32):
    ├── [0] v0
    ├── [1] 0xffffffff
    ├── [2] rel_off
    ├── [3] width
    ├── [4] height
    ├── [5] v5
    └── [6] data_abs               ← 纹理页数据绝对偏移
```

纹理页尺寸：大部分 2048×2048，部分 512×512 / 1024×2048，少量 64×64 / 8×8 / 256×512。

### 3.2 三层封装

```
┌─────────────────────────────────────┐
│ 外层头 (12字节)                      │
│   magic = "2zoq" (0x716f7a32 LE)    │
│   width  (uint16 LE)                │
│   height (uint16 LE)                │
│   uncomp_size (uint32 LE)           │
├─────────────────────────────────────┤
│ bzip2 压缩数据 (签名 "BZh9")         │
│   ┌─────────────────────────────┐   │
│   │ 内层头 (12字节)              │   │
│   │   magic = "fioq" (QOI)      │   │
│   │   width  (uint16 LE)        │   │
│   │   height (uint16 LE)        │   │
│   │   data_size (uint32 LE)     │   │
│   ├─────────────────────────────┤   │
│   │ GameMaker 自定义 QOI 数据    │   │
│   └─────────────────────────────┘   │
└─────────────────────────────────────┘
```

### 3.3 GameMaker 自定义 QOI 操作码

与标准 QOI 完全不同：

| 操作码 | 范围 | 掩码 | 说明 |
|--------|------|------|------|
| INDEX | 0x00-0x3F | 0xC0 | 索引查找，idx = b1 & 0x3F |
| RUN_8 | 0x40-0x5F | 0xE0 | run = b1 & 0x1F（0-31） |
| RUN_16 | 0x60-0x7F | 0xE0 | 2字节，run = ((b1&0x1F)<<8 \| b2) + 32 |
| DIFF_8 | 0x80-0xBF | 0xC0 | r/g/b 各2位有符号差分（-2..1） |
| DIFF_16 | 0xC0-0xDF | 0xE0 | 2字节，r(5位) g(4位) b(4位) |
| DIFF_24 | 0xE0-0xEF | 0xF0 | 3字节，r/g/b/a 各5位有符号差分 |
| COLOR | 0xF0-0xFF | 0xF0 | 位掩码决定读取通道 |

- **索引哈希**：`(r ^ g ^ b ^ a) & 63`
- **索引数组**：存储 **RGBA** 顺序

### 3.4 DIFF_24 位布局

```
字节: b1       b2             b3
      └┬┘ ┌───┴───┐ ┌────┬───┘
       dr  dg    db  db   da

dr = ((b1 & 0x0F) << 1) | ((b2 >> 7) & 1)
dg = (b2 >> 2) & 0x1F
db = ((b2 & 0x03) << 3) | ((b3 >> 5) & 0x07)
da = b3 & 0x1F
```

5位字段有符号扩展：`val = val - 32 if val >= 16 else val`

### 3.5 COLOR 通道掩码

```
b1 & 0x0F:
  bit3 (8) → 读 R
  bit2 (4) → 读 G
  bit1 (2) → 读 B
  bit0 (1) → 读 A
按 R→G→B→A 顺序，每通道1字节
```

### 3.6 纹理页示例

纹理页6（2048×2048）——包含树木、建筑废墟、栅栏、雕像等场景元素：

![纹理页6](file:///C:/src/InformationSecurity/dosgames/extracted/Stoneshard/extracted_assets/texture_pages/tpage_006.png)

---

## 四、精灵提取

### 4.1 SPRT 块

```
SPRT块:
├── uint32 count = 17044
└── uint32[count] sprite_ptrs   ← 指针数组直接从 sprt_off+4 开始
```

### 4.2 精灵描述符

```
偏移  字段
0     name_ptr        (uint32)
4     width           (uint32)
8     height          (uint32)
...
84    num_frames      (uint32)
88    first_frame_ptr (uint32) ← 直接指向 TPAG 条目
```

### 4.3 TPAG 条目（22字节）

```
┌──────────────────────────────┐
│ src_x    uint16  纹理页源X    │
│ src_y    uint16  纹理页源Y    │
│ src_w    uint16  源宽度       │
│ src_h    uint16  源高度       │
│ dst_x    uint16  目标画布X    │
│ dst_y    uint16  目标画布Y    │
│ dst_w    uint16  目标画布宽度 │
│ dst_h    uint16  目标画布高度 │
│ bound_w  uint16  边界宽度     │
│ bound_h  uint16  边界高度     │
│ page_idx int16   纹理页索引   │
└──────────────────────────────┘
```

### 4.4 帧裁剪流程

1. 从 TPAG 获取 src_x/y/w/h 和 page_idx
2. 从纹理页裁剪 `(src_x, src_y, src_x+src_w, src_y+src_h)`
3. 若 dst 尺寸不同，paste 到 dst_w×dst_h 画布的 (dst_x, dst_y)
4. 保存 PNG

### 4.5 精灵示例

sprite_0（31×38，94帧动画）第0帧——角色像素画：

![精灵示例](file:///C:/src/InformationSecurity/dosgames/extracted/Stoneshard/extracted_assets/sprites/sprite_0/frame_0000.png)

---

## 五、音频提取

### 5.1 audiogroup*.dat 结构

```
FORM头 (8字节): "FORM" + size
AUDO头 (8字节): "AUDO" + size
AUDO数据:
├── uint32 count
└── uint32[count] offsets  ← 每个指向OGG文件开始
```

偏移量 i 到偏移量 i+1 之间的数据即为一个 OGG 文件。

### 5.2 提取统计

| 音频组 | 总数 | 提取 | 成功率 |
|--------|------|------|--------|
| audiogroup1 | 76 | 76 | 100% |
| audiogroup3 | 52 | 52 | 100% |
| audiogroup4 | 2291 | 836 | 36% |
| audiogroup5 | 86 | 58 | 67% |
| audiogroup6 | 61 | 61 | 100% |
| audiogroup7 | 2 | 2 | 100% |
| **总计** | **2568** | **1085** | **42%** |

audiogroup4/5 部分条目非标准 OGG，待进一步分析。

---

## 六、核心算法

### 6.1 QOI 解码器

```python
def decode_gm_qoi(qoi_data, width, height):
    pixels = bytearray(width * height * 4)
    index = bytearray(64 * 4)  # RGBA
    r, g, b, a = 0, 0, 0, 255
    p = 0
    run = 0
    out = 0

    for _ in range(width * height):
        if run > 0:
            run -= 1
        elif p < len(qoi_data):
            b1 = qoi_data[p]; p += 1

            if (b1 & 0xC0) == 0x00:          # INDEX
                idx = (b1 & 0x3F) * 4
                r, g, b, a = index[idx:idx+4]
            elif (b1 & 0xE0) == 0x40:        # RUN_8
                run = b1 & 0x1F
            elif (b1 & 0xE0) == 0x60:        # RUN_16
                b2 = qoi_data[p]; p += 1
                run = ((b1 & 0x1F) << 8 | b2) + 32
            elif (b1 & 0xC0) == 0x80:        # DIFF_8
                dr = (b1>>4)&3; dr -= 4 if dr>=2 else 0
                dg = (b1>>2)&3; dg -= 4 if dg>=2 else 0
                db = b1&3;    db -= 4 if db>=2 else 0
                r=(r+dr)&0xFF; g=(g+dg)&0xFF; b=(b+db)&0xFF
            elif (b1 & 0xE0) == 0xC0:        # DIFF_16
                b2 = qoi_data[p]; p += 1
                dr = b1&0x1F; dr -= 32 if dr>=16 else 0
                dg = (b2>>4)&0xF; dg -= 16 if dg>=8 else 0
                db = b2&0xF; db -= 16 if db>=8 else 0
                r=(r+dr)&0xFF; g=(g+dg)&0xFF; b=(b+db)&0xFF
            elif (b1 & 0xF0) == 0xE0:        # DIFF_24
                b2 = qoi_data[p]; b3 = qoi_data[p+1]; p += 2
                dr = ((b1&0x0F)<<1)|((b2>>7)&1); dr -= 32 if dr>=16 else 0
                dg = (b2>>2)&0x1F; dg -= 32 if dg>=16 else 0
                db = ((b2&0x03)<<3)|((b3>>5)&0x07); db -= 32 if db>=16 else 0
                da = b3&0x1F; da -= 32 if da>=16 else 0
                r=(r+dr)&0xFF; g=(g+dg)&0xFF; b=(b+db)&0xFF; a=(a+da)&0xFF
            elif (b1 & 0xF0) == 0xF0:        # COLOR
                if b1 & 8: r = qoi_data[p]; p += 1
                if b1 & 4: g = qoi_data[p]; p += 1
                if b1 & 2: b = qoi_data[p]; p += 1
                if b1 & 1: a = qoi_data[p]; p += 1

            idx = ((r ^ g ^ b ^ a) & 0x3F) * 4
            index[idx:idx+4] = r, g, b, a

        pixels[out:out+4] = r, g, b, a  # RGBA 输出给 PIL
        out += 4

    return pixels
```

### 6.2 纹理页解码

```python
import bz2, struct
from PIL import Image

# 外层头12字节后是bzip2
bz_data = data[data_abs + 12 : data_abs + data_size]
raw = bz2.decompress(bz_data)

# 内层头12字节
qoi_w = struct.unpack_from('<H', raw, 4)[0]
qoi_h = struct.unpack_from('<H', raw, 6)[0]
qoi_len = struct.unpack_from('<I', raw, 8)[0]

pixels = decode_gm_qoi(raw[12:12+qoi_len], qoi_w, qoi_h)
img = Image.frombytes('RGBA', (qoi_w, qoi_h), bytes(pixels))
```

---

## 七、脚本与参考

| 脚本 | 功能 |
|------|------|
| `scripts/774_stoneshard_qoi_rgba.py` | 纹理页解码 |
| `scripts/775_stoneshard_sprites_final.py` | 精灵提取 |
| `scripts/777_stoneshard_audio_fix.py` | 音频提取 |

参考源码：`E:\dev\UndertaleModTool\`（QoiConverter.cs / UndertaleSprite.cs / UndertaleTexturePageItem.cs）

---

## 八、待完善

- audiogroup4/5 剩余约1483个非标准OGG音频
- BGND（17背景）、ROOM（1065房间）、SCPT（9885脚本）、FONT（5字体）
