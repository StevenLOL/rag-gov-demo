# YOHGAS（妖精战士）资源格式破解全记录

> 游戏：妖精战士（YOHGAS / GUN'SHIP / ロマンスは剣の輝き），PC98移植DOS游戏，天堂鸟资讯发行
> 游戏原名：Romance wa Tsurugi no Kagayaki（DRAMA'TIC FANTASY RPG）
> 文档版本：v2.0（GPC破解完成）
> 最后更新：2026-09-16

---

## 〇、环境准备与快速开始

### 0.1 所需环境

- **Python 3.x**（推荐 miniconda base 环境）
- **Pillow**（PIL）：`pip install pillow`
- **可选**：capstone（反汇编用）：`pip install capstone`

### 0.2 游戏目录结构

```
YOHGAS/
├── GUN'SHIP.EXE      # 主程序（68309字节，DragonDude压缩）
├── GUN'SHIP.ORI      # 主程序原始版（92774字节，未压缩，反汇编用）
├── MARK.IMG          # 启动Logo图（128048字节）
├── PW.IMG            # 启动Logo图（128048字节）
├── CHFONT.BIN        # 中文字体（633KB）
├── BFM/              # 战场地图数据（35个文件，265字节/个）
├── CHARA/            # 角色精灵（165个FGP文件）
├── EFC/              # 特效文件（24个，LZSS压缩）
├── EVT/              # 事件/剧情（238个）
├── FRM/              # 帧（2个）
├── GPC/              # 图标/背景/UI（292个）
├── MAP/              # 地图（114个MFC/MFL文件）
├── OBJE/             # 物体（14个FGP文件）
├── PRM/              # 参数/调色板（4个）
└── USO/              # 未知（58个）
```

### 0.3 快速验证（30秒确认格式正确）

将下面代码保存为 `verify_yohgas.py`，修改路径后运行，应输出3张验证图：

```python
"""YOHGAS格式快速验证脚本 - 运行后生成3张验证图"""
import struct, os
from PIL import Image

GAME_DIR = r'E:\BaiduNetdiskDownload\dos\0001_经典DOS游戏合集(绿色免安装完整硬盘版)@www.emu618.com\YOHGAS'
OUT_DIR = r'C:\tmp\yohgas_verify'
os.makedirs(OUT_DIR, exist_ok=True)

# ===== 1. MARK.IMG 验证 =====
with open(os.path.join(GAME_DIR, 'MARK.IMG'), 'rb') as f:
    data = f.read()
palette = []
for i in range(16):
    r = data[i*3] * 4
    g = data[i*3+1] * 4
    b = data[i*3+2] * 4
    palette.append((r, g, b))
img = Image.new('RGB', (640, 400))
px = img.load()
for y in range(400):
    for x in range(640):
        idx = data[48 + y*320 + x//2]
        idx = (idx >> 4) if (x % 2 == 0) else (idx & 0xF)
        px[x, y] = palette[idx]
img.save(os.path.join(OUT_DIR, '01_mark.png'))
print('1. MARK.IMG -> 01_mark.png (应显示天堂鸟logo)')

# ===== 2. FGP验证（BM01帧0）=====
with open(os.path.join(GAME_DIR, 'CHARA', 'BM01.FGP'), 'rb') as f:
    fdata = f.read()
frame_off = struct.unpack_from('<H', fdata, 24)[0]
pal = []
for i in range(16):
    attr = fdata[frame_off + i*4]
    r = fdata[frame_off + i*4 + 1]
    g = fdata[frame_off + i*4 + 2]
    b = fdata[frame_off + i*4 + 3]
    if g == 0xFF and b == 0xFF:
        pal.append((r, r, r))
    else:
        pal.append((r, g, b))
img_data = fdata[frame_off + 64 : frame_off + 64 + 960]
img = Image.new('RGBA', (32, 30))
px = img.load()
for y in range(30):
    row = img_data[y*16 : y*16 + 16]
    for x in range(32):
        bit = 7 - (x % 8)
        byte_idx = x // 8
        p0 = (row[byte_idx] >> bit) & 1
        p1 = (row[byte_idx + 4] >> bit) & 1
        p2 = (row[byte_idx + 8] >> bit) & 1
        p3 = (row[byte_idx + 12] >> bit) & 1
        idx = (p0 << 3) | (p1 << 2) | (p2 << 1) | p3
        r, g, b = pal[idx]
        px[x, y] = (0,0,0,0) if idx == 0 else (r, g, b, 255)
img.resize((128, 120), Image.NEAREST).save(os.path.join(OUT_DIR, '02_bm01_f0.png'))
print('2. BM01.FGP帧0 -> 02_bm01_f0.png (应显示角色轮廓)')

# ===== 3. GPC验证（@YOGICON）=====
with open(os.path.join(GAME_DIR, 'GPC', '@YOGICON.GPC'), 'rb') as f:
    gdata = f.read()
scans = struct.unpack_from('<H', gdata, 0x10)[0]
pal_off = struct.unpack_from('<H', gdata, 0x14)[0]
img_off = struct.unpack_from('<H', gdata, 0x18)[0]
w = struct.unpack_from('<H', gdata, img_off)[0]
h = struct.unpack_from('<H', gdata, img_off + 2)[0]
bpl = ((w + 7) // 8) * 4
pal = []
for i in range(16):
    pd = struct.unpack_from('<H', gdata, pal_off + 4 + i*2)[0]
    pal.append((((pd>>4)&0xF)<<4, ((pd>>8)&0xF)<<4, (pd&0xF)<<4))
bits = bytearray(bpl * h)
decode_buf = bytearray(1024)
line_words = (bpl + 1) // 2
next_line = line_words * 2 + 1
disp = bytearray(line_words * 2)
pos = img_off + 0x10
p_target = 0
def rb():
    global pos
    v = gdata[pos] if pos < len(gdata) else 0
    pos += 1
    return v
for s in range(scans):
    i = s
    while i < h:
        p = p_target
        while p < next_line:
            ch = rb()
            for _ in range(8):
                if ch & 0x80:
                    ch2 = rb()
                    for _ in range(8):
                        decode_buf[p] = rb() if (ch2 & 0x80) else 0
                        p += 1; ch2 <<= 1
                else:
                    for _ in range(8):
                        decode_buf[p] = 0; p += 1
                ch <<= 1
        p_target = p
        ch = decode_buf[0]
        if ch != 0:
            ch1 = decode_buf[1]; start = 1; p = start + ch
            for _ in range(ch):
                while p < next_line:
                    ch1 ^= decode_buf[p]; decode_buf[p] = ch1; p += ch
                start += 1; p = start
        src = 1; dst = 0
        for _ in range(line_words * 2):
            disp[dst] ^= decode_buf[src]; src += 1; dst += 1
        size = p_target - next_line
        if size > 0:
            decode_buf[:size] = decode_buf[next_line:next_line+size]
        p_target = size
        src = 0
        for j in range(4):
            dst = i * bpl
            for _ in range(line_words // 2):
                b = disp[src]; src += 1
                if b & 0x80: bits[dst] |= 0x10 << j
                if b & 0x40: bits[dst] |= 0x01 << j
                if b & 0x20: bits[dst+1] |= 0x10 << j
                if b & 0x10: bits[dst+1] |= 0x01 << j
                if b & 0x08: bits[dst+2] |= 0x10 << j
                if b & 0x04: bits[dst+2] |= 0x01 << j
                if b & 0x02: bits[dst+3] |= 0x10 << j
                if b & 0x01: bits[dst+3] |= 0x01 << j
                dst += 4
        i += scans
img = Image.new('RGBA', (w, h))
px = img.load()
for y in range(h):
    for x in range(w):
        bi = y * bpl + x // 2
        idx = (bits[bi] >> 4) & 0xF if (x % 2 == 0) else bits[bi] & 0xF
        r, g, b = pal[idx]
        px[x, y] = (0,0,0,0) if idx == 0 else (r, g, b, 255)
img.save(os.path.join(OUT_DIR, '03_yogicon.png'))
print('3. @YOGICON.GPC -> 03_yogicon.png (应显示图标工具栏)')
print('\n验证完成！请查看', OUT_DIR)
```

