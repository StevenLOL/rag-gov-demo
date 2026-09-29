# 超时空英雄传说 (SUPER) 资源提取全记录

> 宇峻科技 1996 年 DOS SLG，LE 格式 32 位 DOS 扩展程序。
> 提取日期：2026-09-14
> 状态：**全部主要CEL已正确提取（v3，6209张）**，SPELL/音频待深入
> 版本：v3 — 修正IND条带双格式（行索引 + u8全局引用）

---

## 1. 游戏概述

| 项目 | 内容 |
|------|------|
| 游戏原名 | 超时空英雄传说 |
| 英文名 | SUPER |
| 研发 | 宇峻科技 |
| 发行年份 | 1996 |
| 平台 | DOS (DOS4GW 32位扩展) |
| 游戏类型 | SLG 战略角色扮演 |
| 可执行格式 | LE (Linear Executable) |
| 主程序 | SUPER.EXE (548KB) + DOS4GW.EXE |

---

## 2. 文件结构

游戏目录共 53 个文件，核心资源文件：

### 2.1 图像归档 (.CEL) — 12 个

| 文件 | 大小 | 内容 | 提取状态 |
|------|------|------|----------|
| EMAN.CEL | 2.4 MB | 敌人动画（96记录×13条带） | ✅ 2030张(去重) |
| PMAN.CEL | 1.5 MB | 人物动画（75记录×13条带） | ✅ 1500张(去重) |
| HEAD.CEL | 2.1 MB | 角色头像 | ✅ 364张(去重) |
| SPELL.CEL | 6.4 MB | 法术特效 | ⚠️ 格式待解 |
| MENU.CEL | 971 KB | 菜单/UI | ✅ 579张 |
| STORY.CEL | 291 KB | 剧情图片 | ⚠️ 部分提取 |
| TREE.CEL | 457 KB | 树木/植物 | ✅ 271张(去重) |
| GROUND.CEL | 898 KB | 地形瓦片 | ✅ 1025张(去重) |
| INST.CEL | 102 KB | 设施/建筑 | ⚠️ 部分提取 |
| ICON.CEL | 41 KB | 图标 | ✅ 165张(去重) |
| MAIN.CEL | 63 KB | 主界面 | ⚠️ 部分提取 |
| LARGE.CEL | 1.5 MB | 大图/场景瓦片 | ✅ 275张(去重) |

### 2.2 索引文件 (.IND) — 3 个

| 文件 | 大小 | 内容 |
|------|------|------|
| EMAN.IND | 10 KB | EMAN 索引（96记录×13条带） |
| PMAN.IND | 8 KB | PMAN 索引（75记录×13条带） |
| FILE.IND | 150 B | 文件索引 |

### 2.3 调色板

| 文件 | 大小 | 内容 |
|------|------|------|
| MAP.PAL | 2304 B | 256色×3字节 (**6bit VGA，需×4**) |

### 2.4 音频

| 文件 | 大小 | 内容 |
|------|------|------|
| MIDI.BIN | 144 KB | MIDI 音乐 |
| SOUND.BIN | 2.5 MB | 音效 |

---

## 3. 核心格式总览

SUPER的图像资源采用**三层索引结构**：

```
IND索引文件
  └─ 条带(8字节) → 两种格式
       ├─ 格式1: CEL行索引偏移 → 6字节条目数组 → 帧数据(4字节头+RLE)
       └─ 格式2: 8个u8全局引用编号 → CEL全局索引表 → 帧数据(4字节头+RLE)

CEL图像归档
  └─ 开头全局索引表(u16条目数 + (u32 offset, u16 size)条目数组)
       └─ 图像数据区(4字节头+RLE)
```

---

## 4. IND 索引格式（关键突破）

### 4.1 文件头

```
@0: u16 记录数 (EMAN=96, PMAN=75)
```

### 4.2 记录结构

每条记录 **108 字节** = **13 个条带(strip)** × **8 字节**。

### 4.3 条带的两种格式（v3核心发现）

#### 格式1：行索引格式（大角色动画）

```c
struct StripRowIdx {
    u16 width;          // 参考宽度
    u16 y;              // Y坐标
    u16 cel_offset;     // CEL内行索引偏移（>0x1000）
    u16 reserved;       // 通常为0
};
```

`cel_offset` 指向 CEL 中的行索引（6字节条目数组），解析后得到多帧动画。
- EMAN: 约72个条带使用此格式
- PMAN: 约53个条带使用此格式
- 图像尺寸通常为 64×48 或 64×64

**示例（rec000_s00）**：
```
IND条带: 40 00 00 00 c0 10 00 00
@4=0x10c0 → CEL行索引 → 19帧骑鸟角色动画
```

