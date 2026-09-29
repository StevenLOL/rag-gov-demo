# 《轩辕剑外传·枫之舞》(SWDA) 资源格式逆向与全素材提取

> 大宇资讯 1995 | DOS | 逆向工程 | 两层压缩 | unicorn 模拟
>
> **最终成果**：
> - RSK 图像：259帧（257/259逐像素匹配）
> - VOC 语音：135个WAV
> - LSK 归档：2534个子文件解压，CD/DO/SA图像644张（BMP+透明PNG）
> - MAP 瓦片地图：96张（含底层/顶层/合成三层渲染）
> - SA 多帧动画：212个文件/2530帧（magic=(帧数+1)×2统一格式）
> - DSK 动画：19个，头部/索引表结构已解析，压缩算法待逆向

---

## 0. 核心矛盾与解题路径

### 0.1 最初的困惑

```
RPGViewer 显示 BA01.RSK = 320×200×8bpp = 64000 字节
但 LZSS 解压只出 47125 字节
```

**要么** RPGViewer 显示的是渲染后尺寸（含调色板/帧头），**要么** 数据还有第二层编码。

### 0.2 解题路径图

```
┌─────────────────────────────────────────────────────────────┐
│                    逆向工程时间线                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  阶段1: 暴力尝试 (脚本245-257)                               │
│  ├── 480+ 种 LZSS 参数组合 → 全部失败 (<0.2%)               │
│  ├── 标准 LZH8 / LZARI → 失败                               │
│  └── 结论: 不是标准压缩算法                                  │
│                                                             │
│  阶段2: 反汇编定位 (脚本258-261)                             │
│  ├── vftable 调用链追踪                                     │
│  ├── 0x4eeb30 (RSK头解析) → 0x4ee390 (真正解压)            │
│  └── 确认: deflate风格动态Huffman + LZSS                    │
│                                                             │
│  阶段3: Python手写解码器 (14版)                              │
│  └── 全部 <0.1% → 位读取器模拟不精确                        │
│                                                             │
│  阶段4: unicorn模拟突破 (脚本277-290)                       │
│  ├── PE段用vsize映射 (关键坑!)                              │
│  ├── IAT修复 + 全局变量重置                                 │
│  ├── 调用约定: ecx=输入, edx=长度, 栈=输出/usize/1          │
│  └── BA06 像素 64000/64000 100%匹配!                       │
│                                                             │
│  阶段5: 第二层压缩 (0x447f40)                               │
│  ├── 32个文件像素<64000, 前2字节=4e 54 (0x544e签名)        │
│  ├── RLE变体, 支持MT/NT两种签名                             │
│  └── NT分支写入步长+4 (u32数组取低8位)                      │
│                                                             │
│  阶段6: 多帧格式解析                                        │
│  ├── 索引表格式 (DOR1/DOR3): [u16 idx_size][u16 offsets]   │
│  ├── 偏移表格式 (MENU/MEO): @0开始u16帧偏移数组             │
│  └── 帧数据可乱序存储! (DOR3关键发现)                       │
│                                                             │
│  阶段7: 全资源提取                                          │
│  ├── RSK: 259帧 (BA37 + DOR26 + ME2 + MENU189 + MEO5)     │
│  ├── VOC: 135个 → WAV                                      │
│  ├── LSK: 4个归档 → 2534子文件 → BA格式图像                 │
│  └── RIX: 85个 OPL FM音乐 (待转换)                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 1. 以前错在哪？—— 三个经典失败案例

### 1.1 案例一：LZSS 480+ 组合全灭

**错误假设**：`.RSK` 是标准 LZSS 压缩，只要找到正确的窗口大小/起始偏移/位序就能解压。

**实际尝试**：
- 窗口大小：256 / 512 / 1024 / 2048 / 4096 / 8192
- 起始偏移：0 / 1 / 2 / 3 / 4
- 位序：MSB-first / LSB-first
- 标志位：1字节flag / 直接字面量
- 组合数：480+ 种

**结果**：全部匹配率 < 0.2%，输出几乎全是随机数据。

**根因**：第一层压缩根本不是 LZSS，而是 **deflate 风格的动态 Huffman + LZSS 混合算法**。压缩流开头有 Huffman 树定义，纯 LZSS 无法解析。

**教训**：当暴力参数搜索全部失败时，不要继续调参，应该转向反汇编确认算法类型。

---

### 1.2 案例二：Python 手写 deflate 14 版全灭

**错误假设**：既然是 deflate 风格，用 Python 手写一个解码器就行。

**实际尝试**：14 个版本，逐步修正位读取器、Huffman 树构建、LZSS 匹配。

**结果**：全部 < 0.1%，前几个字节可能正确，后面完全错误。

**根因**：位读取器的模拟不精确。该算法使用**双缓冲区设计**：
- 全局变量 `0x5ac230`：位缓冲区（32位）
- 全局变量 `0x5ac238`：当前位位置
- 全局变量 `0x5ac23c`：输入指针
- 全局变量 `0x5ac22c/34/40/44`：其他状态

位读取的边界条件（缓冲区用尽时重新填充、跨字节对齐）极其微妙，Python 模拟很难 100% 还原 x86 指令的行为。

**教训**：对于位级操作复杂的算法，**直接模拟原始代码**比手写移植更可靠。unicorn 模拟 x86 代码可以保证指令级精确。

---

### 1.3 案例三：0x5070fb 覆盖事件（最严重的 bug）

**错误假设**：`0x5070fb` 是一个函数入口，可以用 IAT 桩覆盖。

**实际发生**：
```
批量提取时，第一层输出全零！
排查发现：0x5070fb 被 IAT 桩覆盖为 ret 指令
```

**根因**：`0x5070fb` **根本不是函数入口**，而是一条普通指令：
```asm
0x5070fb: cmp ecx, [0x59c040]   ; stack check 内联代码
```

覆盖后，这条 `cmp` 指令变成了 `ret`，破坏了代码流，导致后续所有解压调用失败。

**怎么发现的**：逐字节对比成功/失败的 PE 镜像，发现 `0x5070fb` 处的字节被篡改。

**教训**：
1. **绝对不要假设某个地址是函数入口**，必须通过反汇编确认
2. IAT 桩只能覆盖真正的 IAT 条目（`0x516xxx` 范围），不能覆盖代码段
3. 批量失败时，先检查环境状态是否被污染，而不是怀疑算法

---

### 1.4 怎么"蒙对"的？—— unicorn 模拟的关键突破

真正的突破不是"蒙"，而是**换了一条路**：

```
手写解码器 (失败)
    ↓
