# 009 SWDA 枫之舞素材逆向 — 交接评审与再定位报告

> **评审日期**: 2026-09-09（接手人：千问工作助理）
> **评审对象**: `docs/008_SWDA_枫之舞_素材逆向_工作交接.md`
> **结论级别标注**: ✅确认 / ⚠️存疑 / ❌错误（结论强度超过证据）

---

## 一、总体判断

交接文档**工程纪律良好、事实大部分准确**，但存在一个系统性问题：
**把"长度收敛"当成了"解压正确"的证据**，导致核心结论"3.2 LZSS ✅ 确认可精确解压"
不成立。图像渲染失败的真实原因不是"调色板不对"（4.1 节的主嫌疑），
而是**解压出来的字节流本身大部分就是错的**。

由此推翻的连锁结论：
- 4.1 节"观察到的数据特征（83 9D EE 每3字节重复）疑似索引色" —— 前 3 字节是真的
  （MENU.RSK 块头解压后开头确实有 `83 9D EE` 循环），但它是**局部**正确解压的产物，
  不能代表整块数据质量；
- 4.2 节把"定位调色板"列为优先级 1 —— 方向合理但**不是当前最大卡点**，
  算法错误才是。

---

## 二、逐条评审

### 2.1 一、项目基本信息 ✅

| 项 | 核对结果 |
|---|---|
| 工作副本 339 文件 | ✅ 递归计数 339（顶层 66 项；交接文档未注明"递归"） |
| 输出目录/脚本目录/git 库 | ✅ 均存在；git HEAD 已到 `977385e`（交接文档写 998f5da，略旧一提交） |
| 工作树状态 | ✅ `git status` 干净，交接文档所谓"未提交变更"实际已提交 |

### 2.2 三.1 语音提取 ✅（复核通过）