#### 格式2：u8全局引用格式（Q版战斗精灵）

```c
struct StripU8Ref {
    u8 ref[8];          // 8个全局索引表条目编号，0=空帧
};
```

条带的8字节直接是8个u8，每个值是CEL开头全局索引表的条目编号，0表示空帧。
- EMAN: 约1176个条带使用此格式
- PMAN: 约922个条带使用此格式
- 引用的图像通常是 48×35 的Q版角色战斗精灵

**示例（rec022_s03）**：
```
IND条带: 16 17 18 18 19 1a 00 1b
拆成u8: [22, 23, 24, 24, 25, 26, 0, 27]
→ 引用全局索引表条目22,23,24,24,25,26,空,27
→ 8帧动画（第24帧重复，第7帧空）
```

### 4.4 格式识别方法

```python
def is_row_index_format(strip_data, cel, cel_size):
    cel_off = struct.unpack_from('<H', strip_data, 4)[0]
    if cel_off < 0x1000 or cel_off + 6 > cel_size:
        return False
    # 检查前两个条目是否有效
    size0 = struct.unpack_from('<H', cel, cel_off)[0]
    off0 = struct.unpack_from('<I', cel, cel_off+2)[0]
    if not (0 < off0 < cel_size and 0 < size0 < 100000):
        return False
    if cel_off + 12 > cel_size:
        return False
    off1 = struct.unpack_from('<I', cel, cel_off+8)[0]
    return 0 < off1 < cel_size and off1 > off0
```

**判断逻辑**：@4作为u16 > 0x1000 且能解析出有效行索引 → 格式1；否则 → 格式2。

### 4.5 破解过程（如何发现格式2）

**问题现象**：v2版本中rec022/025/040/070等记录提取出大量碎片图像（如rec022_s03_f054只有零星像素）。

**排查步骤**：
1. 检查问题条带的IND原始数据：`16 17 18 18 19 1a 00 1b`
2. 发现@4=0x1a19=6681，作为CEL偏移指向的数据无法解析为标准行索引
3. 将8字节拆成u8：`[22, 23, 24, 24, 25, 26, 0, 27]` — 连续数字！
4. 猜测这些是全局索引表的条目编号
5. 渲染全局索引表条目22-27 → 得到完整的48×35 Q版角色动画
6. 验证：rec022所有条带的u8值组成1-40的连续编号范围，对应40个战斗精灵帧

**关键洞察**：条带的8字节不一定是4个u16，也可能是8个u8。当@4值较小时（<0x1000），应怀疑是u8数组格式。

---

## 5. CEL 全局索引表格式

### 5.1 结构

EMAN.CEL 和 PMAN.CEL 开头都有一个全局索引表：

```
@0: u16 entry_count        // 条目数 (EMAN=2904, PMAN=2129)
@2: 开始 entry_count 个条目，每个6字节
    条目N: u32 data_offset  // 图像数据偏移
             u16 data_size   // 图像数据大小
```

**验证连续性**：
- EMAN: 2904条目 × 6字节 = 17424字节，@2+17424 = 0x4412 = 第一个图像偏移 ✓
- PMAN: 2129条目 × 6字节 = 12774字节，@2+12774 = 0x31e8 = 第一个图像偏移 ✓
- 全表检查：0 gaps, 0 overlaps，图像完全连续

### 5.2 与无IND的CEL格式对比

HEAD/MENU/TREE/GROUND/ICON/LARGE 使用相同的格式（称为格式D），只是没有IND文件：

```
@0: u16 image_count
@2: 开始 image_count 个条目 (u32 offset, u16 size)
```

### 5.3 常见错误

**错误**：将条目格式误认为 `(u16 size, u32 offset)`。
**正确**：条目格式是 `(u32 offset, u16 size)`。

验证方法：条目N的 offset + size 应等于条目N+1的 offset。

---

## 6. CEL 行索引格式（格式1使用）

IND格式1的`cel_offset`指向的行索引是6字节条目数组：

```
条目N: u16 compressed_size + u32 data_offset
```

- `data_offset`: 帧N的像素数据偏移
- `compressed_size`: 帧大小参考值（可用下一帧offset - 当前offset得到精确大小）
- 结束条件：offset超出CEL范围或size=0

**帧数据提取**：
```python
entries = parse_row_index(cel_off)
for f, (offset, size) in enumerate(entries):
    if f < len(entries)-1:
        next_off = entries[f+1][1]
        frame_data = cel[offset:next_off]  # 精确大小
    else:
        frame_data = cel[offset:offset+size]
```

---

## 7. 图像像素格式

