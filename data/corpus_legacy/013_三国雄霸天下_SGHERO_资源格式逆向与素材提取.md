# 三国雄霸天下 (SGHERO) 资源格式逆向与素材提取

## 1. 游戏概述

- **游戏名称**: 三国雄霸天下 (SGHERO)
- **游戏目录**: `E:\BaiduNetdiskDownload\dos\0001_经典DOS游戏合集\SGHERO`
- **可执行文件**: PLAY.EXE (202801字节, 16位DOS MZ)
- **提取输出**: `C:\src\InformationSecurity\dosgames\extracted\SGHERO_超时空英雄传说\`（目录名沿用，将错就错）

## 2. 文件清单与分类

### 2.1 归档文件 (JMC+HED)
| 文件 | 大小 | 说明 |
|------|------|------|
| TEST.JMC | 861136 | 主资源归档（加密ARJ变体） |
| TEST.HED | 4303 | TEST索引文件 |
| PRO.JMC | 502704 | 职业/角色资源归档 |
| PRO.HED | 1248 | PRO索引文件 |
| TITLE.JMC | 470704 | 标题画面归档 |
| TITLE.HED | - | 标题索引 |
| ENDA.JMC | 314992 | 结局A归档 |
| ENDA.HED | - | 结局A索引 |
| ENDB.JMC | 390144 | 结局B归档 |
| ENDB.HED | - | 结局B索引 |
| ENDC.JMC | 101472 | 结局C归档 |
| ENDC.HED | - | 结局C索引 |

### 2.2 动画文件 (NCC)
| 文件 | 大小 | 说明 |
|------|------|------|
| TITLE.NCC | 32482 | 标题动画 |
| ENDA.NCC | 35414 | 结局A动画 |
| ENDB.NCC | 40196 | 结局B动画 |
| ENDC.NCC | 42277 | 结局C动画 |
| END1.NCC | 33673 | 结局动画1 |
| END2.NCC | 32438 | 结局动画2 |
| END3.NCC | 33626 | 结局动画3 |

### 2.3 字体文件
| 文件 | 大小 | 格式 |
|------|------|------|
| PRO.15 | 32768 | 16x16 1bpp字体，1024字符 |
| RPG.15 | 29070 | 16x16 1bpp字体，908字符 |

### 2.4 音乐与音效
| 类型 | 文件数 | 格式 |
|------|--------|------|
| .MID | 8 | 标准MIDI |
| .MUS | 8 | 自定义音乐格式（头部01 00 00 00） |
| .SND | 8 | MIDI音色配置（含乐器名flute2/alien1a等） |

### 2.5 调色板
| 文件 | 大小 | 格式 |
|------|------|------|
| PAL0 | 768 | 256色3字节RGB |
| PAL1 | 768 | 256色3字节RGB |

### 2.6 其他数据
| 文件 | 大小 | 说明 |
|------|------|------|
| TEST.PAK | 13344 | PAK归档/数据 |
| TEST.DIC | 168 | 字典/索引（28条目，每条目3个u16） |
| PRO.SCN | 2000 | 场景文件（u16数组） |
| RPG.SCN | 1938 | 场景文件（u16数组） |
| INSTALL.GDH | 24400 | 安装数据 |
| SETUP.GDH | 19964 | 设置数据 |
| MEMORY.TPC | 64772 | 内存驱动 |
| MOUSE.TPC | 64772 | 鼠标驱动 |
| GMOUSE.COM | 12650 | 鼠标驱动 |
| SYSTEM.CFG | 4 | 系统配置 |

## 3. 已破解格式

### 3.1 字体格式 (.15)
- **格式**: 16x16 1bpp位图字体
- **偏移**: 从文件头开始（offset=0）
- **每字符大小**: 32字节 (16*16/8)
- **字符数**: PRO.15=1024, RPG.15=908
- **头部**: 前12字节为0，然后`00 04 ff fe`
- **位顺序**: MSB first，每行2字节

### 3.2 调色板格式 (PAL0/PAL1)
- **格式**: 256色，每色3字节RGB
- **大小**: 768字节
- **颜色范围**: 0-63（6位），需要左移2位转换为0-255

### 3.3 MIDI音乐 (.MID)
- **格式**: 标准MIDI文件
- **曲目**: FAIL, FIGHT, MAIN, MAIN1, PASS, SPECIFY, TITLE, VICTORY

### 3.4 音效配置 (.SND)
- **头部**: `01 00 NN 00 SS 00` + 乐器名
  - NN: 乐器数量？
  - SS: 数据大小？
- **乐器名**: flute2, alien1a, frhorn1, logdrum1, oboe1, syn4
- **用途**: MIDI音色配置文件

## 4. 研究中格式

### 4.1 JMC格式（加密字节码脚本）

**重大修正**: JMC不是压缩归档，而是**加密的字节码脚本格式**。

**文件结构**:
```
偏移  大小  说明
0     70    JMC头部
42    2     第一块大小 (u16 little-endian)
70    N     第一块数据 (字节码脚本，加密)
70+N  ...   后续数据块 (资源数据，加密)
```

**各JMC第一块大小**:
| 文件 | 总大小 | 第一块大小 | 第一块范围 |
|------|--------|-----------|-----------|
| TEST.JMC | 861136 | 57006 | 70-57076 |
| PRO.JMC | 502704 | 38746 | 70-38816 |
| TITLE.JMC | 470704 | 4721 | 70-4791 |
| ENDA.JMC | 314992 | 4355 | 70-4425 |
| ENDB.JMC | 390144 | - | - |
| ENDC.JMC | 101472 | - | - |

**PLAY.EXE加载流程** (@0xef06函数):
1. 打开JMC文件
2. 读取70字节头部到内存@0xb164
3. cx = 头部@42的u16（第一块大小）
4. 读取cx字节到段0x207e:0
5. 关闭文件
6. 调用@0xf00f初始化（从头部@58/@59/@60读取参数，读取第一块首字节到@0xb15c）
7. 进入@0xf16f字节码解释器主循环

**字节码解释器** (@0xf16f主循环):
- 读取当前字节到@0xb15c
- 根据字节值分派到不同处理函数
- 每个命令处理后读下一字节，为0则循环回主循环

**字节码命令集**:
| 命令 | 说明 | 操作数 |
|------|------|--------|
| 0xf8 | 设置当前字节 | 1字节 |
| 0xfc | 场景切换 | 调用@0xf0c2，条件调用@0xf00f |
| 0xf0 | 位置/坐标处理 | 2字节(x,y)，可能搜索0xf7分隔 |
| 0x80-0x8f | 颜色/属性设置 | 无，属性存@0xb161 |
| 0x90-0x9f | 读取额外字节 | N字节(N=低4位)，0x00触发@0xe284 |
| 0xa0 | 绘制角色 | 1字节(精灵ID)，调用@0xe1b4 |
| 0xb0 | 读两字节输出 | 2字节 |
| 0xc0 | 查表绘制 | 1字节(索引)，查表@0x4edc，调用@0xe03c/@0xe140 |
| 0xd0 | 读一字节 | 1字节 |
| 0xe0 | 绘制大图 | 2字节(偏移)，调用@0xe1ef |
| 0x00 | 块结束/空操作 | 无 |

**加密确认**:
- 字节码反汇编：已知命令占比仅14-16%，84%为未知命令
- 字节频率均匀（256唯一字节，每个约150-400次）
- >=0x80字节约50%，<0x80字节约50%（随机数据特征）
- 未加密字节码预期：命令字节20-30%，操作数70-80%
- 反汇编结果混乱，已知命令出现像是随机巧合
- 第一块数据高熵，无明显文本或结构模式

**解密位置排查（capstone反汇编确认）**:
- @0xef06加载函数：直接int 0x21读文件到段0x207e:0，**无解密步骤**
- @0xf16f字节码解释器：直接`mov al, [si]`从段0x207e读取，**无解密步骤**
- 调用者@0xdb6e：`call @0xecc2 → call @0xef06 → call @0xf00f`，中间**无解密步骤**
- @0xf00f初始化：直接`lodsb`读取首字节，**无解密步骤**
- 结论：解密必须发生在其他位置（DOS中断钩子/TSR/驱动/程序启动时全局解密）

**ENDC.JMC特殊头部**:
- ENDC.JMC前16字节有明文结构：`00 00 fa 10 00 00 28 00 1e 03 01 00 00 00 02 78`
- 其他JMC头部看起来完全随机（加密）
- ENDC.JMC第一块数据仍加密（高/低字节各约50%，256唯一字节）
- 可能原因：ENDC.JMC是占位/空文件，或使用特殊密钥导致头部出现很多0
- @8=0x031e, @10=0x0001 与文件尾部模式 `1e 03 01 00` 对应

**尾部模式**:
- 所有JMC文件末尾附近存在 `1e 03 01 00 10 01 00` 模式
- PRO.JMC末尾精确: `...00 00 29 00 1e 03 01 00 10 01 00 82`
- TEST.JMC末尾: `...d6 06 30 00 00 2c 00 1e 03 01 00 10 01 00 4d 0a`
- 可能是JMC格式的结束标记或尾部元数据

**已证伪的解密方法**:
- 单字节XOR（0-255全部尝试）→ 无密钥
- 双字节XOR（65536种全部尝试）→ 无密钥
- ADD/SUB单字节 → 未找到
- HED前N字节作为XOR密钥 → 未找到
- zlib解压(wbits 15/-15/31/47) → 全部失败
- 位置XOR(pos&0xff/pos+1/pos^0xff/pos*7等) → 无有意义文本
- 7z打开为ARJ/ZIP → 失败
- 直接ARJ头解析 → 压缩大小远超文件大小（ARJ签名是数据巧合）

**ARJ函数集说明**:
- PLAY.EXE中确实存在ARJ函数: `OPENARJ`, `OPENARJ1`, `CLOSEARJ`, `ARJPAK`, `ARJVOC`, `ARJSEG`, `ARJOFT`
- 但这些可能用于处理其他资源（如VOC声音），而非JMC
- JMC文件中的ARJ签名(0x60 0xEA)是加密数据的随机巧合

**待研究**:
- 解密算法可能在@0xef06加载时通过某个钩子动态执行
- 可能需要用unicorn模拟PLAY.EXE的JMC加载流程获取解密后数据
- 或在DOSBox中运行游戏用调试器捕获内存中段0x207e的解密数据
- 70字节头部可能包含解密密钥（@58/@59/@60字段被@0xf00f读取）

### 4.2 HED索引文件
**TEST.HED分析**:
- 大小: 4303字节
- 头部: `04 09 00 00 01 00 00 00 00 9c 03 00 00 04 09 00`
- 重复值: `04 09 00 00` (=2308) 多次出现
- 结构: 不明显，可能是u16或u32数组

**PRO.HED分析**:
- 大小: 1248字节
- 头部: `27 5d 00 00 01 00 00 00 00 75 24 00 00 27 5d 00`
- 重复值: `27 5d 00 00` (=23847) 多次出现

**推测**: HED可能是JMC的文件索引，每个条目包含偏移、大小、文件名等信息。

### 4.3 NCC动画（已完全破解）
**结构**:
- 前128字节: 全0（头部/预留）
- @128开始: RLE压缩图像数据
- 320×200分辨率，8bpp（256色），直接写入VGA显存0xa000
- 多个NCC文件(END1/2/3, ENDA/B/C)的@128开始数据完全相同（共享背景）

**正确RLE算法**（从PLAY.EXE @0xfef3反汇编确认）:
```
跳过前128字节
for row in 0..199:
    col = 320
    while col > 0:
        b = read_byte()
        if (b & 0xC0) == 0xC0:    # 高2位==11，重复命令
            count = b & 0x3F       # 低6位=重复次数
            val = read_byte()      # 下一字节=重复值
            output [val] * count
            col -= count
        else:                      # 字面量，直接写入
            output b
            col -= 1