反汇编确认算法类型 (deflate风格)
    ↓
Python移植 (失败，位读取不精确)
    ↓
unicorn直接模拟x86代码 (成功!)
```

unicorn 模拟的关键坑（踩了无数次才搞对）：

| 坑 | 错误做法 | 正确做法 |
|---|---|---|
| PE段映射 | 用 raw_size | 用 **vsize**（BSS在raw_size之外） |
| 结束地址 | 函数的 ret 指令 | 函数**内部退出点** `0x4ee592` |
| 输入指针 | RSK+4 | **RSK+3**（含type字节） |
| 全局变量 | 不重置 | 每次调用前重置7个全局变量 |
| IAT修复 | 只修memset | memset + malloc + free |
| 函数入口 | 0x5070fb | **0x4ee390**（通过调用链确认） |

---

## 2. .RSK 文件格式（三种变体）

### 2.1 通用文件头

所有 `.RSK` 文件共享同一个外层头：

```
偏移  大小  字段      说明
0     u16   usize     第一层解压后总大小
2     u8    method    压缩方法 (0=未压缩, 1=第一层压缩)
3     u8    type      图像类型 (0x1a-0x20)
4     ...   data      压缩数据 (从RSK+3开始，含type字节)
```

### 2.2 第一层解压后：三种格式判别

```
第一层解压后的数据 (mid)
    │
    ├─ mid[0:2] == 0x0004 ──→ 格式A: BA单帧背景
    │
    ├─ mid[0:2] < 10000 且为偶数 ──→ 格式B: 索引表多帧
    │
    └─ 其他 ──→ 格式C: 偏移表多帧 (MENU/MEO)