### 7.1 帧数据结构

```
@0: u16 width_minus_1    // 实际宽度 = 值+1
@2: u16 height_minus_1   // 实际高度 = 值+1
@4: RLE压缩像素数据
```

常见尺寸：64×48（头值63,47）、64×64、48×48、48×35。

### 7.2 RLE 解码算法（最终确认）

```python
def rle_decode(data):
    out = []
    i = 0
    while i < len(data):
        count = data[i]; i += 1
        if count == 0:
            continue                    # 无操作（跳过1字节）
        elif count < 0x80:
            out.extend([data[i]] * count)  # 重复下一字节count次
            i += 1
        else:  # count >= 0x80
            n = count - 0x80
            out.extend(data[i:i+n])        # 复制n个字面量
            i += n
    return out
```

**三条规则**：
| count值 | 含义 | 操作 |
|---------|------|------|
| 0 | 无操作 | 跳过1字节 |
| 1..127 | 重复 | 下一字节重复count次（**不+1**） |
| 128..255 | 字面量 | 复制后续count-128字节 |

### 7.3 验证数据

| 帧 | 头尺寸 | 解码像素 | 目标像素 | 差值 |
|----|--------|----------|----------|------|
| 0 | 64×48 | 3069 | 3072 | -3 |
| 1 | 64×48 | 3068 | 3072 | -4 |
| 2 | 64×48 | 3070 | 3072 | -2 |
| 6 | 64×48 | 3071 | 3072 | -1 |

差值1-8像素为行末填充字节，不影响渲染。

### 7.4 透明处理

- 像素值 `0` = 透明（渲染时跳过，输出alpha=0）
- 其他值通过 MAP.PAL 查找 RGB 颜色

---

## 8. 调色板格式 (MAP.PAL)

```
2304字节 = 256色 × 3字节
每色: u8 R, u8 G, u8 B (6bit VGA, 值0-63)
```

**关键：必须 ×4 转8bit**（0-63 → 0-252）。

```python
pal = [(r*4, g*4, b*4) for r, g, b in palette_data]
```

**验证**：调色板全局最大值 R=63, G=63, B=63，确认是6bit VGA。
**常见错误**：直接使用原始值导致颜色偏暗。

---

## 9. 反汇编辅助验证 (SUPER.EXE)

### 9.1 LE 格式参数

- 代码对象 rbase = 0x10000
- 代码段文件起始 = 0x18250
- VA 范围 = 0x10000 - 0x78000
- 入口点 EIP = 0x5d148

### 9.2 关键函数

| 函数 | VA | 功能 |
|------|-----|------|
| Blit | 0x3c3a2 | 图像绘制：4字节头(w-1,h-1)+像素，支持透明/直接复制 |
| 着色 | 0x4221a | 颜色替换：0xef/0xec替换为指定颜色 |
| 调色板映射 | 0x41fae | 像素映射：0/0xfd/0xef特殊处理，其他查表 |

### 9.3 Blit 函数确认的格式

```asm
mov ax, [esi]      ; w-1
inc ax             ; 实际宽度
mov [ebp-8], ax
mov ax, [esi+2]    ; h-1
inc ax             ; 实际高度
; 透明模式: 逐像素检查，0跳过
; 直接模式: rep movsd/movsb 批量复制
```

### 9.4 字符串与符号

- `eman.cel` @ VA 0x745cf
- `pman.cel` @ VA 0x745bd
- `map.pal` @ VA 0x75bdc
- C++ 调试符号：`InitManPictureIndex()`, `ReadImage()`, `InitReadAllImage()`, `ReadHeadImage()`, `InitSpellData()`

---

## 10. 完整提取流程（可复现）

### 10.1 准备

```python
from pathlib import Path
from PIL import Image
import struct, hashlib

game_dir = Path(r'...\SUPER')
cel = (game_dir / 'EMAN.CEL').read_bytes()
ind = (game_dir / 'EMAN.IND').read_bytes()
pal_data = (game_dir / 'MAP.PAL').read_bytes()
pal = [(pal_data[i*3]*4, pal_data[i*3+1]*4, pal_data[i*3+2]*4) for i in range(256)]
cel_size = len(cel)
```

### 10.2 读取全局索引表

```python
global_count = struct.unpack_from('<H', cel, 0)[0]

def get_global_entry(n):
    if n >= global_count: return None
    off = 2 + n * 6
    offset = struct.unpack_from('<I', cel, off)[0]
    size = struct.unpack_from('<H', cel, off+4)[0]
    return (offset, size)
```

### 10.3 RLE解码 + 渲染