**预期输出**：
1. `01_mark.png` — 天堂鸟资讯有限公司logo重复排列
2. `02_bm01_f0.png` — 蓝色调角色精灵（4倍放大）
3. `03_yogicon.png` — 游戏图标工具栏（剑、弓、闪电、头盔等）

---

## 一、游戏概况

- **平台**：PC98 → DOS移植
- **发行**：天堂鸟资讯有限公司
- **主程序**：`GUN'SHIP.EXE`（68309字节，DragonDude压缩）、`GUN'SHIP.ORI`（92774字节，未压缩原始版）
- **程序标识**："GUN'SHIP.EXE for PC-9801V (Version 3.45)"
- **资源特征**：所有资源文件头部均为 `PC98)` 开头，确认PC98血统

## 二、已破解格式

### 2.1 MARK.IMG / PW.IMG — 启动Logo图

**文件大小**：128048字节 = 48字节头 + 128000字节图像数据（640×400×4bpp = 128000）

**字节级结构**：
```
偏移  长度  内容
0     48    调色板（16色 × 3字节）
48    128000 图像数据（640×400，4bpp打包）
```

**调色板详解（每色3字节）**：
```
字节0: R通道（0-63，PC98 6位DAC，需 ×4 转0-255）
字节1: G通道（0-63，需 ×4）
字节2: B通道（0-63，需 ×4）
```
> 注意：PC98的DAC是6位的，值范围0-63。VGA是8位DAC（0-255）。转换公式：`vga = pc98 * 4`。

**图像数据格式**：
- 4bpp打包（packed）：每字节存2个像素
- 高4位 = 左像素，低4位 = 右像素（high_first）
- 每行640像素 = 320字节
- 无行填充，无压缩

**完整提取代码**：
```python
import struct
from PIL import Image

def extract_mark_img(path, out_path):
    with open(path, 'rb') as f:
        data = f.read()
    
    # 解析调色板
    palette = []
    for i in range(16):
        r = data[i*3] * 4
        g = data[i*3+1] * 4
        b = data[i*3+2] * 4
        palette.append((r, g, b))
    
    # 解析图像
    width, height = 640, 400
    img = Image.new('RGB', (width, height))
    px = img.load()
    for y in range(height):
        for x in range(width):
            byte_val = data[48 + y * 320 + x // 2]
            if x % 2 == 0:
                idx = (byte_val >> 4) & 0xF
            else:
                idx = byte_val & 0xF
            px[x, y] = palette[idx]
    
    img.save(out_path)
    return palette
```

**验证方法**：
- 输出图像应为640×400
- 内容为"天堂鸟资讯有限公司"logo重复排列（约4×4个logo）
- 颜色：蓝色文字、白色背景

**常见错误**：
| 症状 | 原因 | 修复 |
|------|------|------|
| 颜色偏暗 | 忘记×4，直接用0-63当0-255 | `r = data[i*3] * 4` |
| 左右像素颠倒 | 用了low_first | 高4位=左像素 |
| 图像倾斜 | 行宽计算错误 | 每行320字节（640/2） |