```

### 2.3 格式A：BA 单帧背景（37个文件）

```
┌──────────────────────────────────────────────────┐
│ 0          u16 magic = 4                          │
│ 2          u16 palette_offset                     │
│ 4          u16 height = 200                       │
│ 6          u16 width = 320                        │
│ 8          pixel_data (未压缩 或 0x544e压缩)      │
│ palette_offset  3 bytes unknown (ff ff e8)       │
│ palette_offset+3  768 bytes 6-bit RGB调色板      │
└──────────────────────────────────────────────────┘
```

- `palette_offset = usize - 771`
- 像素数据前2字节为 `4e 54` → 第二层解压
- 未压缩像素 = 64000 字节（对应 usize=64779）

### 2.4 格式B：索引表多帧（DOR1/DOR3等）

```
┌──────────────────────────────────────────────────┐
│ 0          u16 idx_size (索引表总字节数)          │
│ 2          u16 offsets[0]   帧1起始偏移           │
│ 4          u16 offsets[1]   帧2起始偏移           │
│ ...        ...                                    │
│ idx_size   帧0数据 [u16 h][u16 w][像素]          │
│ offsets[0] 帧1数据 [u16 h][u16 w][像素]          │
│ ...                                              │
└──────────────────────────────────────────────────┘
```

**关键发现：帧数据可乱序存储！**

DOR3 的偏移表中，后段偏移（47033）小于前段偏移（59129）。这是因为：
- 帧1（208×67）的压缩数据在 40051-47033
- 帧16-21（小帧）存储在 47033-50173 的"空隙"中
- RLE 解压函数自动停止，不会多读后面的数据

**帧数 = (idx_size - 2) / 2**

### 2.5 格式C：偏移表多帧（MENU/MEO）

```
┌──────────────────────────────────────────────────┐
│ 0          u16 offset[0]   帧0起始偏移            │
│ 2          u16 offset[1]   帧1起始偏移            │
│ ...        ...                                    │
│ offset[0]  帧0 [u16 h][u16 w][像素]              │
│ offset[1]  帧1 [u16 h][u16 w][像素]              │
│ ...                                              │
└──────────────────────────────────────────────────┘
```

- 偏移表从 @0 开始，每帧 2 字节偏移
- 帧数通过验证偏移指向的帧头有效性来确定
- MENU: 189帧，MEO: 5帧
- 帧数据同样可乱序存储

### 2.6 每帧的像素数据

```
帧起始偏移
    ├─ u16 height
    ├─ u16 width
    └─ 像素数据
        ├─ 前2字节 == 4e 54 (0x544e "NT") → 第二层RLE解压
        ├─ 前2字节 == 4d 54 (0x544d "MT") → 第二层RLE解压
        └─ 其他 → 未压缩，直接读 w*h 字节
```

---

## 3. 第一层压缩算法（0x4ee390）—— 完整保存

### 3.1 算法特征

- **类型**：deflate 风格动态 Huffman + LZSS 混合
- **位读取器**：双缓冲区，全局变量维护状态
- **Huffman 树**：从压缩流头部动态构建字面量/长度树和距离树
- **LZSS 匹配**：长度 3-258，距离 1-32768

### 3.2 调用约定

```c
// cdecl，返回值 al (0=成功, 1=失败，但al=1时输出仍有效)
uint8_t decompress_layer1(
    uint8_t* output,   // [esp+4] 输出缓冲区
    uint16_t usize,    // [esp+8] 解压后大小
    uint32_t arg3,     // [esp+12] 恒为 1
    // 寄存器参数
    ecx = compressed_input,  // RSK+3 (含type字节!)
    edx = compressed_length  // 压缩数据长度
);
```

### 3.3 unicorn 模拟完整代码

```python
import struct
from unicorn import *
from unicorn.x86_const import *