```

**关键反汇编**（PLAY.EXE @66291/0xfef3）:
```asm
mov ax, 0xa000        ; VGA显存段
mov es, ax            ; ES=目标
xor di, di            ; 显存偏移0
mov ds, [0xc36e]      ; DS=数据源段
mov si, 0x80          ; 跳过128字节
mov bp, 0xc8          ; 200行
mov bx, 0x140         ; 320列
loop:
  lodsb               ; 读字节
  mov cl, al
  and al, 0xc0        ; 取高2位
  cmp al, 0xc0        ; ==11?
  je repeat
  dec bx
  mov al, cl
  stosb               ; 字面量直接写入
  jmp loop
repeat:
  and cl, 0x3f        ; count=低6位
  sub bx, cx
  lodsb               ; 读重复值
  rep stosb           ; 重复写入
```

**之前错误原因**:
- 旧算法用最高位(0x80)判断重复，实际是高2位==0xC0判断
- 0x80-0xBF范围的字面量被错误当作重复命令，导致水平条纹
- 旧算法没有按行计数(320列)，而是全局解码

**解码结果**（全部正确）:
| 文件 | 压缩大小 | 解码后 | 颜色数 | 内容 |
|------|---------|--------|--------|------|
| TITLE.NCC | 32482 | 64000 | 163 | 标题画面：三武将骑马（PAL1蓝天更自然） |
| ENDA.NCC | 35414 | 64000 | 154 | 结局A：卷轴，武将乘船 |
| ENDB.NCC | 40196 | 64000 | 127 | 结局B：卷轴，众多武将头像 |
| ENDC.NCC | 42277 | 64000 | 135 | 结局C：宫殿，皇帝与宫女 |
| END1.NCC | 33673 | 64000 | 30 | 结局文字1（刘备统一三国） |
| END2.NCC | 32438 | 64000 | 32 | 结局文字2（曹魏王朝） |
| END3.NCC | 33626 | 64000 | 32 | 结局文字3（孙吴王朝） |

**调色板**:
- PAL0: 粉色天空变体
- PAL1: 蓝天自然色（更接近游戏实际显示）

### 4.4 MUS音乐格式
- 头部: `01 00 00 00` + 大量0
- 大小: 1535-10628字节
- 可能是自定义音乐序列格式

### 4.5 PAK归档 (TEST.PAK)
- 大小: 13344字节
- 头部: `04 01 0f 00 0d 08 32 01 04 02 13 0f 00 0c 08 32`
- 有重复模式，可能是索引表或脚本数据

### 4.6 DIC字典 (TEST.DIC)
- 大小: 168字节 = 28条目 × 6字节
- 每条目: 3个u16 (偏移?, 宽度?, 高度?)
- 条目示例: (0,14,15), (11,22,22), (44,20,24), (79,20,24)...
- 可能是精灵/图像的索引表

## 5. PLAY.EXE逆向发现

### 5.0 MZ头与代码段定位
- **MZ签名**: @0 `4D 5A`
- **e_cparhdr**: 64 (= 0x40) → 头部大小 = 64×16 = 1024字节
- **代码段起始**: @0x400 (文件偏移1024)
- **入口点**: @0x41c (e_ip=0x1c, e_cs=0)
- **程序类型**: 16位DOS MZ可执行文件

### 5.1 关键函数地址（文件偏移）
| 地址 | 函数 | 说明 |
|------|------|------|
| @0xef06 | JMC加载函数 | 读70字节头+cx字节到段0x207e |
| @0xf00f | JMC初始化 | 从头部@58/@59/@60读参数，读首字节到@0xb15c |
| @0xf16f | JMC字节码解释器 | 主循环，命令分派 |
| @0xed41 | AdLib音乐输出 | 向端口0x330/0x331写数据 |
| @0xe1b4 | 绘制角色 | 精灵绘制函数 |
| @0xe1ef | 绘制大图 | 大图像绘制函数 |
| @0xeb49 | MIDI加载 | 替换扩展名为.MID，读0x3c00=15360字节到段0x207e |
| @0xdfde | 文件加载 | 读6字节头+cx字节 |
| @0xe284 | 字符绘制/颜色处理 | 字体/文本渲染 |
| @0xe03c | 绘制函数A | 被0xc0命令调用 |
| @0xe140 | 绘制函数B | 被0xc0命令调用 |
| @0xf0c2 | 场景处理 | 被0xfc命令调用 |

### 5.2 关键函数名（字符串位置）
- @192613: `START`, `REPLAY`, `QUIT`, `ARJSEG`, `ARJOFT`, `OPENARJ`, `OPENARJ1`, `CLOSE_ALL`, `CLOSEARJ`, `ARJPAK`, `ARJVOC`
- @192671: `LOADMAP`
- @192990: `SETPAL`
- @193355: `ANIMPAL_P`
- @194744: `LOADMUSIC`
- @194754: `LOADVOC`
- @199791: `OPENDBF`
- @200139: `OPEN_JMC1`, `OPEN_JMC2`, `OPEN_JMC0`, `OPEN_JMC`, `STACKSEG`, `PRO_JMC`, `PRO_HED`, `FILE_JMC`, `FILE_HED`
- @202555: `SETPAL4`

### 5.3 资源文件名表
- @82896: `TEST.PAK`, `TEST.DIC`, `PAL0`, `PAL1`, `PRO.JMC`, `PRO.HED`, `TEST.JMC`, `TEST.HED`
- @102772: `RPG.15`, `RPG.SCN`
- @126966: `PRO.15`, `PRO.SCN`, `ATTRIB`
- @132772: 结局文件表（TITLE/ENDA/ENDB/ENDC的NCC/JMC/HED）

### 5.4 错误消息
- @127983: "ERROR: Open music file error.$"
- @128048: "ERROR: Read music file error.$"
- @128218: "ERROR: Open timbre file error.$"
- @128285: "ERROR: Read timbre file error.$"

## 6. 已提取资源

### 6.1 标准资源
- `music_mid/`: 8首MIDI
- `palettes/`: PAL0, PAL1 + 预览图
- `fonts/`: PRO.15, RPG.15 字体预览（16x16网格）
- `sound_snd/`: 8个SND音效配置
- `music_mus/`: 8个MUS音乐
- `ncc_anim/`: 7个NCC原始数据 + 测试渲染
- `scn_scenes/`: 2个SCN场景
- `TEST.PAK`, `TEST.DIC`, 其他数据文件

### 6.2 字体提取
- PRO.15: 1024字符，16x16 1bpp
- RPG.15: 908字符，16x16 1bpp
- 渲染为16x16网格PNG

## 7. 下一步计划

1. **JMC解密**（最高优先级，核心瓶颈）:
   - JMC确认为加密字节码脚本，简单XOR/ADD/zlib全部失败
   - 方向A: 用unicorn模拟PLAY.EXE的@0xef06加载流程，捕获段0x207e的解密数据
   - 方向B: 在DOSBox中运行游戏，用调试器在@0xef06返回后dump段0x207e内存
   - 方向C: 深入反汇编@0xef06和@0xf00f，寻找隐藏的解密步骤（可能在DOS中断钩子中）
   - 方向D: 分析70字节头部@58/@59/@60字段，可能是解密密钥或参数
   - 解密后可提取JMC中的全部游戏脚本和资源

2. **NCC渲染**（次高优先级）:
   - RLE解码正确（约64000字节=320x200），颜色范围176-255
   - 新方向：4bpp 16色假设（body≈32000字节），渲染有轮廓但噪点多
   - 已穷尽行优先/列优先/Mode X/块排列/颜色转换，均不对
   - 方向: 反汇编PLAY.EXE中的NCC加载/绘制函数，找到正确的解交织方式
   - 可能是压缩的Mode X 4平面格式，或先RLE再4bpp解包

3. **HED索引解析**:
   - TEST.HED(4303B)/PRO.HED(1248B)结构不明显
   - 头部包含重复u32值（TEST=2308, PRO=23847）
   - 可能是JMC的文件索引表，解密JMC后可对照验证

4. **MUS音乐转换**:
   - 头部`01 00 00 00`，自定义音乐序列
   - 可能与SND音色配置配合使用

5. **PAK/DIC解析**:
   - TEST.PAK(13344B)有重复模式
   - TEST.DIC(168B)=28条目×3u16，可能是精灵索引表

## 8. 脚本清单

| 脚本 | 说明 |
|------|------|
| 520_sghero_overview.py | SGHERO目录概览 |
| 521_sghero_jmc_hed.py | JMC+HED格式初步分析 |
| 522_sghero_hed_strings.py | HED字符串和u16值分析 |
| 523_sghero_jmc_analysis.py | JMC熵值/签名/zlib分析 |
| 524_sghero_jmc_signatures.py | JMC中PCX/BMP签名位置检查 |
| 525_sghero_playexe_strings.py | PLAY.EXE字符串搜索 |
| 526_sghero_arj_check.py | JMC中ARJ签名搜索 |
| 527_sghero_arj_parse.py | ARJ头解析（失败，字段加密） |
| 528_sghero_jmc_decrypt.py | JMC XOR/ADD解密尝试（全部失败） |
| 529_sghero_disasm_jmc.py | PLAY.EXE反汇编（代码段压缩） |
| 530_sghero_extract_standard.py | 标准资源提取 |
| 531_sghero_ncc_pak_analysis.py | NCC和PAK格式分析 |
| 532_sghero_ncc_render.py | NCC图像渲染 |
| 533_sghero_ncc_rle_test.py | NCC RLE算法变体测试 |
| 534_sghero_ncc_modex.py | NCC Mode X排列测试 |
| 535_sghero_playexe_mzheader.py | PLAY.EXE MZ头正确解析 |
| 536_sghero_disasm_entry.py | 入口点反汇编+函数开头搜索 |
| 537_sghero_jmc_load_func.py | JMC加载函数@0xef06分析 |
| 538_sghero_jmc_header.py | JMC 70字节头部字段解析 |
| 539_sghero_endc_analysis.py | ENDC.JMC特殊头部分析 |
| 540_sghero_jmc_decrypt_funcs.py | 反汇编JMC相关子函数 |
| 541_sghero_jmc_data_usage.py | 搜索段0x207e引用，定位字节码主循环 |
| 542_sghero_jmc_interpreter.py | 反汇编@0xf16f字节码解释器完整主循环 |
| 543_sghero_jmc_text_extract.py | JMC文本提取（乱码，确认加密） |
| 544_sghero_jmc_xor_decrypt.py | JMC XOR/位置XOR/ADD解密（全部失败） |
| 545_sghero_jmc_chunks.py | JMC分块结构分析（第一块大小=@42 u16） |
| 546_sghero_jmc_disasm.py | JMC字节码反汇编（确认加密，已知命令仅14-16%） |
| 547_sghero_jmc_full_disasm.py | 完整反汇编JMC加载函数（确认无解密步骤） |
| 548_sghero_capstone_disasm.py | 用capstone反汇编@0xf16f字节码解释器（确认无解密） |
| 549_sghero_jmc_encrypt_check.py | 验证JMC数据加密状态（高/低字节各50%） |
| 550_sghero_jmc_header_caller.py | 分析JMC头部和@0xef06调用者 |
| 551_sghero_endc_unencrypted.py | 分析ENDC.JMC特殊头部（明文结构但数据加密） |
| 552_sghero_ncc_deep.py | NCC深度分析，多种尺寸和块排列渲染 |
| 553_sghero_ncc_rle_variants.py | NCC RLE算法变体测试（A/B/C/D/E） |
| 554_sghero_ncc_palette.py | NCC调色板和宽度测试 |
| 555_sghero_ncc_color_convert.py | NCC颜色值转换测试（减0xb0/低4位/高4位） |
| 556_sghero_ncc_loader.py | 反汇编NCC加载函数搜索 |
| 557_sghero_ncc_4bpp.py | NCC 4bpp 16色图像测试（错误方向） |
| 558_sghero_mz_segments.py | MZ头完整段布局解析 |
| 559_sghero_reloc_ncc.py | 重定位表和NCC字符串引用分析 |
| 560_sghero_vga_refs.py | 搜索VGA显存0xa000写入代码（找到NCC解码器） |
| 561_sghero_ncc_correct_rle.py | **NCC正确RLE解码（高2位0xC0判断，全部7张图正确）** |

> **下文第 9 章起为 562–728 阶段的成果补记。第 4.1 节「JMC 加密字节码、最高优先级瓶颈」、第 7 节「下一步计划」中的 JMC/NCC 难题此后均已攻克，结论以第 9 章以后为准。**

---

## 9. JMC 容器完全破解：Huffman + LZ77（unicorn 模拟，805 块 0 失败）

### 9.1 以前错在哪

早期（523–554）把 JMC 当成「加密字节码脚本」，反复试 XOR / ADD / 位置 XOR / zlib / ARJ / Mode X / 4bpp，
熵值高、高低字节各约 50%，于是判定「数据加密、无解密步骤」，长期卡死。**根因是一直在数据侧找对称加密，
而真正的解码逻辑是一段可执行的 16 位解压例程，藏在 PLAY.EXE 内、由 far call 触发，纯字节统计永远看不出来。**

### 9.2 正确路径：让游戏自己的解压函数跑起来

- HED 是索引：每条 **13 字节**记录 = `u16 A(解压大小低字) / u16 B(64KB 块数) / u8 C(1=Huffman,0=纯拷贝) / u16 off_lo / u16 off_hi / u16 rest / u16 blk`；
  压缩长 = `blk*65536 + rest`，解压长 = `A + B*65536`。记录数 TEST=331 / PRO=96 / TITLE=105 / ENDA=72 / ENDB=91 / ENDC=110。
- 加载链：`@0x1ef0`（块加载解压包装）→ `@0x27c7`（lseek HED 读 13B、lseek JMC 读压缩数据到 `[0x40c]` 段）→
  `lcall 0xff5:0x34ad`（**Huffman+LZ77 解压核心**，输出到调用者 ES:DI）；`@0x133fd` 是 Huffman 主循环，`bl=0` 时走 `@0x137e2` 纯拷贝。
- 用 **unicorn 模拟**（脚本 600，禁止 DOSBox）：CODE_SEG=0x1000、FARC_CS=0x1ff5、入口物理 `0x1ff5*16+0x34ad=0x233fd`，
  MAIN/COMP/OUT/STACK 段分别 0x4000/0x5000/0x9000/0xe000，每块清零 0x34ad 字节的码表区，hook 到单地址 RETF 停止。
- **结果：6 个 JMC 共 805 块全部解压成功，0 失败**，产出 `jmc_decompressed/<前缀>/blkNNN_<大小>.bin` 与根目录 `_manifest.tsv`。

> 方法论教训：**「高熵 + 看不出明文」不等于加密**。对这种自带解压器的游戏，最稳的是反汇编定位 far call 解压入口，
> 再用 unicorn 直接执行原厂代码，比猜压缩算法快且不会错。

## 10. 解压块三分类、242 张裸位图、NCC+命令流合成 378 帧

805 块解压后按内容自动三分类（脚本 622）：**命令流 392 / 裸位图 242 / 其他 171**。

### 10.1 裸位图（脚本 607）

格式极简：`[u16 宽][u16 高][宽×高 索引像素]`，总长 = `4 + 宽×高`；全屏块 = 64004（320×200+4）。
共 242 张，含 **177 个 48×48 三国武将头像**、场景、战场背景、UI、标题、君主选择界面等；统一用 **PAL1** 渲染。
产物：`jmc_images/all_bitmaps/`（×PAL0/PAL1 共 484 张）、`TEST_sprites_48x48_contact.png`（177 头像拼图）。

![177个48×48武将头像拼图](images/sghero/TEST_sprites_48x48_contact.png)

### 10.2 NCC 动画（脚本 561，已完全破解）

跳过前 128 字节，320×200；逐字节：**高 2 位 == 0xC0 为 RLE 重复**（count=低 6 位，0 表示 64，下一字节为值），否则为字面量。
7 个 NCC（TITLE/END A/B/C、END1/2/3）全部正确解码。

### 10.3 @0xfd12 命令流透明精灵层（脚本 611–621）

部分块在裸背景之上还叠了一层**命令流精灵**（标题骑兵、结局宫女/武将群像等）。详见第 11 章。
最终用「NCC/位图背景 + 命令流透明层」**合成 378 帧完整画面**（脚本 621，`jmc_images/composited/`），
标题、结局 A/B/C 完美重建：

![标题画面合成](images/sghero/TITLE_blk000_17242_composite.png)
![结局C宫殿合成](images/sghero/ENDC_blk001_1561_composite.png)
![结局B武将群像合成](images/sghero/ENDB_blk000_11338_composite.png)

## 11. @0xfd12 命令流格式（13 命令，偶数编码，DI 16 位回绕）

### 11.1 定位

解释器运行时 CS 段相对值 = **0xfbf**，段内 IP=0x122；命令跳转表在主代码段偏移 **0xfbf4**（文件 0x400+0xfbf4）。
主循环：`DS=[0xc370]、ES=0xa000(显存)、SI=DI=0`，`lodsb → mov bl,al → jmp cs:[bx+4]`。
**命令字节是偶数（=2×命令号）**，表项在 `0xfbf4 + 命令字节`，处理程序主偏移 = 表项值 + 0xfbf0。映射存 `scripts/fd12_cmdmap.json`。

### 11.2 13 条命令

| 字节 | 命令 | 语义 |
|------|------|------|
| 0x00 | SKIP16 | lodsw n；`DI += n`（有符号） |
| 0x02 | SKIP8  | lodsb n；`DI += n` |
| 0x04 | COPY16e | lodsw cx；rep movsw（拷 2cx 字节，偶数收尾） |
| 0x06 | COPY16o | 2cx+1，末尾多一个 movsb |
| 0x08 | FILL16e | lodsw cx；lodsw val；rep stosw |
| 0x0a | FILL16o | 2cx+1，末尾多一个 stosb |
| 0x0c | MOVSW | 单字拷贝 |
| 0x0e | MOVSB | 单字节拷贝 |
| 0x10 | END | mov ds,0x13f3；ret |
| 0x12 | FILL8e | lodsb cx；lodsw val；rep stosw |
| 0x14 | FILL8o | 同上奇数收尾 |
| 0x16 | COPY8e | lodsb cx；rep movsw |
| 0x18 | COPY8o | 奇数收尾 |

**命令 0x1a 及以上的表项是垃圾**，解析中一旦遇到即说明不是该格式（曾据此证伪「blk203 用 fd12」的猜测，见第 13 章）。

### 11.3 一个隐蔽 bug：DI 是 16 位，负偏移要回绕

SKIP16 的 n 是**有符号**数，用于在显存里回退（跨行/对称精灵）。初版用 Python 任意精度整数做 `DI += n`，
遇到负 n 得到负索引，ENDC 两个对称宫女精灵一直错位。根因：真实 16 位 CPU 的 DI 只有 16 位，
必须 `DI &= 0xffff` **回绕**。修正后对称精灵正确（脚本 620）。
教训与第 12 章的 IP 回绕同源：**模拟 16 位代码时，所有指针/索引寄存器都要按 16 位截断，不能用宿主语言的宽整数。**

---

## 12. 重大纠错：16 位 near call 的 IP 回绕（曾白白浪费约 26 个脚本）

### 12.1 错误现象与误判

攻关 TEST 大块精灵时，追踪加载/绘制函数遇到大量 `e8 rel16`（near call），capstone 反汇编显示的目标地址 **超过 0xFFFF**（如 `e8 be 60` 显示 call 0x11ef0）。
当时想当然地认为「目标落在 0x10000–0x13300 这块在 EXE 文件里全为 0 的区域」，于是推断存在一个
**运行时才填充的 overlay 函数库 / BSS 动态代码区**，并花了脚本 653–678（约 26 个）去找：
排查 .OVL 文件、判定 MEMORY.TPC/MOUSE.TPC 是内存转储、扫描 805 个解压块里有没有 8086 代码块、
分析 EXE 末尾 50257 字节附加区……全部无果。

### 12.2 根因：16 位 CPU 的 IP 只有 16 位，会回绕

脚本 678 重新逐字节核算 `e8 rel16` 时才发现：真实 16 位 CPU 取指地址是

```
下一条指令IP = (caller_next_IP + rel16) & 0xFFFF      # 注意 & 0xFFFF
```

capstone 显示的是**未回绕**的线性值 0x11ef0，而真实 IP = `0x11ef0 & 0xffff = 0x1ef0`。
所谓「BSS overlay 函数」全都是**低地址真实函数的回绕别名**，根本不存在运行时填充的代码区：

| capstone 显示（错） | 回绕后真实地址 | 真实功能 |
|--------------------|----------------|----------|
| 0x11ef0 | 0x1ef0 | 块加载解压包装 |
| 0x1239d | 0x239d | 文本/汉字字模渲染（不是精灵！） |
| 0x136fd | 0x36fd | 随机数位运算 ror |
| 0x13144 | 0x3144 | **帧缓冲→显存透明 blit 主函数** |
| 0x11f19 | 0x1f19 | VGA DAC 调色板（mov dx,0x3c8; rep outsb） |
| 0x11f65 | 0x1f65 | 设置 ES=0x13f3 |
| 0x1149d | 0x149d | 精灵解码变体 A |
| 0x114bf | 0x14bf | 精灵解码变体 B |
| 0x11cc3 / 0x1072c / 0x11149 / 0x11ec7 / 0x10d5a | 0x1cc3 / 0x72c / 0x1149 / 0x1ec7 / 0xd5a | 各类低地址函数 |

### 12.3 规则固化（举一反三）

> **今后反汇编 16 位 8086 代码，凡 call/jmp 目标 > 0xFFFF，一律先 `& 0xFFFF` 再判断它落在哪个段；
> capstone/IDA 的线性地址不代表真实执行地址。** 配套的另一处基址错误：动作×方向分派表基址
> 一度少加 0x10000 算成 0xe0ce（脚本 682，反汇编全错位），脚本 693 纠正为 **主代码段 0x1e0ce（文件 0x1e4ce）**。

### 12.4 分派表与绘制调用链（纠正后）

`@0xbf29 call bx` 间接分派；`@0xbf25 mov bx,[bx+si+0xa19e]`，其中 bx = 20×动作 i、si = 2×方向 j、DS=0x13f3，
表基址物理 = `0x13f3*16 + 0xa19e = 0x1e0ce`。完整调用链见第 13 章与 `docs/014`。

---

## 13. 战场单位精灵 RLE 攻关全过程（TEST blk203–242）

这是本轮耗时最长、试错最多的一块，完整记录「怎么走错、又怎么蒙对」，避免重蹈覆辙。

### 13.1 数据现象

TEST.JMC 尾部有 20 组「大块（40976–56896 B）+ 96/78 B 配对表」。配对表 16（或13）条 ×6B =
`[off u16][b u16 宽][c u16 高]`，宽高为 95×75 / 86×78 / 106×85 / 132×68 / 57×63 等，明显是**战场单位精灵**。
RPGViewer 不识别这种私有格式，只能自己逆向。

### 13.2 走过的弯路（都已证伪，列出来避雷）

1. **当成 @0xfd12 命令流**（脚本 668–672）：Python 严格模拟与 unicorn 真实跑 @0xfd12 结果一致，
   blk203 从 tail@19841 解析，FILL/COPY 几条后 SI=20008 遇到命令 0x1a（>0x18，表项是垃圾），直接跑出解释器。
   **结论：blk203 用的是另一套解码器，不是 fd12。**
2. **按「行头 8 字节 tag + f1(NN 04) + f2(XX 00 行像素数) + 裸像素行体」手工切行**（脚本 689–692）：
   能看到 `08 e1 00 00`(888)、`08 ea 00 00`(308) 这类均匀分布的标记，以为是行魔数；
   后来证明 `08 e1` 只是 **RLE 命令字节 + 数据字节的巧合**，根本没有独立行魔数（见 13.4）。
3. **全段扫描 cmp 立即数找行标记**（脚本 688）：没有 `cmp al,0xc8/0xe1/0xea`、没有 `cmp ax,0xe108`，
   说明行边界不是靠魔数匹配，而是结构化命令流——这条反而是正确的方向提示。
4. **误以为存在 overlay/BSS**（见第 12 章），纯系 IP 回绕误判，浪费约 26 个脚本。

### 13.3 正确做法：顺着绘制调用链逐层下钻（纯静态，禁 DOSBox）

IP 回绕纠正后，调用链一次性贯通：

```
@0xbf29 动作分派(表0x1e0ce) → @0xc348 动作0 → @0xc416 动画坐标循环 → @0xc629 帧步进
→ @0xc70b/@0xc790 帧绘制
     @0xc714 帧缓冲初始化(rep stosw 填 0xFFFF = 透明)
     @0x149d/@0x14bf 解码变体A/B → @0x14db 解码主循环(按行)
        @0x1af7 读配对表(bx=f*6; si=off段号; [0x4a2]=宽b; [0x4a4]=高c)
        行分派表 @0x1c28 → @0x1c48 行RLE扫描 / @0x1cbe 块拷贝xlatb
        实际像素RLE @0x1556(表0x15a3) / @0x1977(表0x1a33) / @0x1a44(表0x1aeb)
     @0x3144 帧缓冲→显存透明blit(0xFF透明, scasb跳段, 像素原语@0x15af处理跨64KB段)