**提取结果**：
- `mark.png` — 天堂鸟资讯有限公司logo重复排列
- `pw.png` — 同上（内容相同）

### 2.2 FGP — 角色/物体精灵图（核心突破）

**文件头结构（24字节 + 帧偏移表）**：
```
偏移  长度  内容
0     16    魔数 "PC98)FGP v1.0\0\0\0" 或 "PC98)FGP v1.1\0\0\0"
16    2     方向数（通常=2）
18    2     每方向帧数
20    2     颜色数相关参数
22    2     图像高度-1（通常=29，即30像素高）
24    N*2   帧偏移表（LE16数组，最后一个值重复作为结束标记）
```

**每帧结构（固定1024字节）**：
```
偏移  长度  内容
0     64    调色板（16色 × 4字节）
64    960   图像数据（2个32×30×4bpp图像，按行交错4位平面）
```

**调色板详解（每色4字节）**：
```
字节0: 属性字节
       0x00 = 普通颜色
       0x80 = 特殊颜色（如高亮）
       0x0D, 0x02 = 其他属性
字节1: R通道（0-255，有效值）
字节2: G通道（部分颜色未初始化，值=0xFF）
字节3: B通道（部分颜色未初始化，值=0xFF）
```

**调色板解析规则**：
```python
if g == 0xFF and b == 0xFF:
    # 灰度颜色：R=G=B=字节1
    color = (r, r, r)
else:
    # 真彩色：直接使用(R, G, B)
    color = (r, g, b)
```
> 为什么G/B会是0xFF？PC98游戏开发时，调色板可能只初始化了R通道，G/B通道的内存残留为0xFF。这是PC98游戏的常见现象。

**图像数据格式（按行交错4位平面）**：
```
960字节 = 2个32×30×4bpp图像（i0和i1）
├── i0: 字节0-479（480字节 = 30行 × 16字节/行）
└── i1: 字节480-959（480字节 = 30行 × 16字节/行）

每行16字节的布局：
字节0-3:   位平面0（32像素 = 4字节，MSB优先）
字节4-7:   位平面1
字节8-11:  位平面2
字节12-15: 位平面3

像素索引计算：
idx = (平面0_bit << 3) | (平面1_bit << 2) | (平面2_bit << 1) | 平面3_bit
```

**像素位提取示例**（第x像素）：
```python
byte_idx = x // 8          # 0-3
bit_pos = 7 - (x % 8)      # MSB优先：位7=最左像素
plane0_bit = (row[byte_idx] >> bit_pos) & 1
plane1_bit = (row[byte_idx + 4] >> bit_pos) & 1
plane2_bit = (row[byte_idx + 8] >> bit_pos) & 1
plane3_bit = (row[byte_idx + 12] >> bit_pos) & 1
idx = (p0 << 3) | (p1 << 2) | (p2 << 1) | p3
```

**完整提取代码**：
```python
import struct, os
from PIL import Image

def extract_fgp(filepath, out_dir):
    with open(filepath, 'rb') as f:
        data = f.read()
    
    magic = data[:16]
    directions = struct.unpack_from('<H', data, 16)[0]
    frames_per_dir = struct.unpack_from('<H', data, 18)[0]
    
    # 读取帧偏移表
    frame_offsets = []
    pos = 24
    while True:
        off = struct.unpack_from('<H', data, pos)[0]
        pos += 2
        if frame_offsets and off == frame_offsets[-1]:
            break  # 重复值=结束标记
        frame_offsets.append(off)
        if pos >= len(data):
            break
    
    # 注意：部分文件（如BM01）实际帧数 > 偏移表条目数
    # 按文件大小计算总帧数：(文件大小 - 头部) / 1024
    header_size = 24 + len(frame_offsets) * 2
    total_frames = (len(data) - header_size) // 1024
    # 补充偏移表中缺失的帧
    for i in range(len(frame_offsets), total_frames):
        frame_offsets.append(header_size + i * 1024)
    
    base_name = os.path.splitext(os.path.basename(filepath))[0]
    
    for fi, frame_off in enumerate(frame_offsets):
        # 解析调色板
        palette = []
        for i in range(16):
            attr = data[frame_off + i*4]
            r = data[frame_off + i*4 + 1]
            g = data[frame_off + i*4 + 2]
            b = data[frame_off + i*4 + 3]
            if g == 0xFF and b == 0xFF:
                palette.append((r, r, r, 255))
            else:
                palette.append((r, g, b, 255))
        
        # 解析图像数据（2个32x30图像）
        img_data = data[frame_off + 64 : frame_off + 64 + 960]
        
        for sub in range(2):  # i0, i1
            sub_data = img_data[sub*480 : (sub+1)*480]
            img = Image.new('RGBA', (32, 30))
            px = img.load()
            for y in range(30):
                row = sub_data[y*16 : y*16 + 16]
                for x in range(32):
                    bit = 7 - (x % 8)
                    bi = x // 8
                    p0 = (row[bi] >> bit) & 1
                    p1 = (row[bi + 4] >> bit) & 1
                    p2 = (row[bi + 8] >> bit) & 1
                    p3 = (row[bi + 12] >> bit) & 1
                    idx = (p0 << 3) | (p1 << 2) | (p2 << 1) | p3
                    if idx == 0:
                        px[x, y] = (0, 0, 0, 0)  # 透明
                    else:
                        px[x, y] = palette[idx]
            
            out_name = '%s_f%02d_i%d.png' % (base_name, fi, sub)
            img.save(os.path.join(out_dir, out_name))
    
    return total_frames
```