def setup_unicorn(exe_path):
    """加载RPGViewer.exe到unicorn，修复IAT"""
    with open(exe_path, 'rb') as f: exe = f.read()
    pe_off = struct.unpack_from('<I', exe, 0x3c)[0]
    n_sec = struct.unpack_from('<H', exe, pe_off+6)[0]
    opt_size = struct.unpack_from('<H', exe, pe_off+20)[0]
    sec_off = pe_off + 24 + opt_size
    
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    BASE = 0x400000
    mu.mem_map(BASE, 0x300000)
    
    # 关键: 用vsize映射，不是raw_size!
    for i in range(n_sec):
        vsize = struct.unpack_from('<I', exe, sec_off+i*40+8)[0]
        vaddr = struct.unpack_from('<I', exe, sec_off+i*40+12)[0]
        raw_size = struct.unpack_from('<I', exe, sec_off+i*40+16)[0]
        raw_ptr = struct.unpack_from('<I', exe, sec_off+i*40+20)[0]
        addr = BASE + vaddr
        size = max(vsize, raw_size)
        mu.mem_write(addr, b'\x00' * size)
        if raw_size > 0:
            mu.mem_write(addr, exe[raw_ptr:raw_ptr+raw_size])
    
    # IAT桩
    MEMSET = 0xA00100
    mu.mem_map(0xA00000, 0x10000)
    mu.mem_write(MEMSET, b'\xc3')  # ret
    mu.mem_write(0x5162f4, struct.pack('<I', MEMSET))
    
    mu.mem_map(0x800000, 0x10000)  # 栈
    mu.mem_map(0x900000, 0x100000) # 输入/输出
    
    def hook_memset(mu, addr, size, ud):
        if addr == MEMSET:
            esp = mu.reg_read(UC_X86_REG_ESP)
            ptr = struct.unpack('<I', mu.mem_read(esp+4, 4))[0]
            val = struct.unpack('<I', mu.mem_read(esp+8, 4))[0] & 0xff
            num = struct.unpack('<I', mu.mem_read(esp+12, 4))[0]
            if num > 0 and ptr > 0:
                mu.mem_write(ptr, bytes([val]) * num)
            mu.reg_write(UC_X86_REG_EAX, ptr)
            ret = struct.unpack('<I', mu.mem_read(esp, 4))[0]
            mu.reg_write(UC_X86_REG_EIP, ret)
            mu.reg_write(UC_X86_REG_ESP, esp + 4)
    
    mu.hook_add(UC_HOOK_CODE, hook_memset)
    return mu

def decompress_layer1(mu, rsk_data):
    """第一层解压: rsk_data → 解压后字节"""
    usize = struct.unpack_from('<H', rsk_data, 0)[0]
    INPUT, OUTPUT = 0x900000, 0x910000
    
    # 关键: 输入从RSK+3开始，含type字节
    compressed = rsk_data[3:]
    mu.mem_write(INPUT, compressed)
    mu.mem_write(OUTPUT, b'\x00' * usize)
    
    # 重置全局变量
    for addr in [0x5ac22c, 0x5ac230, 0x5ac234, 0x5ac238,
                 0x5ac23c, 0x5ac240, 0x5ac244]:
        mu.mem_write(addr, b'\x00' * 4)
    
    # 栈布局: [esp]=返回地址, [esp+4]=output, [esp+8]=usize, [esp+12]=1
    esp = 0x800000 + 0x10000 - 0x100
    mu.reg_write(UC_X86_REG_ESP, esp)
    mu.mem_write(esp, struct.pack('<IIII', 0x4ee592, OUTPUT, usize, 1))
    
    # 寄存器参数
    mu.reg_write(UC_X86_REG_ECX, INPUT)
    mu.reg_write(UC_X86_REG_EDX, len(compressed))
    
    # 关键: 结束地址是内部退出点0x4ee592，不是ret!
    try:
        mu.emu_start(0x4ee390, 0x4ee592)
    except:
        pass
    
    return bytes(mu.mem_read(OUTPUT, usize))
```

---

## 4. 第二层压缩算法（0x447f40）—— 完整保存

### 4.1 算法特征

- **类型**：RLE（行程编码）变体
- **两种签名**：
  - `0x544d` ("MT")：memset 优化的 RLE
  - `0x544e` ("NT")：手动循环 RLE，写入步长 +4
- **NT 分支**：输出为 u32 数组，每个像素占 4 字节，取低 8 位

### 4.2 调用约定

```c
// stdcall, ret 0x18 (6参数, 24字节)
uint32_t decompress_layer2(
    InputStruct* input,   // [ebp+8]  [input]=数据指针
    uint32_t offset,      // [ebp+0xc] 0
    uint32_t width,       // [ebp+0x10]
    uint32_t height,      // [ebp+0x14]
    uint32_t arg5,        // [ebp+0x18] 0
    uint32_t* out_size    // [ebp+0x1c] 输出大小
);
```

### 4.3 unicorn 模拟完整代码

```python
MALLOC = 0xA00200
FREE = 0xA00300
OUTPUT_BUF = 0x980000