```

- **off 是段号不是字节偏移**：行扫描 @0x1c48 `mov si,cs:[0x1554]; add si,[0x402]; mov ds,si; xor si,si`，
  精灵 f 独占段 `[0x402]+off[f]`，字节偏移 = `off×16`。相邻精灵间隔约 220 段≈3520 B，16 个≈56320≈大块 56896，自洽。
- 找到三套 RLE 解释器，命令处理程序地址都拿到了，但**第一次在数据上解析仍然全部失败**（见 13.4）。

### 13.4 最后一层窗户纸：命令字节是偶数（怎么蒙对的）

最初按跳转表「表项序号 = 命令号」的直觉，认为命令是 0–5 的连续值，于是写解析器把数据首字节当 0–5：
- 精灵 0 开头 `00 5f 08 e1 00`：解成「cmd0 SKIP8, n=0x5f=95」后，下一字节是 **0x08**，超出 0–5 → 非法；
- 暴力扫描精灵段内**每一个**偏移作为起点（脚本 719），**没有任何一个**能解析出 ≥5 行，全部失败。

回头重读解释器主循环 `lodsb → mov bl,al → jmp cs:[bx + 表基址]`：**bx 就是命令字节本身，不是除以 2**。
跳转表每项 2 字节，于是偶数字节 0x00/0x02/0x04/0x06/0x08/0x0a 依次命中第 0/1/2/3/4/5 个处理程序，
奇数字节命中的是相邻两表项字节拼出来的垃圾、永不会出现。也就是说**命令字节 = 2×命令号（偶数编码）**——
这与第 11 章 @0xfd12 命令流「命令字节全偶数」是**同一套编码习惯**，之前在 fd12 已经踩过一次，这里差点又没第一时间反应过来。

按偶数编码重读开头 `00 5f 08 e1 00`：

| 字节 | 解码 |
|------|------|
| `00 5f` | cmd0 SKIP8，n=95（跳过一整行宽=整行透明） |
| `08 e1 00` | cmd4 NEWLINE（0x08）+ 2 字节参数 e1 00，换行 |

连续 7 组 = 精灵顶部 7 行全空。改完编码（脚本 723）精灵 0 立刻解出 **75 行 × 每行恰 95 像素**，
行 0–6 全透明、行 7 起非透明像素 6→21→31→33 递增，骑兵轮廓自上而下显现，cmd0x0a(END) 在 75 行后正确收尾。

> **复盘**：卡点不在压缩算法本身（RLE 很简单），而在「命令编号 ↔ 命令字节」这层映射。
> 判据是跳转表用 `jmp [bx+table]` 且 bx 直接等于读到的字节、表项 2 字节——此时命令字节必然是偶数步进。
> 暴力扫描全失败本身就是强信号：不是起点问题，是命令集理解错了。

### 13.5 批量解码结果：330 张，0 失败

脚本 726 自动扫描所有配对表（96B=16 精灵 / 78B=13 精灵），共 **21 组、330 个战场单位精灵全部解码成功**，
PAL1 渲染、0xFF 透明，产物在 `jmc_images/battle_units/`，格式规范与参考实现见 **`docs/014`**。

全兵种总览（蓝方玩家 blk203–221 / 红方敌方 blk223–241 同兵种异色一一对应，blk243 为空马+步兵）：

![全兵种总览](images/sghero/units_overview.png)

代表兵种联系表：

| 骑兵基础(长枪) blk203 | 长枪突刺 blk213 | 弓骑兵 blk217 |
|---|---|---|
| ![](images/sghero/contact_blk203.png) | ![](images/sghero/contact_blk213.png) | ![](images/sghero/contact_blk217.png) |

| 刀骑兵 blk205 | 剑骑兵 blk209 | 斧戟重骑 blk215 |
|---|---|---|
| ![](images/sghero/contact_blk205.png) | ![](images/sghero/contact_blk209.png) | ![](images/sghero/contact_blk215.png) |

| 冲锋突刺 blk219 | 红方弓骑 blk237 | 空马+步兵 blk243 |
|---|---|---|
| ![](images/sghero/contact_blk219.png) | ![](images/sghero/contact_blk237.png) | ![](images/sghero/contact_blk243.png) |

**帧布局**：每组帧 0–11（95×75）是侧视骑兵的行走/待机**步态循环**（马朝左、马蹄交替），
帧 12–15（尺寸更大，86×78 / 106×85 / 132×68 等）是**攻击动画**（挥刀/劈剑/突枪/射箭/冲锋，含刀光、剑气、箭矢等特效帧）；
弓骑兵组（217/237，13 帧）末帧是独立的箭矢飞行精灵。多朝向由动作×方向分派表（0x1e0ce，动作 i×20、方向 j×2）
在运行时组合，坐标为负时走变体 B（@0x14bf，命令经 cs:[di+0x2ce4] 指针表取流）做水平翻转。

---

## 14. PLAY.EXE 内存段布局与关键函数速查（回绕后真实地址）

PLAY.EXE：202801 字节，16 位 DOS MZ。头部 0x400（e_cparhdr=0x40）；MZ 映像 = (298−1)×512+480 = **152544 B**，
文件末尾另有 **50257 B overlay 数据**（文件 @0x253e0 起，结构化记录数组，非代码）。主数据段 DS=ES=SS=**0x13f3**，VGA 显存 0xa000。
映射：主代码段偏移 X → 文件偏移 `0x400 + X`。capstone：`Cs(CS_ARCH_X86, CS_MODE_16)`，`disasm(exe[0x400+a:0x400+b], a)`。

### 14.1 内存分配（@0x1d9d，int21 ah=0x48，bx=0x6900）

```
cs:[0x16] = 分配基址
[0x402] = cs:[0x16]+0x1100   # 大块精灵段（blk0xcb+2t 解压到 ES=[0x402]:0）
[0x400] = [0x402]+0xafc
[0x404] = [0x400]+0x1000 ; [0x3fe]=[0x404]
[0x406] = [0x3fe]+0xfa0
[0x40e] = [0x406]+0x1000
[0x40c] = [0x40e]+0x200     # 压缩数据源段
cs:[8]  = [0x40c]+0x400
```

### 14.2 关键段变量

| 变量 | 含义 |
|------|------|
| [0x40c] | 压缩数据源段 |
| [0x408] | 解压/绘制目标段（@0x1f2c 设 0xa000） |
| [0x402] | 大块精灵段基址 |
| [0x406]/[0x412]/[0x414]/[0x416] | 帧缓冲段链 |
| [0x4a0] | 主数据段缓存（0x13f3） |
| [0x4a2]/[0x4a4] | 当前精灵宽 b / 高 c |
| [0x4a6]/[0x4a8] | 目标 x / y（cs:[0x1550]/[0x1552]） |
| cs:[0x1554] | 当前精灵 off 段号 |
| cs:[0xc636] | 当前帧号 |
| cs:[0x239b] | 文本行 stride |

### 14.3 关键函数（均为 &0xffff 回绕后地址）

| 地址 | 功能 |
|------|------|
| @0x1ef0 | 块加载解压包装（call 0x27c7；lcall 0xff5:0x34ad 解压到 ES:DI） |
| @0x27c7 | HED 块加载（lseek 读 13B 到 0x5285，读压缩数据到 [0x40c]） |
| @0x133fd | Huffman 解压主循环（bl=0 走 @0x137e2 纯拷贝） |
| @0xfd12 | 命令流解释器（运行 CS=0xfbf，见第 11 章） |
| @0xfef3 | NCC 解码 |
| @0x239d | 文本/汉字字模渲染（mul 0x9d 字模、逐位绘制、int21 读 30B 记录），**非精灵** |
| @0x1f19 | VGA DAC 调色板（mov dx,0x3c8; rep outsb） |
| @0x1d9d | 内存分配（ah=0x48） |
| @0xbf29 | 动作×方向 call bx 分派（表 0x1e0ce） |
| @0xc348 / @0xc416 / @0xc629 | 动作0绘制 / 动画坐标循环 / 帧步进 |
| @0xc70b/@0xc790 | 帧绘制（@0xc714 初始化帧缓冲 + @0x149d/@0x14bf 解码） |
| @0x3144 | 帧缓冲→显存透明 blit（0xFF 透明、scasb 跳段、call 0x15af） |
| @0x149d/@0x14bf | 精灵解码变体 A / B（设 3 行函数指针后 call 0x14db） |
| @0x14db | 解码主循环（@0x1af7 设源/宽高/裁剪，按行 call cs:[bp+0x1c28]） |
| @0x1af7 | 源/宽高/裁剪设置（bx=f*6，读 off/b/c） |
| @0x1c48 | 裁剪行 RLE 扫描（DS=[0x402]+off 段，跳转表 @0x1ca3） |
| @0x1556/@0x1977/@0x1a44 | 三套像素 RLE 解释器（表 @0x15a3/@0x1a33/@0x1aeb） |
| @0x15af | 跨段像素拷贝原语（处理跨 64KB 段、bp/si 前进、行边界、裁剪） |

### 14.4 三套 RLE 跳转表（命令字节偶数，命令号=字节/2）

| 解释器 | 表基址 | cmd0 | cmd1 | cmd2 | cmd3 | cmd4换行 | cmd5结束 |
|--------|--------|------|------|------|------|----------|----------|
| @0x1556 | 0x15a3 | 0x1565 SKIP8 | 0x1574 SKIP16 | 0x1581 COPY8 | 0x1591 COPY16 | 0x159f | 0x15a2 |
| @0x1977 | 0x1a33 | 0x198b | 0x19a6 | 0x19bf | 0x19f8 | 0x1a2f | 0x1a32 |
| @0x1c48(行扫描) | 0x1ca3 | 0x1c64 | 0x1c6d | 0x1c78 | 0x1c85 | 0x1c90 | 0x1c9e |

---

## 15. 当前提取总览与后续

### 15.1 已提取（extracted/SGHERO_超时空英雄传说/）

- `jmc_decompressed/`：805 个解压块 + 根目录 `_manifest.tsv`（TEST 331 / PRO 96 / TITLE 105 / ENDA 72 / ENDB 91 / ENDC 110）
- `jmc_images/all_bitmaps/`：242 张裸位图 ×PAL0/PAL1（含 177 个 48×48 武将头像）
- `jmc_images/composited/`：378 帧 NCC/位图背景 + 命令流精灵层合成完整画面（标题/结局 A/B/C）
- `jmc_images/cmdstream/`：392 个命令流透明层 PNG
- `jmc_images/battle_units/`：**330 张战场单位精灵（21 组，0 失败）+ 21 张联系表 + `_ALL_UNITS_OVERVIEW.png`**
- `ncc_anim/`、`music_mid/`(8)、`sound_snd/`(8)、`music_mus/`(8)、`palettes/`、`fonts/`、`scn_scenes/`(2)

### 15.2 后续待办

1. 其余非位图非命令流块（约 130 个）内容类型识别：60000B 块×15（TEST 头 `68 0e` 重复）、6600B 块×15（头全 ff）、
   4B 块×33（`0000fa10`）、96/120/54/28B 小块、PRO 每 5 个一组规律块（blk21-60：864/120/21240/1416/14641）、TEST blk330 查找表(8123)。
2. 游戏文本系统提取：武将名/对话/属性繁体中文（manifest 标 text 的 20 块多为偏移表，可能在非位图块，试 Big5/GBK）。
3. MUS 音乐格式（70 头+序列，加载到段 0x207e，@0xe5ec 播放、@0xe403 序列解析）；两个 .15 字体字符映射（PRO.15=32768、RPG.15=29070）。
4. TEST.PAK(15088)/TEST.DIC(186≈31×6B 三元组)；EXE 末尾 50257B overlay 记录数组（@0x253e0）；8 组间接 jmp 解释器（@0x2f39 等）。
5. 变体 B（@0x14bf / cs:[di+0x2ce4] 命令指针表）的水平翻转可用 unicorn 复核，用于补全右朝向精灵。

---

## 附录 A：脚本清单续（562–728）

| 脚本 | 说明 |
|------|------|
| 600_sghero_decomp_all.py | **unicorn 模拟 lcall 0xff5:0x34ad，6 个 JMC 805 块 Huffman+LZ77 全解压（0 失败）** |
| 607_sghero_render_all_bitmaps.py | **242 张裸位图批量渲染（含 177 个 48×48 头像），PAL0/PAL1** |
| 561_sghero_ncc_correct_rle.py | NCC 正确 RLE（高 2 位 0xC0） |
| 611–620 | @0xfd12 命令流定位、CS 段=0xfbf、跳转表 0xfbf4、13 命令、DI 16 位回绕修复、全块解码 |
| 618_sghero_scan_cseg.py | 命令流 CS 段扫描 |
| 620_sghero_decode_cmd_all.py | 392 命令流块批量解码为透明层 PNG |
| 621_sghero_composite_ncc_cmd.py | **NCC/位图背景 + 命令流层合成 378 帧完整画面** |
| 622_sghero_classify_all.py | 805 块三分类（cmdstream392/bitmap242/unknown171） |
| fd12_cmdmap.json | @0xfd12 13 命令映射表 |
| 644–647 | VGA 显存函数排除：@0xcb2f 清屏、@0xcb40 60 单位渲染循环、地形 flood-fill（均非精灵解码） |
| 649–652 | blk203 加载路径：块 ID=0xcb+2*type、目标段 [0x402]、配对表到主数据段:0xde |
| 653–658 | **（后证伪）BSS/overlay 误判排查**：无 .OVL、TPC 是转储、805 块无代码块、EXE 附加区非代码 |
| 659–667 | 块记录锚点、tail 分析、行切分尝试（后被 RLE 命令流取代） |
| 668–672 | **@0xfd12 证伪**：Python 严格模拟与 unicorn 一致，blk203 遇 0x1a 跑出解释器 |
| 673–677 | @0x1ef0 块加载包装、BSS 填充排查、EXE overlay 扫描 |
| 678_sghero_bss_call_scan.py | **关键：重算 e8 rel16 发现 16 位 IP 回绕（&0xffff）** |
| 679_sghero_disasm_239d.py | @0x239d 文本/汉字字模渲染（排除为精灵解码器） |
| 680_sghero_real_targets.py | 回绕目标重标（0x11ef0→0x1ef0 等全映射） |
| 681–693 | 动作×方向分派表：0xe0ce 错误基址（682）→ 纠正 **0x1e0ce（693）**；绘制函数打分 |
| 694–710 | 绘制调用链逐层下钻：c416→c629→c70b/c790→c714 帧缓冲→3144 透明 blit |
| 711_sghero_disasm_149d.py | 定位帧缓冲 RLE 解释器 @0x1556（跳转表 0x15a3） |
| 712_sghero_rle_table.py | dump RLE 跳转表、@0x15af 像素拷贝、@0x1af7 行循环设置 |
| 713_sghero_disasm_copy_rest.py | @0x15af 跨段像素拷贝剩余逻辑 |
| 714_sghero_disasm_setup.py | 解码前 DS 段/帧号/基址设置（找到第二套解释器 @0x1a83） |
| 715_sghero_row_dispatch.py | 行分派表 @0x1c28（16 项）与行函数 |
| 716_sghero_row_rle.py | 行 RLE @0x1c48（表 0x1ca3）、块拷贝 xlatb、内存分配链 |
| 717_sghero_disasm_1977.py | @0x1977 带裁剪 RLE（表 0x1a33） |
| 718–720 | RLE 解析尝试（误把命令当 0–5 连续值，全失败）、暴力扫描起点（0 个≥5 行）、dump 全部 4 跳转表 |
| 721_sghero_sprite0_struct.py | 配对表 16 记录、精灵 0 段范围、头部 5 字节单元分析 |
| 722_sghero_variantB.py | 变体 B（@0x2868/@0x2e24，cs:[di+0x2ce4] 命令指针表，水平翻转） |
| 723_sghero_decode_sprite.py | **改用偶数命令编码，精灵 0 成功解出 75×95** |
| 724_sghero_decode_all_units.py | 3 组大块 48 精灵解码渲染 + 联系表 |
| 725_sghero_scan_unit_groups.py | 扫描全部 96/78B 配对表，发现 21 组；比较 blk203/223 异色 |
| 726_sghero_decode_all_groups.py | **全量 21 组 330 精灵解码，0 失败** |
| 727_sghero_frame_layout.py | 16 帧布局/重心分析（0–11 步态循环、12–15 攻击） |
| 728_sghero_units_overview.py | 生成全兵种总览图鉴 `_ALL_UNITS_OVERVIEW.png` |

> 配套格式规范：**`docs/014_SGHERO_战场单位精灵RLE格式规范.md`**（含可复现 Python 参考实现）。