```python
def rle_decode(data):
    out = []
    i = 0
    while i < len(data):
        c = data[i]; i += 1
        if c == 0: continue
        if c < 0x80:
            if i < len(data):
                out.extend([data[i]] * c)
                i += 1
        else:
            n = c - 0x80
            out.extend(data[i:i+n])
            i += n
    return out

def render_img(offset, size):
    row_data = cel[offset:offset+size]
    if len(row_data) < 4: return None
    w = struct.unpack_from('<H', row_data, 0)[0] + 1
    h = struct.unpack_from('<H', row_data, 2)[0] + 1
    if w > 256 or h > 256: return None
    px = rle_decode(row_data[4:])
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    p = img.load()
    for y in range(h):
        for x in range(w):
            idx = y*w + x
            if idx < len(px):
                c = px[idx] & 0xff
                if c != 0:
                    r, g, b = pal[c]
                    p[x, y] = (r, g, b, 255)
    return img
```

### 10.4 解析IND并提取

```python
rec_count = struct.unpack_from('<H', ind, 0)[0]
rec_size = (len(ind) - 2) // rec_count

seen = set()  # MD5去重

for rec in range(rec_count):
    for strip in range(13):
        rec_off = 2 + rec * rec_size + strip * 8
        strip_data = ind[rec_off:rec_off+8]

        if is_row_index_format(strip_data, cel, cel_size):
            # 格式1: 行索引
            cel_off = struct.unpack_from('<H', strip_data, 4)[0]
            entries = parse_row_index(cel_off)
            for f, (offset, size) in enumerate(entries):
                img = render_img(offset, size)
                save_unique(img, f'rec{rec:03d}_s{strip:02d}_f{f:03d}')
        else:
            # 格式2: u8全局引用
            for f, ref in enumerate(strip_data):
                if ref == 0: continue
                ge = get_global_entry(ref)
                if ge:
                    offset, size = ge
                    img = render_img(offset, size)
                    save_unique(img, f'rec{rec:03d}_s{strip:02d}_g{ref:03d}')
```

### 10.5 无IND的CEL提取

```python
count = struct.unpack_from('<H', cel, 0)[0]
for i in range(count):
    off = 2 + i * 6
    offset = struct.unpack_from('<I', cel, off)[0]
    size = struct.unpack_from('<H', cel, off+4)[0]
    img = render_img(offset, size)
    save_unique(img, f'{i:04d}')
```

---

## 11. 提取成果汇总（v3 最终版）

### 11.1 总统计

| 类别 | 格式 | 去重后PNG |
|------|------|-----------|
| EMAN（敌人动画） | 行索引72条带 + u8引用1176条带 | 2,030 |
| PMAN（人物动画） | 行索引53条带 + u8引用922条带 | 1,500 |
| HEAD（头像） | 格式D | 364 |
| MENU（菜单UI） | 格式D | 579 |
| GROUND（地形） | 格式D | 1,025 |
| LARGE（大图/瓦片） | 格式D | 275 |
| TREE（树木） | 格式D | 271 |
| ICON（图标） | 格式D | 165 |
| **总计** | | **6,209** |

### 11.2 版本对比

| 版本 | EMAN | PMAN | 总计 | 问题 |
|------|------|------|------|------|
| v1 | 33771 | 25069 | ~61800 | 颜色偏暗(6bit未×4)，大量重复 |
| v2 | 1660 | 1303 | 5642 | 颜色正确，但u8引用格式误解析为行索引，产生碎片 |
| v3 | 2030 | 1500 | 6209 | 双格式正确识别，全部完整图像 |

### 11.3 输出目录

```
extracted/SUPER_超时空英雄传说_v3/
├── eman/           # 敌人动画
│   ├── recXXX_sYY_fZZZ.png   # 行索引格式帧
│   └── recXXX_sYY_gNNN.png   # u8引用格式帧
├── pman/           # 人物动画
├── head/           # 头像
├── menu/           # 菜单UI
├── ground/         # 地形瓦片
├── large/          # 大图/场景瓦片
├── tree/           # 树木
└── icon/           # 图标
```

---

## 12. 破解历程与教训

### 12.1 RLE算法破解（第5章详细）

**走过的弯路**：
1. 简单字节RLE（高位1=重复）→ 全黑
2. u16命令对（count+color）→ count=129超出行宽
3. PackBits（n<128重复n+1）→ 解码1461像素，渲染条纹
4. B变体（count<0x80重复count+1）→ 差217像素
5. 4bpp/1bpp格式 → 全部失败

**突破点**：反汇编Blit函数确认4字节头(w-1,h-1)，然后系统测试6种RLE变体，发现count=0跳过、count<0x80重复count次（不+1）的变体解码3069像素（只差3像素），确认正确。