def decompress_layer2(mu, comp_data, w, h):
    """第二层RLE解压"""
    INPUT = 0x940000
    INPUT_STRUCT = 0x950000
    OUT_SIZE = 0x950010
    
    mu.mem_write(INPUT, comp_data)
    mu.mem_write(INPUT_STRUCT, struct.pack('<I', INPUT))
    mu.mem_write(OUT_SIZE, struct.pack('<I', 0))
    # NT分支需要w*h*4字节输出缓冲区
    mu.mem_write(OUTPUT_BUF, b'\x00' * (w * h * 4))
    
    esp = 0x800000 + 0x10000 - 0x100
    mu.reg_write(UC_X86_REG_ESP, esp)
    mu.mem_write(esp, struct.pack('<IIIIIII',
        0x447f2f,       # 返回地址(内部退出点)
        INPUT_STRUCT,   # [ebp+8]
        0,              # [ebp+c] offset
        w,              # [ebp+10] width
        h,              # [ebp+14] height
        0,              # [ebp+18]
        OUT_SIZE        # [ebp+1c] out_size指针
    ))
    
    try:
        mu.emu_start(0x447f40, 0x447f2f)
    except:
        pass
    
    out_size = struct.unpack('<I', mu.mem_read(OUT_SIZE, 4))[0]
    result = bytes(mu.mem_read(OUTPUT_BUF, out_size))
    
    # NT分支: u32数组取低8位
    if len(result) >= w * h * 4:
        return bytes([result[i*4] for i in range(w*h)])
    return result[:w*h]