**关键验证步骤**：
1. **单色平面验证**：将平面0单独作为32×30单色图像渲染，应有清晰角色轮廓（无条纹）。如果平面0就是噪点，说明数据布局完全错误。
2. **调色板验证**：BM01帧0的调色板R值应为 `[0, 30, 1, 225, 6, 0, 2, 0, 4, 0, 8, 0, 18, 0, 28, 0]`。
3. **帧数验证**：BM01.FGP大小=8228字节，头部36字节，(8228-36)/1024=8帧。但偏移表只列4帧，后4帧需补充。

**常见错误**：
| 症状 | 原因 | 修复 |
|------|------|------|
| 水平条纹 | 用了4平面连续存储（平面0全部→平面1→...） | 改用按行交错（每行16字节=4平面×4字节） |
| 颜色偏灰 | 未处理G/B=0xFF的灰度情况 | 判断G==0xFF且B==0xFF时用R作灰度 |
| 只有一半帧 | 只按偏移表提取，忽略文件末尾的帧 | 按文件大小/1024计算总帧数 |
| 左右颠倒 | 用了LSB优先（位0=最左） | 用MSB优先（位7=最左） |
| 960字节当1个图 | 未拆分为i0/i1 | 960=2×480，每个480字节是一个32×30图 |

**提取结果**：
- 共提取 **1451张** 角色精灵PNG（CHARA目录158个角色 + OBJE目录14个物体）
- 每帧输出2个图像（i0和i1）
- 输出目录：`fgp_final/`

**文件命名规律**：
| 前缀 | 含义 | 示例 |
|------|------|------|
| BMxx | 男性角色 | BM01-BM20 |
| FExx | 女性角色/敌人 | FE01-FE20 |
| FNxx | 女性角色（数量最多） | FN01-FN50 |
| FTxx | 女性角色 | FT01-FT10 |
| FIxx | 物品/道具 | FI01-FI10 |
| FMxx | 男性角色 | FM01-FM10 |
| BTxx | 战斗相关 | BT01-BT10 |
| SHIP | 飞船 | SHIP.FGP |
| EXPLO/THUNDER/V_FIRE | 特效 | - |
| J_* | 接口/光标 | - |

### 2.3 GPC — 图标/背景/UI图形（核心突破）

**参考来源**：CSDN博客《PC98游戏图片格式（GPC）》— https://blog.csdn.net/superarhow/article/details/1575219
> 该博客详细描述了IDLES公司GPC格式的完整算法。YOHGAS的GPC是该格式的变体，有2处关键差异（见下文）。

**文件头结构**：
```
偏移  长度  内容
0     16    魔数 "PC98)GPCFILE   \0"（注意GPCFILE后有3个空格+1个\0）
16    2     scans（扫描次数，通常=1；隔行扫描时=2，先偶数行后奇数行）
18    2     保留（=0）
20    2     palette_offset（调色板偏移，通常=48）
22    2     保留（=0）
24    2     image_offset（图像数据偏移，通常=84）
26    22    保留（=0）
```

**调色板区（偏移palette_offset=48开始）**：
```
偏移  长度  内容
+0    2     colorcount（颜色数，LE16，通常=16）
+2    2     transcolor（透明色索引，LE16，通常=2）
+4    32    16个颜色，每个2字节
```

**调色板颜色格式（每色2字节，4位RGB）**：
```
字节0（高字节）: GGGG RRRR  （G高4位，R中4位）
字节1（低字节）: BBBB ????  （B低4位，低4位未用）

解析：
g = ((paldata >> 8) & 0xF) << 4   # 取高字节高4位，左移4转8位
r = ((paldata >> 4) & 0xF) << 4   # 取高字节低4位，左移4
b = (paldata & 0xF) << 4          # 取低字节低4位，左移4
```
> 注意：4位颜色值范围0-15，左移4后变为0-240（步长16），不是0-255。这是PC98 12色/16色模式的标准做法。

**图像区（偏移image_offset=84开始）**：
```
偏移  长度  内容
+0    2     width（图像宽度，LE16）
+2    2     height（图像高度，LE16）
+4    12    其他参数（含义待确认，可能是X/Y偏移、热区等）
+16   N     RLE压缩数据（从image_offset+0x10开始）
```

**尺寸计算**：
```python
bpl = ((width + 7) // 8) * 4      # 每行字节数（4平面，每平面(width+7)//8字节）
line_words = (bpl + 1) // 2       # 每行字数（16位字）
next_line_pos = line_words * 2 + 1  # 每行解码目标位置（含1字节前缀）
```

**RLE压缩算法（双层游程编码）**：

这是GPC格式的核心。压缩数据按行解码，每行的解码过程：

```
1. 读取控制字节A
2. A的每一位（从位7到位0）控制一个8字节组：
   - 位=0：该组8字节全为0，直接填充
   - 位=1：读取控制字节B，B的每一位控制组内1个字节：
     - B的位=0：该字节为0
     - B的位=1：从流中读取1字节作为目标值
3. 重复直到解码字节数 >= next_line_pos
```

**伪代码**：
```python
p = p_target  # 关键：从上次的p_target继续，不是从0开始！
while p < next_line_pos:
    ch = read_byte()  # 控制字节A
    for j in range(8):  # A的8位，从高位开始
        if ch & 0x80:
            ch2 = read_byte()  # 控制字节B
            for k in range(8):  # B的8位
                if ch2 & 0x80:
                    decode_buf[p] = read_byte()  # 非零字节
                else:
                    decode_buf[p] = 0
                p += 1
                ch2 <<= 1
        else:
            for k in range(8):
                decode_buf[p] = 0  # 8个零字节
                p += 1
        ch <<= 1
p_target = p  # 保存当前位置
```

**后处理三步（关键！）**：