### 12.2 调色板破解

**问题**：v1颜色偏暗。
**排查**：检查MAP.PAL发现全局最大值R=63/G=63/B=63，确认是6bit VGA调色板。
**修复**：所有颜色值×4转8bit。

### 12.3 IND双格式破解（v3核心）

**问题**：v2中rec022等记录提取出大量碎片。
**排查**：
1. 检查问题条带IND数据：`16 17 18 18 19 1a 00 1b`
2. @4=0x1a19作为CEL偏移无法解析行索引
3. 拆成u8发现连续数字[22,23,24,24,25,26,0,27]
4. 猜测是全局索引表条目编号 → 渲染验证成功
5. 系统分类所有条带：72个行索引格式 + 1176个u8引用格式

**关键教训**：8字节的条带不一定是4个u16，当@4值较小时应考虑u8数组格式。

### 12.4 CEL全局索引表格式修正

**错误**：最初认为条目格式是(u16 size, u32 offset)。
**正确**：条目格式是(u32 offset, u16 size)。
**验证**：条目N的offset+size == 条目N+1的offset。

---

## 13. 经验总结（举一反三）

### 13.1 DOS游戏资源逆向通用方法论

1. **先普查文件结构**：列出所有文件、大小、扩展名，识别归档文件和索引文件
2. **从索引文件入手**：.IND/.DAT等小文件通常包含偏移/大小信息，是理解归档格式的钥匙
3. **验证索引连续性**：解析索引后检查offset是否递增、offset+size是否等于下一个offset
4. **反汇编确认格式**：用IDA/capstone分析可执行文件中的加载函数，确认头格式和压缩算法
5. **小样本验证**：先提取1-2个图像验证格式正确，再全量提取
6. **去重**：基于像素MD5去重，DOS游戏大量复用精灵

### 13.2 常见陷阱

| 陷阱 | 表现 | 解决 |
|------|------|------|
| 6bit VGA调色板 | 颜色偏暗 | 检查调色板最大值，×4转8bit |
| 条带多格式 | 部分图像正确部分碎片 | 检查@4值大小，小值可能是u8数组 |
| 索引条目字节序 | offset异常大 | 尝试(u32 offset, u16 size) vs (u16 size, u32 offset) |
| RLE的count=0 | 全黑或条纹 | count=0可能是无操作/跳过 |
| RLE重复次数 | 差几个像素 | 是count次还是count+1次需精确验证 |
| 透明色 | 黑色背景 | 像素0通常是透明，渲染时alpha=0 |

### 13.3 格式识别检查清单

提取新DOS游戏图像时，按以下顺序检查：

1. **调色板**：是8bit还是6bit？最大值是多少？
2. **索引文件**：记录数？每条记录大小？条带结构？
3. **条带格式**：@4是偏移还是编号？8字节是u16×4还是u8×8？
4. **归档头**：条目数？条目格式(offset,size)的字节序？
5. **图像头**：w/h是实际值还是-1？
6. **压缩算法**：RLE？count=0如何处理？重复次数是否+1？
7. **透明色**：哪个像素值表示透明？

### 13.4 可复用代码模式

本文档的`rle_decode()`、`render_img()`、`is_row_index_format()`、全局索引表解析等函数可直接复用于其他宇峻科技DOS游戏（如超时空英雄传说2、三国群英传等），因为它们可能使用相同的CEL/IND格式。

---

## 14. 未解决问题

1. **SPELL.CEL** (6.4MB)：格式与其他CEL不同，u32偏移数组非递增，第一个图像8×1异常
2. **音频提取**：MIDI.BIN / SOUND.BIN 未提取
3. **STAGE.BIN**：地图数据格式未分析
4. **文本资源**：对话/剧情文本未定位
5. **STORY.CEL / INST.CEL / MAIN.CEL**：部分提取，需确认完整性

---

## 15. 相关脚本

| 脚本 | 功能 |
|------|------|
| scripts/900-903 | IND/CEL索引分析 |
| scripts/919-945 | 反汇编与RLE搜索 |
| scripts/950-956 | RLE变体系统测试 |
| scripts/957 | 最终RLE验证（成功） |
| scripts/963-968 | v1/v2提取 |
| scripts/970 | CEL全局索引表解析 |
| scripts/971 | v2统一提取（6bit×4+去重） |
| scripts/979-984 | IND双格式排查系列 |
| scripts/985 | **v3 EMAN正确提取（双格式）** |
| scripts/986 | **v3 PMAN正确提取（双格式）** |

---

*文档版本：v3.0 | 最后更新：2026-09-14*