```

---

## 5. 其他资源格式

### 5.1 .VOC 语音（135个）

标准 Creative Voice 格式，直接转换为 WAV：
- 采样率：从 VOC 块头读取
- 位深：8-bit unsigned PCM
- 已全部转换：`audio_voc/` 目录 135 个 WAV

### 5.2 .RIX OPL FM 音乐（85个）

大宇自研 OPL2 FM 合成音乐格式，签名 `0x55aa`。

```
@0   u16 0x55aa (签名)
@2   u16 0 (保留)
@4   u32 0 (保留)
@8   u16 数据偏移 (通常=20)
@10  u16 速度参数
@12+ 音乐事件序列 (乐器定义+音符事件+控制命令)
```

**关键发现**：RIX 不是简单的 OPL 寄存器转储，而是完整的音乐序列格式，包含乐器定义（11通道OPL寄存器参数）、音符事件、节奏控制（BD/SD/TT/CY/HH鼓组）和循环标记。

**播放器**：adplug 的 `rix.cpp`（约1500行）完整实现，SDLPal 的 `rixplay.cpp` 封装播放接口。pyopl 仅提供 OPL 硬件模拟，无法直接播放 RIX 序列。

**状态**：格式已完全分析，转换需移植 adplug 播放器。

### 5.3 .LSK 数据包（4个，共14MB）

```
┌──────────────────────────────────────────────────┐
│ 0          u32 offset[0] = idx_size              │
│ 4          u32 offset[1]                         │
│ ...        ...                                    │
│ idx_size   子文件0数据                            │
│ offset[1]  子文件1数据                            │
│ ...                                              │
└──────────────────────────────────────────────────┘
```

- CD.LSK: 587子文件 → 531个8bpp图像（精灵/界面）
- DO.LSK: 664子文件 → 36个8bpp + 1个16bpp图像（对话框）
- MAP.LSK: 833子文件 → 96个16bpp 5:6:5图像（地图图块）
- SA.LSK: 450子文件 → 67个8bpp图像（战斗背景）
- 子文件头：`[u16 usize][u8 method=1][u8 type]` → 第一层解压 → BA格式图像

#### 5.3.1 LSK 调色板破解（关键发现）

**问题**：首次转换全部黑色，因为大部分子文件无内嵌调色板（pal_off 指向文件末尾）。

**破解过程**：
1. CD 的 `0000.dec` 是独立调色板文件（h=1,w=4 占位图，含768字节6bit调色板）
2. DO 的 `0038.bin`（未压缩原始文件，1842字节）@2 含768字节调色板
3. MAP 的 `0000.dec`（1842字节未压缩）@2 含调色板
4. SA 的 `0199.dec`（1842字节未压缩）@2 含调色板

**各目录调色板特征**：
| 目录 | 调色板来源 | [0] | [254] | 用途 |
|---|---|---|---|---|
| CD | 0000.dec@pal_off+3 | 00 00 00 | 00 27 16 | 精灵/界面 |
| DO | 0038.bin@2 | 00 00 00 | 00 27 16 | 对话框 |
| MAP | 0000.dec@2 | 00 00 00 | 00 27 16 | 地图（16bpp不用） |
| SA | 0199.dec@2 | 00 00 00 | 00 27 16 | 战斗背景 |

**教训**：搜索调色板时不能只看 `all(b<=63)`，压缩数据中会有大量假阳性（灰色调色板）。真正的调色板特征是 `[0]=00 00 00` 黑色且有明显颜色分布。

#### 5.3.2 MAP 瓦片地图格式突破（历时最长的逆向）

**这是整个项目中最曲折的部分，经历了 6 次方向转变，最终靠数据关联而非反汇编突破。**

##### 阶段1：把地图当图像（完全错误）

最初假设 MAP 是 16bpp RGB 5:6:5（因为像素数据长度 = w×h×2），渲染后颜色完全错误。
随后尝试低字节=8bpp索引+MAP调色板，用户反馈"轮廓对了，色彩不对"。
接着测试了 7 种索引格式、6 种颜色通道×3 种位深、116 个调色板逐个测试，全部被用户否决。

**根因**：MAP 根本不是图像，而是**瓦片地图数据**。

##### 阶段2：用户的关键洞察

用户指出："这不是 bmp 图片，而是地图 map，上面的数值就是代表放置什么东西。所以一定有一个地方存着所有的瓦片数据。"

分析 MAP.LSK 结构，发现**每 7 个文件一组**：
```
[调色板(1842B)] [瓦片集×4(固定大小)] [地图数据(magic=4)] [物体数据(u16数组)]
```

地图数据格式：`[u16 magic=4][u16 pal_off][u16 h][u16 w][w×h×2字节]`
每瓦片 2 字节：低字节=瓦片ID，高字节=属性。

##### 阶段3：8×8 瓦片假设（半对）

用 8×8 瓦片+48字节头部假设渲染组1（0008瓦片集，511瓦片+0012地图220×120），得到 1760×960 城镇地图，用户说"还是不太对"。

**核心矛盾**：组2瓦片集仅 14848 字节 = 232 个 64 字节瓦片，但地图瓦片 ID 范围 0-255，有 81 个 ID 超出范围。

##### 阶段4：反汇编游戏 EXE（用户要求）

用户三次强调"必须反编译游戏本身，禁止反汇编 RPGViewer"。反汇编 RPG.EXE 发现：
- `0x34a2`：瓦片地址计算，`es=[0x718b]+0x20; si=瓦片ID×2+4; si=es:[si]` → 证实有偏移表
- `0x4333`：瓦片解压转换，解压到段+0x6400，转换到段+0x6000（16KB=256个8×8瓦片）
- 远调用目标 `0xeec:0x3c2`/`0xaf8:0x38ac` 不在 RPG.EXE/SWDA.EXE/MAPA.EXE 中

偏移表假设被数据证伪（偏移不递增），反汇编陷入僵局。

##### 阶段5：数据关联突破（最终解法）

**关键线索**：调色板文件 @0 的 u16 值：
- 组0: 1603 | 组1: 2047 | 组2: 928 | 组3: 623 | 组4: 744

**偶然发现**：4 个瓦片集文件合并后 / 64 = 调色板 @0 值！
```
组2: 4 × 14848 / 64 = 928  ✓
组1: 4 × 32752 / 64 = 2047 ✓  (全部5组精确匹配!)
```

这证明：
1. **4 个瓦片集文件合并成一个大瓦片集**（之前误以为是 4 个独立瓦片集）
2. **每瓦片固定 64 字节**（8×8，8 位索引），**没有 48 字节头部**
3. 调色板 @0 = 总瓦片数（校验字段）

随后发现组1高字节低 3 位有 0-7 全部 8 个值，测试 `全局索引 = (high & 7) × 256 + tile_id`，**超出范围=0**，渲染正确。

##### 最终格式定义

```
调色板文件:
  @0   u16 total_tiles    (总瓦片数，=4×瓦片集大小/64)
  @2   u8[768] palette    (6bit RGB 调色板)
  @770 u16[536] unknown   (属性表/动画表)