**第1步：异或解密（post_decode_1）**
```python
ch = decode_buf[0]   # 步长
if ch != 0:
    ch1 = decode_buf[1]  # 初始值
    start = 1
    p = start + ch
    for j in range(ch, 0, -1):
        while p < next_line_pos:
            ch1 ^= decode_buf[p]
            decode_buf[p] = ch1
            p += ch
        start += 1
        p = start
```
> 这是一种增量异或解密。decode_buf[0]是步长，decode_buf[1]是初始值。从start+ch开始，每隔ch个字节进行异或累积。

**第2步：与disp_buf异或（post_decode_2，增量解码）**
```python
src = 1
dest = 0
for j in range(line_words * 2):
    disp_buf[dest] ^= decode_buf[src]
    src += 1
    dest += 1
```
> disp_buf是跨行的累积缓冲区。每行的新数据与disp_buf异或，结果存回disp_buf。这意味着图像是增量编码的——每行只存储与上一行的差异。disp_buf初始为全0。

**第3步：移动剩余数据（post_decode_3）**
```python
size = p_target - next_line_pos
if size > 0:
    decode_buf[:size] = decode_buf[next_line_pos:next_line_pos + size]
p_target = size
```
> RLE解码可能多读了几个字节（因为每次处理8字节组）。多余的字节属于下一行，移到缓冲区开头，下一行从p_target=size继续解码。

**4平面转4bpp**：
```python
src = 0
for plane in range(4):  # 平面0,1,2,3
    dest = i * bpl  # 关键：YOHGAS不垂直翻转！用i*bpl，不是(height-i-1)*bpl
    for k in range(line_words // 2):
        bits = disp_buf[src]
        src += 1
        # 每个字节控制8个像素的当前平面位
        if bits & 0x80: bits_buffer[dest]     |= 0x10 << plane  # 像素0高4位
        if bits & 0x40: bits_buffer[dest]     |= 0x01 << plane  # 像素0低4位
        if bits & 0x20: bits_buffer[dest + 1] |= 0x10 << plane  # 像素1高4位
        if bits & 0x10: bits_buffer[dest + 1] |= 0x01 << plane  # 像素1低4位
        if bits & 0x08: bits_buffer[dest + 2] |= 0x10 << plane  # 像素2高4位
        if bits & 0x04: bits_buffer[dest + 2] |= 0x01 << plane  # 像素2低4位
        if bits & 0x02: bits_buffer[dest + 3] |= 0x10 << plane  # 像素3高4位
        if bits & 0x01: bits_buffer[dest + 3] |= 0x01 << plane  # 像素3低4位
        dest += 4
```
> disp_buf的布局：前line_words/2字节=平面0，接下来=平面1，再=平面2，最后=平面3。
> 每个字节的8位对应8个像素（MSB优先），每2个像素占1字节4bpp（高4位=左像素）。

**与博客IDLES GPC的2处关键差异**：

| 差异点 | 博客IDLES GPC | YOHGAS GPC | 错误症状 |
|--------|--------------|------------|----------|
| p_target初始化 | 循环外初始化为decode_buf，每行继续 | **同左**（最初实现错误地每行从0开始） | 竖条纹、数据错位 |
| 行存储顺序 | `dest = (height-i-1)*bpl`（垂直翻转） | `dest = i*bpl`（**不翻转**） | 图像上下颠倒、文字镜像 |

> **差异1详解**：博客代码中`p_target`在所有循环外初始化为`decode_buf`（即偏移0）。每行RLE解码从`p_target`开始，post_decode_3后`p_target`更新为剩余数据长度。下一行从这个位置继续解码。如果每行都从0开始，会导致每行数据错位，产生竖条纹。

> **差异2详解**：博客代码在4平面转4bpp时使用`dest = (height - i - 1) * bpl`，将第i行存储到倒数第i行（垂直翻转）。YOHGAS不需要翻转，直接用`dest = i * bpl`。如果用了博客的翻转，森林场景的角色会倒挂，LOGO文字会镜像。

