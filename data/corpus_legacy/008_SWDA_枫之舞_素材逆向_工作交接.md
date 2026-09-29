# SWDA 轩辕剑外传枫之舞 — 素材逆向工作交接文档

> **交接日期**: 2026-09-09
> **状态**: 进行中（语音提取完成，图像素材未完成）
> **接手人**: 下一位逆向专家
> **目标**: 从 SWDA（大宇资讯 1995）提取图像/语音/音乐素材

---

## 一、项目基本信息

| 项 | 值 |
|---|---|
| 游戏 | 轩辕剑外传枫之舞（SWDA） |
| 发行商 | 大宇资讯 |
| 发行年份 | 1995 |
| 原始目录 | `E:\BaiduNetdiskDownload\dos\0001_经典DOS游戏合集(绿色免安装完整硬盘版)@www.emu618.com\SWDA` |
| 工作副本 | `C:\src\InformationSecurity\dosgames\work\swda\`（339 文件，已完整复制） |
| 输出目录 | `C:\src\InformationSecurity\dosgames\extracted\SWDA_枫之舞\` |
| 项目根目录 | `C:\src\InformationSecurity\dosgames\` |

---

## 二、环境配置（必须记住）

### 2.1 Python 环境
- **Python 路径**: `E:\Users\Administrator\miniconda3\python.exe`
- 已安装 Pillow（图像处理）
- 无其他特殊依赖

### 2.2 工具
- **DOSBox-X**: `E:\tools\dosbox\bin\x64\Release SDL2\dosbox-x.exe`
  - 已验证可启动枫之舞（密码输入画面正常显示）
  - 首次启动会弹"选择工作目录"对话框，点 Choose → 是(Y) 即可
  - 配置文件: `C:\src\InformationSecurity\dosgames\work\swda.conf`
- **IDA Pro 7.6**: `E:\BaiduNetdiskDownload\IDA7.6`（之前烈焰钢狼传用过，可用）

### 2.3 脚本规范
- 脚本目录: `C:\src\InformationSecurity\dosgames\scripts\`
- 当前最大脚本编号: **218**
- 命名规则: `{序号}_{功能}.py`
- 每个脚本顶部必须有详细注释

---

## 三、已完成的工作（100% 确认）

### 3.1 语音提取（✅ 完成）

**结果**: 135 个 WAV 文件，全部可正常播放。

**输出位置**: `extracted\SWDA_枫之舞\01_voice\SP000.wav` ~ `SP135.wav`

**方法**:
1. SWDA 目录下有 136 个 `.VOC` 文件（Creative Voice File 标准格式）
2. 用标准 VOC → WAV 转换流程批量转换
3. 脚本: `scripts\202_swda_rix_voc.py`、`203_swda_voc.py`

**注意**: SP000.wav 只有 47 字节，是占位文件（空语音）。

---

### 3.2 LZSS 压缩算法（✅ 确认可精确解压）

**算法参数（已验证）**:
- 标准 LZSS 变体
- 控制字节: 8位，bit=1 表示引用，bit=0 表示字面量
- 引用格式: `off = ((b1 & 0xF) << 8) | b2`, `len = (b1 >> 4) + 3`
- 窗口大小: 4096（12 位 offset）

**已验证解压的文件**:

| 文件 | 压缩大小 | 解压后大小 | 状态 |
|---|---|---|---|
| MENU.RSK | 18955 | 56654 | ✅ 精确 |
| BA01.RSK | ? | 47125 | ✅ 精确 |
| DOR1.RSK | 30924 | 50089 | ✅ 精确 |
| ME01.RSK | 16563 | 31778 | ✅ 精确 |

**解压后文件位置**: `extracted\SWDA_枫之舞\{NAME}_decomp.bin`

**脚本**:
- `204_swda_lzss.py` — LZSS 解压核心函数
- `207_swda_lzss2.py` — 改进版
- `214_swda_lzss_b.py` — 批量解压

---

### 3.3 .LSK 资源包结构（✅ 确认）

**4 个资源包**:

| 文件 | 大小 | 推测内容 |
|---|---|---|
| MAP.LSK | 5.5 MB | 地图数据 |
| DO.LSK | 4.8 MB | 地牢/野外 |
| SA.LSK | 2.1 MB | 场景 A |
| CD.LSK | 1.4 MB | CD 音乐/过场 |

**结构格式**:
```
头部: N 个 u32 小端偏移表（指向每个数据块）
数据块格式:
  u16  解压后大小
  u8   0x01（压缩方法标识）
  u8   类型编号（5/22/29/33/39 等）
  N 字节 LZSS 压缩数据