瓦片集: 4个文件合并，每瓦片64字节(8×8, 8位索引)
  全局索引范围: 0 ~ total_tiles-1

地图数据:
  @0   u16 magic = 4
  @2   u16 pal_off        (像素数据结束位置 = 8 + w×h×2)
  @4   u16 h              (地图高度，瓦片数)
  @6   u16 w              (地图宽度，瓦片数)
  @8   u8[w×h×2] tiles    (每瓦片2字节)

每瓦片2字节:
  低字节 tile_id:  局部瓦片ID (0-255)
  高字节 attributes:
    bits 0-2 (0x07): bank 选择 (0-7)，全局索引 = bank×256 + tile_id
    bit 4  (0x10): 垂直翻转 (推测)
    bit 6  (0x40): 水平翻转
    bit 7  (0x80): 顶层标记 (渲染在角色之上)
```

**验证**：96 个地图全部渲染成功（之前只渲染了35个，因为按组逻辑有缺陷），所有瓦片全局索引均在范围内（超出范围=0）。
组1（220×120）渲染出完整城镇：城墙、护城河、建筑、道路、田地。
组0（120×120）渲染出野外大地图：草地、水域、沙地。
其他地图包括建筑内部、迷宫、战斗场景等。

**教训**：
1. 数据长度是 2×像素数 ≠ 16bpp RGB，必须先判断数据语义
2. 当反汇编陷入僵局时，回到数据本身寻找关联（调色板@0与瓦片集大小的关系是突破口）
3. "4个文件"不等于"4个独立瓦片集"，可能是一个大瓦片集的分片
4. 用户的领域直觉（"这是地图数据"）比技术猜测更有价值

### 5.4 .DSK 动画（19个，压缩格式待逆向）

- CHNA1-16：场景/人物动画
- BOOK：图鉴
- CHAIN：连续动画
- CHFIG：人物形象

```
@0   u16 block_count = (文件大小-2)/32  (所有19个文件精确匹配)
@2   u16 type_tag (0x40a1/0x4bb6/0xfcab/0x48a5)
@4   u16 index[block_count-2]  (帧在解压后64KB空间的偏移)
@4+(block_count-2)*2   压缩数据
```

**关键发现**：
- 文件按32字节块对齐，`block_count=(size-2)/32`精确匹配所有19个文件
- 索引表有`block_count-2`个u16条目，值范围16548-65219（0x40a4-0xfefe）
- 索引值指向**解压后64KB空间**中的帧偏移，前16KB(0x0000-0x3fff)为调色板/头部
- 同类型DSK共享type_tag：0x40a1(11个)、0x4bb6(6个)、0xfcab(1个)、0x48a5(1个)
- 压缩数据字节分布：0(14%)、16、8、64、254、32等2的幂值，疑似LZSS/Huffman
- zlib/raw deflate/gzip/LZSS/RLE/RSK unicorn第一层解压均无效
- 无RSK签名(0x544d/0x544e)、无YJ_1签名

**加载机制**：
- DSK由覆盖模块加载（CHNA1.EXE→CHNA1.DSK, FIG.EXE→CHFIG.DSK等）
- FIG.EXE通过`int 61h`功能2调用解压（SWDA.EXE TSR提供）
- SWDA.EXE设置int 61h中断向量，函数表在ds:0x6d，功能2对应解压函数
- 压缩算法在SWDA.EXE的TSR中，需动态调试或IDA Pro深入分析

**状态**：头部/索引表结构已解析，压缩算法待逆向。

### 5.5 SA 多帧动画（212个文件，2530帧）

SA.LSK 中所有 **偶数 magic≥6** 的文件都是多帧动画，格式统一。

```
@0    u16 magic = (帧数+1) × 2
@2    u16 offsets[帧数]  (每帧结束偏移，相对于文件起始)
@2+帧数×2   帧0: [u16 w][u16 h][w×h字节8位索引]
@offsets[0] 帧1: ...
```

**关键发现**：
- magic值直接编码帧数：magic=6→2帧, magic=8→3帧, magic=10→4帧, ..., magic=26→12帧, magic=68→33帧
- 每帧 = 4字节头部(w,h) + w×h字节像素
- 索引254(0xfe)为透明色
- 调色板使用SA共享调色板（13个调色板文件，按文件索引就近匹配）
- 帧尺寸多样：40×24, 24×24, 32×40, 31×32, 64×24, 16×16等

**验证**：212个文件全部成功渲染，共2530帧。包括战斗特效、角色动画、场景动画等。

---

## 6. 提取成果统计

| 资源类型 | 数量 | 状态 | 输出目录 |
|---|---|---|---|
| BA背景图 | 37 | ✅ 100% | `rsk_all/BA*.bmp` |
| DOR多帧 | 26 | ✅ 100% | `rsk_all/DOR*.bmp` |
| ME单帧 | 2 | ✅ 100% | `rsk_all/ME*.bmp` |
| MENU界面 | 189 | ✅ 100% | `rsk_all/MENU*.bmp` |
| MEO精灵 | 5 | ⚠️ 257/259 | `rsk_all/MEO*.bmp` |
| VOC语音 | 135 | ✅ 已转WAV | `audio_voc/` |
| LSK子文件 | 2534 | ✅ 已解压 | `lsk_decoded/` |
| LSK-CD精灵(8bpp) | 540 | ✅ 已转BMP+透明PNG | `lsk_bmp/CD/`, `lsk_png/CD/` |
| LSK-DO对话框(8bpp) | 37 | ✅ 已转BMP+透明PNG | `lsk_bmp/DO/`, `lsk_png/DO/` |
| LSK-MAP瓦片地图 | 96 | ✅ 底层/顶层/合成 | `map_rendered/`, `map_layered/` |
| LSK-SA战斗(8bpp) | 67 | ✅ 已转BMP+透明PNG | `lsk_bmp/SA/`, `lsk_png/SA/` |
| SA多帧动画 | 212个/2530帧 | ✅ 已提取 | `sa_all_anims/` |
| DSK动画 | 19 | ⏳ 结构已解析，压缩待逆向 | 根目录 |

**总计：259帧RSK + 135语音 + 644张LSK图像 + 96张瓦片地图 + 2530帧SA动画**

---

## 7. 关键脚本清单

| 脚本 | 功能 |
|---|---|
| `318_swda_final_all_rsk.py` | **统一RSK提取器**（三种格式，259帧，unicorn模拟） |
| `321_swda_extract_lsk.py` | LSK归档解包（4个归档2534子文件） |
| `322_swda_decompress_lsk.py` | LSK子文件第一层解压 |
| `326_swda_voc_all.py` | VOC批量转WAV（135/135） |
| `337_swda_final_lsk_bmp.py` | LSK 8bpp转BMP（CD/DO/SA正确） |
| `344_swda_bmp_to_png_green_transparent.py` | CD/DO/SA BMP转透明PNG |
| `407_swda_map_merged_paloffset.py` | **MAP格式突破**（4瓦片集合并+8bank验证） |
| `410_swda_map_batch_render.py` | MAP批量渲染（初版35个） |
| `421_swda_map_all_magic4.py` | **MAP全量渲染**（96个magic=4地图） |
| `422_swda_tile_flip_analysis.py` | 瓦片翻转/顶层属性分析 |
| `423_swda_map_layered.py` | **MAP分层渲染**（底层/顶层/合成） |
| `427_swda_sa_all_anims.py` | **SA动画全量提取**（212个/2530帧） |
| `428-437_swda_dsk_*.py` | DSK格式分析（结构已解析，压缩待逆向） |

---

## 8. 经验总结

1. **暴力调参有上限**：480+ 种 LZSS 组合全灭，说明算法类型判断错了
2. **反汇编是金标准**：通过 vftable 调用链精确定位到 `0x4ee390`
3. **模拟优于移植**：位级复杂算法用 unicorn 模拟原始代码，比手写移植可靠
4. **环境状态要纯净**：0x5070fb 覆盖事件教训——不要假设地址是函数入口
5. **数据可以乱序**：DOR3 偏移表后段偏移小于前段，RLE 自动停止是关键
6. **ground truth 是验证基础**：RPGViewer 导出的 259 张 BMP 是所有验证的基准
7. **逐层验证**：先验证单帧（BA06），再多帧（DOR1），最后全量（259帧）