**完整提取代码**：
```python
import struct, os
from PIL import Image

def decode_gpc(data):
    # 解析头部
    scans = struct.unpack_from('<H', data, 0x10)[0]
    palette_offset = struct.unpack_from('<H', data, 0x14)[0]
    image_offset = struct.unpack_from('<H', data, 0x18)[0]
    width = struct.unpack_from('<H', data, image_offset)[0]
    height = struct.unpack_from('<H', data, image_offset + 2)[0]
    
    if width <= 0 or height <= 0 or width > 2048 or height > 2048:
        return None
    
    bpl = ((width + 7) // 8) * 4
    
    # 解析调色板
    palette = []
    for i in range(16):
        paldata = struct.unpack_from('<H', data, palette_offset + 4 + i * 2)[0]
        g = ((paldata >> 8) & 0xF) << 4
        r = ((paldata >> 4) & 0xF) << 4
        b = (paldata & 0xF) << 4
        palette.append((r, g, b))
    
    # 初始化缓冲区
    bits_buffer = bytearray(bpl * height)
    decode_buf = bytearray(1024)
    line_words = (bpl + 1) // 2
    next_line_pos = line_words * 2 + 1
    disp_buf = bytearray(line_words * 2)
    
    data_pos = image_offset + 0x10
    p_target = 0  # 关键：循环外初始化
    
    def read_byte():
        nonlocal data_pos
        if data_pos >= len(data):
            return 0
        b = data[data_pos]
        data_pos += 1
        return b
    
    for s in range(scans):
        i = s
        while i < height:
            # === RLE解码 ===
            p = p_target  # 从上次位置继续
            while p < next_line_pos:
                ch = read_byte()
                for j in range(8):
                    if ch & 0x80:
                        ch2 = read_byte()
                        for k in range(8):
                            decode_buf[p] = read_byte() if (ch2 & 0x80) else 0
                            p += 1
                            ch2 <<= 1
                    else:
                        for k in range(8):
                            decode_buf[p] = 0
                            p += 1
                    ch <<= 1
            p_target = p
            
            # === post_decode_1: 异或解密 ===
            ch = decode_buf[0]
            if ch != 0:
                ch1 = decode_buf[1]
                start = 1
                p = start + ch
                for j in range(ch, 0, -1):
                    while p < next_line_pos:
                        ch1 ^= decode_buf[p]
                        decode_buf[p] = ch1
                        p += ch
                    start += 1
                    p = start
            
            # === post_decode_2: 与disp_buf异或 ===
            src = 1
            dest = 0
            for j in range(line_words * 2):
                disp_buf[dest] ^= decode_buf[src]
                src += 1
                dest += 1
            
            # === post_decode_3: 移动剩余数据 ===
            size = p_target - next_line_pos
            if size > 0:
                decode_buf[:size] = decode_buf[next_line_pos:next_line_pos + size]
            p_target = size
            
            # === 4平面转4bpp ===
            src = 0
            for plane in range(4):
                dest = i * bpl  # YOHGAS: 不垂直翻转
                for k in range(line_words // 2):
                    bits = disp_buf[src]
                    src += 1
                    if bits & 0x80: bits_buffer[dest]     |= 0x10 << plane
                    if bits & 0x40: bits_buffer[dest]     |= 0x01 << plane
                    if bits & 0x20: bits_buffer[dest + 1] |= 0x10 << plane
                    if bits & 0x10: bits_buffer[dest + 1] |= 0x01 << plane
                    if bits & 0x08: bits_buffer[dest + 2] |= 0x10 << plane
                    if bits & 0x04: bits_buffer[dest + 2] |= 0x01 << plane
                    if bits & 0x02: bits_buffer[dest + 3] |= 0x10 << plane
                    if bits & 0x01: bits_buffer[dest + 3] |= 0x01 << plane
                    dest += 4
            
            i += scans
    
    # 转换为RGBA图像
    img = Image.new('RGBA', (width, height))
    px = img.load()
    for y in range(height):
        for x in range(width):
            byte_idx = y * bpl + x // 2
            if x % 2 == 0:
                idx = (bits_buffer[byte_idx] >> 4) & 0xF
            else:
                idx = bits_buffer[byte_idx] & 0xF
            r, g, b = palette[idx]
            px[x, y] = (0, 0, 0, 0) if idx == 0 else (r, g, b, 255)
    
    return img
```

**验证步骤**：
1. **头部验证**：`data[:16]`应为`b'PC98)GPCFILE   \x00'`
2. **调色板验证**：A001.GPC的前4色应为 `(224,144,96), (208,128,80), (240,176,144), (240,240,240)`（棕/肤色系）
3. **尺寸验证**：@YOGICON.GPC应为448×64，A001.GPC应为112×64，G001.GPC应为560×240
4. **内容验证**：
   - @YOGICON.GPC → 图标工具栏（剑、弓、闪电、头盔、龙卷风、蛇、三角形、方形、X、十字）
   - LOGO.GPC → 日文"ロマンスは剣の輝き" + 英文"DRAMATIC FANTASY RPG"
   - G001.GPC → 森林场景，角色正立站在林间小道
   - FAIRY.GPC → "FAIRY TALE"启动画面

**常见错误排查**：
| 症状 | 原因 | 修复 |
|------|------|------|
| 竖条纹、完全不可识别 | p_target每行从0开始，未保持连续性 | p_target在循环外初始化，post_decode_3后更新 |
| 图像上下颠倒、角色倒挂 | 用了博客的`(height-i-1)*bpl` | 改用`i*bpl` |
| 文字镜像（左右翻转） | 同上（垂直翻转导致视觉上也像水平翻转） | 同上 |
| 颜色偏暗/偏色 | 调色板4位未左移4，或RGB顺序错 | `g=(pd>>8&0xF)<<4, r=(pd>>4&0xF)<<4, b=(pd&0xF)<<4` |
| 解码越界/崩溃 | decode_buf大小不足（1024够吗？） | 确保decode_buf≥1024字节，最大行next_line_pos≈513 |
| 只有上半部分图像 | scans>1时未处理隔行扫描 | 外层循环`for s in range(scans)`，行步长=scans |
| 图像有残留/鬼影 | disp_buf未初始化为0 | `disp_buf = bytearray(line_words * 2)` |

**提取结果**：
- 共提取 **292张** GPC图形PNG，全部成功（0失败）
- 输出目录：`gpc_final/`

**尺寸分布**：
| 尺寸 | 数量 | 内容 |
|------|------|------|
| 16×2 | 少量 | 极小元素（如G160S） |
| 64×64 | 多个 | 小图标（A009等） |
| 96×96 | 多个 | 中等图标（F01A等） |
| 112×64 | 多个 | 按钮（A001-A008） |
| 448×64 | 1 | @YOGICON图标工具栏 |
| 576×64 / 576×128 | 2 | YOGICON/YOGICON2 |
| 208×144 ~ 640×400 | 大量 | 背景图、UI框架、场景 |