```

**脚本**: `201_swda_lsk.py`

---

### 3.4 VGA DAC 调色板写入位置（✅ 确认）

在 `RPG.EXE` 中找到 **2 处** VGA DAC 写入指令:

| 地址 | 指令 | 说明 |
|---|---|---|
| 0x6FDC | `mov dx,03C8h; out dx,al` | 设置调色板索引 |
| 0x6FE7 | `mov dx,03C9h; out dx,al` × 3 | 写 RGB |

**关键代码分析**:
```asm
0x6FD5: mov si, 64FC        ; 调色板源基址
0x6FD8: add si, [6DFE]      ; 加上当前调色板偏移
0x6FDC: mov dx, 03C8h       ; DAC 索引端口
0x6FDF: out dx, al          ; 写索引
0x6FE0: mov cx, 02FA        ; 762 字节 = 254×3
0x6FE3: sub cx, [6DFE]      ; 减去已写数量
0x6FE7: mov dx, 03C9h       ; DAC 数据端口
0x6FEA: out dx, byte [ds:si]; 读调色板数据
0x6FEB: loop 0x6FEA         ; 循环写
```

**结论**: 调色板数据在内存偏移 `0x64FC + [0x6DFE]` 处，768 字节（256色 × 3通道，6位 DAC）。

**注意**: 这是**运行时内存地址**，不是文件偏移。需要用 IDA 或 DOSBox 调试器确定段基址后才能定位到文件中的实际位置。

**脚本**: `215_swda_dac_search.py`、`216_swda_dac_context.py`

---

## 四、未解决的问题（❌ 待攻克）

### 4.1 图像素材渲染（❌ 核心卡点）

**现状**: LZSS 解压成功，但解压后的数据渲染为噪点。

**已尝试的方案（全部失败，不要重试）**:

| 方案 | 结果 | 原因推测 |
|---|---|---|
| 24位 RGB 直接渲染 | 噪点 | 不是 RGB 格式 |
| RGB565 渲染 | 噪点 | 不是 16 位色 |
| 索引色 + DO.LSK@161872 调色板 | 噪点 | 调色板不对 |
| 索引色 + DO.LSK@161872 调色板（dopal 版） | 噪点 | 同上 |
| 索引色 + EXE 内调色板候选 | 噪点 | 调色板不对 |
| 不同宽度（318/320/322/640） | 噪点 | 不是宽度问题 |

**观察到的数据特征**:
- MENU_decomp.bin 开头: `83 9D EE 83 9D EE ...` 每 3 字节重复
- 疑似索引色数据，但调色板不匹配

**可能原因（按优先级排序）**:
1. **调色板不对** — 游戏有多个场景调色板，当前用的不是对应场景的调色板
2. **像素布局有子结构** — 解压后的数据不是直接像素流，可能有帧头/命令流
3. **离屏缓冲区 pitch 不是 320** — 参考神雕侠侣经验：物理 320 但离屏缓冲可能是 400

---

### 4.2 调色板定位（❌ 未完成）

**已做的尝试**:
1. 在 RPG.EXE 里搜 768 字节连续数据 → 找到多个候选，但渲染都不对
2. 在 DO.LSK @161872 找到疑似调色板（768 字节）→ 渲染噪点
3. 从 DOSBox 实机截图提取颜色 → 得到关键颜色 RGB 值
4. 用屏幕颜色反推 6 位 DAC 值，在文件里搜匹配 → RPG.EXE @0x12686 匹配 3/8 关键颜色（不够精确）

**从实机截图得到的关键颜色（RGB 8位）**:
- 绿色按钮: `(20, 182, 20)` → DAC `(4, 44, 4)`
- 蓝色按钮: `(28, 48, 243)` → DAC `(6, 11, 60)`
- 黄色按钮: `(255, 235, 69)` → DAC `(63, 58, 17)`
- 红色按钮: `(243, 28, 28)` → DAC `(60, 6, 6)`
- 暗黄: `(223, 199, 0)` → DAC `(55, 49, 0)`
- 暗红: `(178, 0, 0)` → DAC `(43, 0, 0)`
- 白色: `(255, 255, 255)` → DAC `(63, 63, 63)`
- 黑色: `(0, 0, 0)` → DAC `(0, 0, 0)`

**下一步建议**:
- 用 IDA Pro 7.6 打开 RPG.EXE，定位 0x6FDC 处的调色板写入函数
- 追踪 `[0x6DFE]` 变量的来源，确定初始调色板在文件中的位置
- 或者用 DOSBox-X 的 Debug → Dump VGA RAM 功能直接 dump 帧缓冲区和调色板

---

## 五、文件结构总览

### 5.1 主程序文件
| 文件 | 大小 | 说明 |
|---|---|---|
| SWDA.EXE | 18947 | 启动器 |
| RPG.EXE | 95730 | 主游戏引擎（含调色板写入代码） |
| FIG.EXE | 79762 | 战斗模块 |
| MEO.EXE | 27954 | 菜单/动画模块 |
| MAPA.EXE | 65492 | 地图模块 |
| ORC.EXE | 54284 | 怪物/精灵模块 |
| ITEM.EXE | 50121 | 物品模块 |

### 5.2 资源文件
| 类型 | 数量 | 说明 |
|---|---|---|
| .LSK | 4 | 压缩资源包（LZSS） |
| .RSK | 多个 | 压缩资源文件（LZSS） |
| .VOC | 136 | 语音文件（已转 WAV） |
| .RIX | 多个 | 索引/地图数据（AA55 标志） |
| .DSK | 16 | 软盘映像（CHNA*.DSK 配套 CHNA*.EXE） |

### 5.3 脚本清单（SWDA 相关）
| 脚本 | 功能 |
|---|---|
| 201_swda_lsk.py | .LSK 资源包结构分析 |
| 202_swda_rix_voc.py | .RIX/.VOC 分析 |
| 203_swda_voc.py | VOC → WAV 批量转换 |
| 204_swda_lzss.py | LZSS 解压核心 |
| 205_swda_rsk_dsk.py | .RSK/.DSK 分析 |
| 206_swda_strings.py | 字符串提取 |
| 207_swda_lzss2.py | LZSS 改进版 |
| 208_swda_decomp_analyze.py | 解压后数据分析 |
| 209_swda_decomp_images.py | 解压后图像尝试渲染 |
| 210_swda_render.py | 渲染测试 |
| 211_swda_palette_search.py | 调色板搜索 |
| 212_swda_render_pal.py | 用找到的调色板渲染 |
| 213_swda_render_dopal.py | 6位 DAC 调色板渲染 |
| 214_swda_lzss_b.py | 批量 LZSS 解压 |
| 215_swda_dac_search.py | VGA DAC 写入搜索 |
| 216_swda_dac_context.py | DAC 写入上下文分析 |
| 217_swda_screen_colors.py | 实机截图颜色分析 |
| 218_swda_pal_match.py | 屏幕颜色反推调色板匹配 |

---

## 六、历史经验参考（来自前序项目）

### 6.1 神雕侠侣（智冠 CONDOR 引擎）经验
- 调色板**不在 EXE 里**，在运行时数据中（神雕在 EAGLEN.DAT @0x251）
- 离屏缓冲区 pitch 可能不是 320（神雕是 400）
- 用 IDA 追踪 `out 3C8h/3C9h` 找 VGA DAC 写入定位调色板
- RLE 命令格式：按命令字节最高 2 位区分（跳过/复制/填充）

### 6.2 烈焰钢狼传经验
- 调色板优先于图片解码
- 反汇编验证格式假设
- 按行压缩的 RLE，每行独立

---

## 七、下一步行动建议（按优先级）

### 优先级 1：用 IDA Pro 定位调色板（最推荐）
1. 用 IDA Pro 7.6 打开 `RPG.EXE`
2. 定位地址 `0x6FDC` 处的调色板写入函数
3. 追踪 `[0x6DFE]` 变量的来源
4. 找到初始调色板数据在文件中的位置
5. 提取 768 字节调色板，用它渲染解压后的图像

### 优先级 2：DOSBox-X Debug dump
1. 启动枫之舞到标题画面
2. 用 DOSBox-X 的 `Debug` 菜单 → `Dump VGA RAM`
3. 直接 dump 帧缓冲区（320×200 索引色）
4. 同时 dump VGA DAC 调色板
5. 对比 dump 的调色板和文件中的数据

### 优先级 3：分析解压后数据的子结构
1. 用十六进制编辑器打开 `MENU_decomp.bin`
2. 仔细分析开头的结构
3. 是否有帧头（width/height）？
4. 是否有命令流（类似 CMP 的 RLE 命令）？
5. 参考烈焰钢狼传的 CMP 命令集分析方法

---

## 八、死路清单（不要重试）

以下方法已验证失败，**不要浪费时间重试**:

1. ❌ 24 位 RGB 直接渲染解压数据 → 噪点
2. ❌ RGB565 渲染 → 噪点
3. ❌ DO.LSK @161872 调色板 → 噪点
4. ❌ RPG.EXE 内直接搜 768 字节调色板候选 → 匹配度不够
5. ❌ 尝试不同宽度（318/320/322/640）→ 噪点不变
6. ❌ 直接用屏幕截图颜色反推调色板索引 → 匹配度仅 3/8

---

## 九、Git 状态

- 项目根目录: `C:\src\InformationSecurity\dosgames\`（已初始化 git）
- 最近提交: `998f5da`（SWDA LZSS + 135 语音）
- 未提交变更: 交接文档、最新脚本

---

## 十、关键文件速查

| 用途 | 路径 |
|---|---|
| 原始游戏文件 | `E:\...\SWDA\` |
| 工作副本 | `C:\src\InformationSecurity\dosgames\work\swda\` |
| 解压后 BIN | `extracted\SWDA_枫之舞\*_decomp.bin` |
| 语音 WAV | `extracted\SWDA_枫之舞\01_voice\` |
| 失败的渲染图 | `extracted\SWDA_枫之舞\*_w*.png` |
| 分析脚本 | `scripts\201~218_swda_*.py` |
| 配置文件 | `work\swda.conf` |
| 实机截图 | `work\swda_screen*.png` |

---

> **交接人备注**: 语音提取已完成，LZSS 算法已确认。图像渲染卡在调色板定位——核心线索是 RPG.EXE @0x6FDC 的 VGA DAC 写入代码，追踪 `[0x6DFE]` 变量应该能找到调色板在文件中的实际位置。用 IDA 做这件事是最可靠的路径。祝好运！