135 个 WAV 在 `extracted\SWDA_枫之舞\01_voice\`，VOC→WAV 是标准格式转换
（Creative Voice File 规范），✅ 可信。

### 2.3 三.2 LZSS"精确解压" ❌ 核心误判

**证据链（本轮新实验，脚本 219~231）**:

1. `scripts\220_swda_blocks_palette_hunt.py`：把前任解压器的**静默钳位**
   （`if start<0: start=0` / `if src>=len(out): src=len(out)-1`，见
   `207_swda_lzss2.py:36-41`、`214_swda_lzss_b.py:27-31`）改成违规计数后，
   全部 2542 块中**仅 1 块**真正无违规解压。前任声称"4 个文件全部精确"，
   实测 4 文件同样违规（MENU 184 处 / MAP 块0 121 处…）。
   → **"长度对 ≠ 内容对"**，钳位让输出恰好填满目标长度，制造了精确假象。

2. `scripts\221_swda_lzss_probe.py`：违规位置分布显示**第一处越界总在输出最前端**
   （输出@0 就引用 off=899/1590/3071），且压缩流中引用密度异常高。
   这不是"个别字节错位"，而是**引用编码的语义整个不对**。

3. `scripts\222_swda_lzss_ring.py` + `scripts\224_swda_header_scan.py`：
   扫描 480+ 组合（窗口 RING/PAD × token 打包 A/B/E/F × 控制位极性 × MSB/LSB ×
   块头长 2~6 × offset±1 × min_len 2~4），**没有任何组合能同时满足
   "输出长度=usize 且压缩流消费字节数=压缩区长"**。朴素 LZSS 假设被否定。

4. `scripts\230_swda_shared_window.py`：验证"整包共享 4096 环形窗口"假设
   （LSK 顺序解码不重置环）——48 组合全部失败（中段块 top1≈0.02 仍是噪点）。❌ 出局。

5. `scripts\231_swda_cumulative_test.py`：**正面确认了前任 3.3 节的块结构**：
   偏移表是文件内指针（4 个 LSK 全部 `delta<usize+4` 命中 46~50/50、
   `offs[0]=表尾`、`offs末=文件尾`、Σusize/文件大小 = 2.3~4.4 倍健康压缩比）。
   ✅ 块头 `[u16 usize][u8 0x01][u8 type]` + 分块独立压缩成立，
   **唯一未知项是块内压缩算法**。

**新主嫌疑（按优先级）**:
- **LZHuff / LZH8 类**（LZSS+双 Huffman 树，日本 DOS 游戏极常见）：
  QuickBMS 参考实现 `others\QuickBMS\src\compression\lzh8_dec.c`
  （头注：格式 `0x40 + 3B 长度 + 9位树 + 5位树 + 位流`，"Reverse engineered by hcs,
  public domain"，信源 http://hcs64.com/files/lzh8_cmpdec08.zip ，
  经 QuickBMS 源码转存核实，访问 2026-09-09）。
  本游戏块头第 3 字节恒为 `0x01` 而非 `0x40`，但树结构与位流形态高度待验。
- **逐 bit 位流 + 自创 token**（前任按"字节对齐控制字"假设可能整个错了方向）。
- 带预置字典的 LZ 变体（首引用指向预载窗）。

### 2.4 三.3 .LSK 结构 ✅（经 231 独立复核成立）

见上 5。补充：块类型编号实际分布 0~45 + 少量 71/72/117/160/164/192/206/250
（220 脚本统计，45 种类型），远不止交接文档列举的 5 种。

### 2.5 三.4 VGA DAC 定位 ✅ 结论成立，⚠️ 坐标系表述错误

- 用修正版脚本 `scripts\219_swda_exe_reloc_dac.py`（正确剥离 MZ 头 512B）
  capstone 反汇编复核：交接文档那张指令表**逐条真实存在**，
  但地址是**文件偏移**而非运行时地址，镜像内偏移 = 文件偏移 − 0x200。
  例：`mov si,64FCh` 真实在镜像 RVA `0x6DD5`（= 0x6FD5 − 0x200）。
- 交接文档"0x6FDC 是运行时内存地址，需要确定段基址"——本轮已解决：
  **IDA 显示 DS 段（dseg）= 线性 0x1F290 起**，前任的 `word [6DFE]` 即 IDA 的
  `word_2608E`（0x1F290+0x6DFE），`0x64FC 调色板缓冲`即 `word_2588C` 区（DS 段内 +0x64FC）。
  ✅ 交接文档的"下一步建议"（找段基址）技术上完成了一半。
- **但注意**：`0x64FC` 处**文件里的初值是指令字节**（`7F 6E C7 06…`），即
  调色板缓冲在 EXE 镜像内**没有静态初值**，是运行时填充的 →
  "在 RPG.EXE 里搜 768B 调色板"（4.2 尝试1）注定徒劳，交接文档死路清单第 4 条
  其实有结构性原因，不只是"匹配度不够"。
- IDA 还挖出一段**交接文档没提的关键代码**（线性 `0x16D46`，DS 内 `0x6AB6`）：
  一个 **6 槽 × 768B 的调色板动画/淡入淡出管理器**——
  维护 `DS:6DFC..6E0B` 的 6 组 (起始/当前/长度) 游标，把 `DS:64FC+dx` 处字节
  **逐分量插值**写回表，再由 DAC 例程 `@16DD5` 分批上传。
  另有 `@1F1C6`：`rep movsw cx=180h` 把 768B 调色板**整表拷贝**（保存/恢复现场）。
  → **确证：游戏运行时对调色板做插值动画，静态 dump 只能拿到某一帧**，
  与神雕侠侣经验（6.1 节）一致：调色板必须运行时 dump 或从资源块解析。

### 2.6 四、未解决问题与死路清单 ⚠️

- 4.1"可能原因 1/2/3"排序失效：真实主因是**解压数据本身错误**（见 2.3），
  在算法解决前讨论 pitch/子结构没有意义。
- 死路清单 6 条：第 1、2、5 条（RGB/RGB565/多宽度）**证据无效**——
  输入数据就是解压错的，判不了格式；第 3、4 条见 2.5 的结构性解释；
  第 6 条（屏幕色反推）结论仍可参考。→ 死路清单需整体降级为"在错误数据上的无效实验"。
- 交接文档 5.3 脚本表漏了磁盘上存在的 `block0_lsb/msb.bin`（位平面尝试）与
  `swda_capture_menu*.png`、`swda_debug_menu.png`（DOSBox 抓图）两条线索，本轮已补录。

### 2.7 交接文档质量评分

| 维度 | 评分 | 说明 |
|---|---|---|
| 事实准确性 | 7/10 | 文件/脚本/结构核对基本一致 |
| 结论可靠性 | **4/10** | 核心"LZSS 已确认"不成立，属钳位假象 |
| 死路清单 | 5/10 | 多数"死路"建立在错误解压之上，未真正排除 |
| 下一步建议 | 6/10 | IDA 方向对，但优先级排错了卡点 |

---

## 三、本轮新增证据（可复现）

| 脚本 | 作用 | 关键输出 |
|---|---|---|
| `219_swda_exe_reloc_dac.py` | MZ 头修正 + capstone 复核 DAC 代码 | 证实前任指令表，坐标 = 镜像偏移 |
| `220_swda_blocks_palette_hunt.py` | 全量 2542 块严格解压 | 仅 1 块无违规 → 算法未解出 |
| `221_swda_lzss_probe.py` | 违规分布探针 | 首引用即指向空窗 → 引用语义错 |
| `222_swda_lzss_ring.py` | 环形/预填窗口 96 组合 | consumed 全灭 |
| `224_swda_header_scan.py` | 块头长 × 打包 480 组合 | consumed 全灭 |
| `230_swda_shared_window.py` | 整包共享环假设 | 出局 |
| `231_swda_cumulative_test.py` | 偏移表语义判定 | **文件指针+分块压缩成立** |

## 四、外部工具情报（用户指定 E:\tools 后新增）

- `E:\tools\rpgviewer\RPGViewer.exe`（Van, v3.x）：Readme 附录 1 明确支持
  **大宇：轩辕剑系列（2代~6代以及它们的外传）** → 枫之舞在列。
  Readme 原文另声明"导入导出功能仅供个人学习研究之用"（版权提示，见 §六）。
- 它是**原生 32 位 MFC** PE（COM 目录=0，ilspycmd 拒读，非 .NET）。
- RTTI 考古（`scripts\225/226/227/228/229_rpgviewer_*.py`，RTTI 结构信源：
  openrce《Reversing Microsoft Visual C++ Part II》
  https://www.openrce.org/articles/full_view/23 ，访问 2026-09-09）确认存在类：
  `CSoftStarFile_LSK / CSoftStarFile_RSK / CSoftStarPic_lsk / CSoftStarPic_rsk /
  CSoftStarRSKPicBase`，但虚表 slot 多为构造/析构/内存管理，
  真解码器藏在基类 vftable `0x565C0C` 的虚调用后（+0x3C/+0x4C/+0x50/+0x54 槽），
  静态追全链成本高。

## 五、修正后的作战方案（接手人版）

| 优先级 | 路径 | 状态 |
|---|---|---|
| P0 | **RPGViewer 实跑导出**：DOSBox-X 环境就绪前提下直接用工具批量导出图片/调色板 → 素材提取目标即达成；导出结果反推格式再写自研解码器（工具输出 = ground truth 对照集） | 计划中 |
| P1 | IDA 全量字符串 xref 管线（`work\ida_rpg\ida_probe4.py`）：找 RPG.EXE 打开 `*.LSK/*.RSK` 的加载函数 → 反汇编解压器 → 移植 Python | 进行中 |
| P2 | DOSBox-X 调试器动态 dump：标题画面停下抓 `A000:` 帧缓冲 + DAC 寄存器表（前任 `swda_debug_menu.png` 说明有截图能力，但未做 RAM dump） | 备选 |
| P3 | LZH8/LZHuff 形态专测：按 `lzh8_dec.c` 位流格式直接套解块头（块类型 0x01 或即"LZHuff 变体"标识） | 备选 |

## 六、合规提示

RPGViewer Readme 与大宇版权提示：提取素材**仅限个人学习研究**，不得商用或再分发。
本报告与提取产物按此边界使用。

## 七、信源清单

1. DOS MZ EXE 头字段定义（e_cblp@0x02…e_lfarlc@0x18，0x3C 属 PE 保留）——
   Wikipedia "ME (assembly header)" https://en.wikipedia.org/wiki/ME_(assembly_header) ，访问 2026-09-09
2. VGA DAC 0x3C8/0x3C9 端口时序 —— OSDev Wiki
   https://wiki.osdev.org/VGA_Hardware ，访问 2026-09-09
3. LZSS 环形窗口/1-based distance —— Wikipedia "LZ77 and LZ78"
   https://en.wikipedia.org/wiki/LZ77_and_LZ78 ，访问 2026-09-09
4. LZH8 格式（9位长度树+5位距离树+MSB位流，hcs 逆向，public domain）——
   `others\QuickBMS\src\compression\lzh8_dec.c` 文件头（上游 http://hcs64.com/files/lzh8_cmpdec08.zip ），访问 2026-09-09
5. MSVC 32 位 RTTI（COL/vftable/TypeDescriptor 结构）—— openrce
   https://www.openrce.org/articles/full_view/23 ，访问 2026-09-09
6. RPGViewer 支持游戏列表 —— `E:\tools\rpgviewer\Readme.txt` 附录1（本地文件，2026-09-09 读取）
7. VOC 文件格式 —— Creative Labs VOC File Format Specification (1994, 附录 A)
   镜像 https://www.tavi.co.uk/phobos/adapt/multivoc.html （历史参考, 前任已完成, 未复核）

---
*评审人注：本文档所有"❌/⚠️"判定均可用第三节脚本一键复现。*