**典型文件说明**：
| 文件 | 尺寸 | 内容 |
|------|------|------|
| @YOGICON.GPC | 448×64 | 游戏图标工具栏（2行×多列图标） |
| LOGO.GPC | 464×177 | 标题logo（日文+英文） |
| FAIRY.GPC | 640×400 | "FAIRY TALE"启动画面（全屏） |
| G001.GPC | 560×240 | 森林场景背景（角色+光线） |
| G010.GPC | 464×240 | 场景背景 |
| G022.GPC | 512×288 | 场景背景 |
| G031.GPC | 208×144 | 小场景 |
| G103.GPC | 312×240 | 场景 |
| SWORD.GPC | 592×264 | 剑相关UI/菜单 |
| FRAME.GPC | 536×269 | 对话框框架 |
| BATL_ICN.GPC | 608×160 | 战斗图标栏 |
| FREM.GPC | 608×352 | 框架/菜单 |
| IDES95.GPC | 616×291 | 95年IDES标识 |
| ED_01.GPC | 232×368 | 结局画面 |
| A001-A009.GPC | 112×64/64×64 | 按钮/小图标 |

## 三、分析中的格式

### 3.2 EFC — 特效文件

**头部**：前2字节=0x1F40=8000（解压大小）
**解压**：LZSS v3（10位偏移/6位长度/MSB优先）可解压出约8000字节
**状态**：解压成功，但渲染格式未确认。

### 3.3 MFC / MFL — 地图格式

**头部**：`PC98)MFC v1.0` / `PC98)MFL v1.0`
**状态**：头部已识别，图像数据未破解。

### 3.4 其他目录

| 目录 | 数量 | 内容推测 |
|------|------|----------|
| BFM | 35 | 背景/帧 |
| CHARA | 165 | 角色精灵（已提取） |
| EFC | 24 | 特效（LZSS解压成功） |
| EVT | 238 | 事件/剧情 |
| FRM | 2 | 帧 |
| GPC | 292 | 图标/背景/UI（已提取292张） |
| MAP | 114 | 地图（MFC/MFL） |
| OBJE | 14 | 物体 |
| PRM | 4 | 参数/调色板 |
| USO | 58 | 未知 |

## 四、破解方法论总结

### 4.1 FGP格式破解的关键转折

**第一阶段：盲目猜测（全部失败）**
- 4bpp打包（所有尺寸64×30/48×40/32×60等）→ 噪点
- VGA位平面（4平面连续存储）→ 平面0有轮廓，平面1-3有水平条纹
- LZSS解压（多种参数）→ 解压但噪点
- PC98 8像素块位平面（平面交错）→ 批量提取1826帧后，用户明确指出"都是错的"

**第二阶段：反汇编分析**
- IDA/capstone反汇编GUN'SHIP.ORI
- 确认VGA渲染使用4平面+数据旋转0/1/2/3（端口0x3CE寄存器0x04）
- 发现VGA写模式3相关设置（设置/重置寄存器=0F，位平面掩码=0F）
- 测试循环右移平面1/2/3 → 未解决条纹

**第三阶段：关键发现（单色平面验证法）**
- **平面0单独作为32×30单色图像有清晰角色轮廓**（无条纹）
- 这说明前120字节是有效的单色图像数据，数据布局方向正确
- 960字节 = 8个120字节块，但只有块0有清晰轮廓
- 分析4个平面的行数据关系：P1行0=P0行20（完全相同），但无简单映射规律

**第四阶段：最终突破（按行交错）**
- 测试按行交错布局（每行16字节=4平面×4字节）
- 2个32×30×4bpp图像连续存储（i0=字节0-479，i1=字节480-959）
- **成功显示角色轮廓！**
- 批量提取1451张图像，确认布局正确

### 4.2 GPC格式破解的关键转折

**参考来源**：CSDN博客《PC98游戏图片格式（GPC）》（https://blog.csdn.net/superarhow/article/details/1575219）

**第一阶段：直接套用博客算法（竖条纹）**
- 头部结构匹配：scans@0x10, palette_offset@0x14, image_offset@0x18
- 调色板解析正确（4位RGB，G高4位/R中4位/B低4位）
- 但解码输出竖条纹，完全不可识别

**第二阶段：定位bug（p_target连续性）**
- 逐行对比博客C代码和Python实现
- 发现博客代码中`p_target`在循环外初始化为`decode_buf`
- 每行RLE解码从`p_target`开始（不是从0开始！）
- post_decode_3将剩余数据移到decode_buf开头，p_target更新为剩余长度
- 最初实现每行从p=0开始，导致每行数据错位，产生竖条纹
- 修复后：A001.GPC显示红色椭圆（按钮），@YOGICON显示图标工具栏

**第三阶段：方向修复（不垂直翻转）**
- 博客代码使用`dest = (height-i-1)*bpl`（垂直翻转）
- YOHGAS的G001.GPC（森林场景）角色倒挂，LOGO文字镜像
- 测试4种翻转组合（fv0/fv1 × fh0/fh1）后确认：`dest = i*bpl`（不翻转）正确
- 博客的翻转可能是IDLES游戏的特定实现，YOHGAS不需要

**关键经验**：
1. **参考实现要逐行对比指针逻辑**：p_target的连续性是RLE增量解码的关键，不能每行重置
2. **翻转方向需验证**：博客代码的翻转不一定适用于所有GPC变体，要通过真实图像验证
3. **调色板格式确认**：4位RGB的排列顺序（G:R:B）需通过已知图像验证

### 4.3 通用经验教训

1. **单色平面验证法**：当4bpp组合有条纹时，先单独渲染每个平面的1bpp单色图像。如果某个平面有清晰轮廓，说明数据布局方向正确，只是组合方式有误。这是FGP突破的关键。

2. **按行交错 vs 4平面连续**：VGA位平面有两种常见存储方式：
   - 4平面连续存储：平面0全部数据 → 平面1 → 平面2 → 平面3
   - 按行交错：每行包含所有4个平面的数据（如FGP的每行16字节=4平面×4字节）
   - PC98移植游戏常用按行交错

3. **不要被"结束标记"迷惑**：FGP帧偏移表的重复值可能只列出部分帧，文件末尾可能还有额外帧。按文件大小/每帧大小计算总帧数更可靠。

4. **调色板未初始化处理**：PC98游戏的调色板可能只有R通道有效，G/B通道未初始化为0xFF。解析时需判断G/B是否为0xFF，若是则用R作为灰度值。

5. **反汇编印证但不直接给答案**：反汇编能确认VGA渲染机制（4平面、数据旋转、写模式3），但具体的数据组织方式仍需通过图像验证。

6. **用户反馈是最准确的验证**：当用户明确说"都是错的"时，不要在错误方向上继续优化，要回到基础数据重新分析。

7. **参考实现的变体差异**：即使格式名称相同（如GPC），不同游戏的实现可能有细微差异（翻转方向、p_target连续性等）。必须通过实际图像验证，不能盲目套用。

8. **增量解码的状态保持**：RLE+异或的增量解码中，跨行状态（p_target、disp_buf）必须保持连续，不能每行重置。这是GPC竖条纹bug的根本原因。

## 五、提取脚本索引

| 脚本 | 用途 | 状态 |
|------|------|------|
| `scripts/1515_yohgas_img.py` | MARK.IMG/PW.IMG提取 | 完成 |
| `scripts/1594_yohgas_full_extract.py` | FGP全量提取（按行交错布局） | 完成 |
| `scripts/1593_yohgas_palette_test.py` | FGP调色板解析测试 | 参考 |
| `scripts/1583_yohgas_render_func.py` | VGA渲染函数反汇编分析 | 参考 |
| `scripts/1602_yohgas_gpc_final.py` | GPC全量提取（292张，正确方向） | 完成 |
| `scripts/1600_yohgas_gpc_v4.py` | GPC解码v4（修复p_target连续性） | 参考 |

> 快速验证脚本见本文档"〇、环境准备与快速开始"部分，可直接复制运行。

## 六、输出成果汇总

### 6.1 已提取资源

| 格式 | 数量 | 输出目录 | 说明 |
|------|------|----------|------|
| MARK.IMG/PW.IMG | 2张 | `mark.png`, `pw.png` | 启动Logo（640×400） |
| FGP角色精灵 | 1451张 | `fgp_final/` | 角色/物体/特效（32×30，每帧2图） |
| GPC图标/背景/UI | 292张 | `gpc_final/` | 图标栏、背景、按钮、框架（16×2~640×400） |
| **合计** | **1745张** | | |

### 6.2 目录结构

```
extracted/YOHGAS_妖精战士/
├── mark.png              # 启动Logo
├── pw.png                # 启动Logo
├── fgp_final/            # 1451张角色精灵
│   ├── BM01_f00_i0.png   # 命名：文件_帧_子图
│   ├── BM01_f00_i1.png
│   └── ...
├── gpc_final/            # 292张GPC图形
│   ├── @YOGICON_GPC.png  # 图标工具栏
│   ├── LOGO_GPC.png      # 标题logo
│   ├── G001_GPC.png      # 森林背景
│   └── ...
├── GUNSHIP.ORI           # 反汇编用主程序（复制到简单路径）
├── ida_analysis.txt      # IDA反汇编结果v1
└── ida_analysis2.txt     # IDA反汇编结果v2
```

## 七、待完成

- [x] MARK.IMG/PW.IMG启动Logo提取
- [x] FGP角色精灵格式破解（1451张）
- [x] GPC图标/背景/UI格式破解（292张）
- [ ] MFC/MFL地图格式破解（114个文件）
- [ ] EFC特效渲染格式确认（24个文件，LZSS已解压）
- [ ] BFM背景格式破解（35个文件，265字节/个，疑似战场地图数据）
- [ ] FGP i0/i1具体含义确认（2方向？2帧？上下半部分？）
- [ ] CHFONT.BIN中文字体提取（633KB）
- [ ] OBJE目录14个FGP文件提取（物体精灵）
- [ ] EVT事件/剧情文件解析（238个）
- [ ] USO未知格式分析（58个）

## 八、反汇编关键信息（供后续破解参考）

**程序**：GUN'SHIP.ORI（92774字节，未压缩原始版）
**标识**："GUN'SHIP.EXE for PC-9801V (Version 3.45)"

**关键函数地址**（文件偏移，代码段从偏移32开始）：
- VGA位平面加载函数：+44354附近（4平面连续存储，通过0x3C4端口位平面掩码选择平面）
- VGA渲染函数：+9350-9900（4平面分别设置数据旋转值0/1/2/3，端口0x3CE寄存器0x04）
- 写模式3设置：+9721（设置/重置=0F）、+9776（位平面掩码=0F）、+9853（数据旋转/函数选择=0x1803）
- GPC错误消息：+85922-86275（"Face GPC Load Error!"等）
- FGP错误消息："FGP Memory ERROR!", "FGP Load ERROR!"
- MFC错误消息："MFC Load ERROR!"
- BFM错误消息："BFM Load ERROR!"

**VGA渲染机制**：
- 4个位平面通过序列控制器端口0x3C4的位平面掩码寄存器（ax=0x102/0x202/0x402/0x802）选择
- 数据旋转寄存器（端口0x3CE，寄存器0x04）设置为0/1/2/3，对应4个平面
- 写模式3相关：设置/重置寄存器=0F，位平面掩码=0F，数据旋转/函数选择=0x1803

> 注意：反汇编确认了VGA渲染使用4平面+数据旋转，但FGP的实际数据组织方式（按行交错）是通过单色平面验证法发现的，反汇编并未直接给出答案。
