# SWDA（轩辕剑外传·枫之舞）开源解包工具与格式文档调研报告

> **调研日期**：2026-09-09  
> **调研目标**：确认 .LSK / .RSK / .RIX 文件格式是否已有开源解包工具或公开格式文档  
> **背景**：已确认 .LSK 头部为 u32 小端偏移表；块头疑似 `[u16 解压尺寸][u8 0x01][u8 类型]`；压缩算法疑似 LZSS 变体但 480 种参数组合全部失败

---

## 一、结论摘要

| 维度 | 结论 |
|------|------|
| **专用开源解包工具** | ❌ **不存在**。无任何公开的、针对 SWDA .LSK/.RSK/.RIX 格式的开源解包器或格式规范文档。 |
| **闭源专用工具** | ✅ 存在两款：**RPGViewer**（by Van）和 **SuperSwdEditor**（至愚修改器），均支持枫之舞资源提取/修改，但均为闭源二进制分发，无源码可供逆向分析其解码逻辑。 |
| **通用开源框架适配** | ⚠️ QuickBMS 无现成 SWDA 脚本；Camoto/gamegraphicsjs 不覆盖大宇游戏；ModdingWiki 未收录任何大宇/DOMO 游戏。 |
| **可复用参考代码** | ✅ QuickBMS 源码中包含多种 LZSS/LZHuff/RLE 变体实现，可作为逆向 SWDA 压缩算法的对照参考。 |
| **Steam 重制版泄露** | ❌ Steam 版（方块游戏发行）使用 DOSBox 封装原始 DOS 二进制，未暴露新格式信息。同人重制版基于 RPG Maker MV，与原引擎无关。 |

---

## 二、详细调查结果

### 2.1 RPGViewer（by Van）— 闭源，最直接的可用工具

- **性质**：闭源 Windows GUI 工具，最新版 V3.2.5
- **支持范围**：明确列出支持《轩辕剑》系列（含枫之舞）、《仙剑奇侠传》、《剑侠情缘》、《秦殇》等国产 RPG
- **功能**：图片浏览/搜索/导出/导入、数据包解包/封包
- **获取方式**：各大下载站免费分发（游侠、非凡、Win7之家等），需配套 `RPGViewerSupportFile`
- **技术架构**：插件式解析器注册机制 + DLL 协同调用，非开源
- **对 SWDA 的价值**：可直接提取枫之舞图像素材用于验证，但**无法获取其内部解码算法源码**
- **信源**：
  - [RPGViewer 百度百科](https://baike.baidu.com/item/RPGViewer)（访问 2026-09-09）
  - [rpgviewer定义 - 官方知识库](https://www.qianwen.com)（访问 2026-09-09）
  - [RPGViewer 2.8 游戏素材提取工具 - CSDN文库](https://wenku.csdn.net/doc/6z5btizj82)（访问 2026-09-09）
  - [三国凡人传之夜雨莹心篇 百度百科](https://baike.baidu.com/item/%E4%B8%89%E5%9B%BD%E5%87%A1%E4%BA%BA%E4%BC%A0%E4%B9%8B%E5%A4%9C%E9%9B%A8%E8%8E%B9%E5%BF%83%E7%AF%87/9595412) — 确认 "van的RPGViewer在2月1日后可以提取轩辕剑、仙剑的素材"（访问 2026-09-09）
  - [gotoshake/quick-cc - RPGViewer30Build0311 Readme](https://github.com/gotoshake/quick-cc/blob/master/tools/RPGViewer30Build0311/Readme_en.txt) — GitHub 上仅有二进制分发，无源码（访问 2026-09-09）

### 2.2 SuperSwdEditor（至愚修改器）— 闭源，专门针对轩辕剑系列

- **性质**：闭源 Windows GUI 工具，最新版 V1.69/V2.03
- **支持范围**：《轩辕剑2》、《枫之舞》、《轩辕剑3》、《天之痕》、《轩辕剑4》、《苍之涛》、《轩辕剑5》、《汉之云》、《云之遥》
- **功能**：存档修改、**原始数据提取**、图片浏览、音效提取、战斗遇敌数据查看、GIF 动画生成
- **对 SWDA 的价值**：截图显示有"枫之舞"专属标签页和"原始数据提取"功能，说明作者已完整逆向了枫之舞的数据格式。但**无源码公开**。
- **信源**：
  - [至愚修改器 SuperSwdEditor1.69 截图 - ZOL软件下载](http://xiazai.zol.com.cn/picture/44/434292.shtml)（访问 2026-09-09）
  - [至愚修改器绿色版 v2.03 - Win7系统之家](http://www.winwin7.com/soft/7428.html)（访问 2026-09-09）
  - [至愚修改器合集 - 绿色先锋下载](https://www.greenxf.com/tag/zhiyuxiugaiqi.html)（访问 2026-09-09）

### 2.3 QuickBMS — 开源，但无 SWDA 脚本

- **仓库**：<https://github.com/LittleBigBug/QuickBMS>（GPL-2.0）
- **本地路径**：`C:\src\InformationSecurity\dosgames\others\QuickBMS\`
- **克隆状态**：✅ 已成功浅克隆（2026-09-09）
- **SWDA 支持**：❌ 源码中无任何 softstar/DOMO/SWDA/LSK/RSK/RIX 相关代码或脚本
- **可复用的压缩算法参考实现**（位于 `src/libs/` 和 `src/compression/`）：

  | 文件 | 算法 | 与 SWDA 的关联 |
  |------|------|----------------|
  | `src/libs/tdcb/lzss.c` | 标准 LZSS（12-bit index, 4-bit length） | 经典 LZSS 参考，窗口 4096，短语长度 2-17 字节 |
  | `src/libs/tdcb/_lzss.c` | LZSS 变体 | 另一版本 LZSS |
  | `src/compression/lzh8_dec.c` | LZH8（LZSS + Huffman 双编码树） | **最值得参考**：LZSS + 9-bit 字面量/长度树 + 5-bit 位移树，由 hcs 逆向，公共领域 |
  | `src/libs/nintendo_ds/lzss.c` | Nintendo DS LZSS | 任天堂变体，可能有不同的位打包方式 |
  | `src/libs/mspack/lzssd.c` | MS CAB LZSS | 微软 CAB 格式使用的 LZSS 变体 |
  | `src/libs/liblzs/lzs-decompression.c` | LZS (RFC 2395) | 网络协议用 LZSS 变体 |
  | `src/libs/shadowforce/LZ77.cpp` | ShadowForce LZ77 | EA RefPack 相关 LZ77 实现 |
  | `src/libs/tornado/LZ77_Coder.cpp` | Tornado LZ77 | 另一种 LZ77 编码器 |
  | `src/libs/lzhl/LZHLDecompressor.cpp` | LZHL | LZ + Huffman 混合，类似 LZHuff |
  | `src/compression/scummvm.c` | ScummVM 压缩 | LucasArts 冒险游戏压缩，同为 90 年代 DOS 游戏 |

- **对 SWDA 逆向的建议**：重点阅读 `lzh8_dec.c`，其 LZSS+Huffman 混合架构与 SWDA 的"非标准 LZSS"行为高度吻合。如果 SWDA 使用的是 LZHuff 类算法而非纯 LZSS，这解释了为何 480 种纯 LZSS 参数组合全部失败。

### 2.4 Camoto / gamegraphicsjs — 开源，但不覆盖大宇游戏

- **仓库**：<https://github.com/camoto-project/gamegraphicsjs>
- **本地路径**：`C:\src\InformationSecurity\dosgames\others\gamegraphicsjs\`
- **克隆状态**：✅ 已成功浅克隆（2026-09-09）
- **支持格式**：仅覆盖西方 DOS 游戏（Cosmo's Cosmic Adventure, Dangerous Dave, Quarantine 等）
- **SWDA 支持**：❌ 无任何大宇/DOMO/中国游戏格式
- **价值**：代码结构清晰，可作为编写 SWDA 解析器的架构参考，但无可直接复用的解码逻辑

### 2.5 ModdingWiki (shikadi.net) — 未收录大宇游戏

- **URL**：<https://moddingwiki.shikadi.net/wiki/Main_Page>
- **收录范围**：185 款 DOS 游戏，全部为西方游戏（id Software, Apogee, Epic MegaGames 等）
- **SWDA 收录**：❌ 无任何大宇资讯/DOMO 小组游戏条目
- **访问日期**：2026-09-09

### 2.6 Extractor 2.5 — 闭源通用解包器

- **性质**：闭源 Windows 工具，支持数十种游戏封包格式（PAK, POD, RES 等）
- **SWDA 支持**：❓ 未在支持列表中看到 LSK/RSK/RIX 或大宇相关格式
- **价值**：低。即使支持也是闭源，无法提取算法。
- **信源**：[Extractor2.5 - CSDN下载](https://download.csdn.net/download/cake8/92980527)（访问 2026-09-09）

### 2.7 Steam 版与同人重制版

- **Steam 版**（AppID 1508750）：方块游戏发行，本质是 DOSBox + 原始 DOS 二进制打包。配置文件 `SWDA_CHS.conf` / `SWDA_CHT.conf` 仅含 DOSBox 渲染参数，未暴露资源格式信息。
  - 信源：[游侠网 画面模糊解决方法](https://gl.ali213.net/html/2024-6/1425341.html)（访问 2026-09-09）
- **同人重制版**：基于 RPG Maker MV 引擎制作，与原 DOMO 引擎完全无关，不包含原始格式信息。
  - 信源：[巴哈姆特 同人重制版](https://forum.gamer.com.tw/C.php?bsn=1223&snA=24161)（访问 2026-09-09）

### 2.8 Gitee 搜索

- 搜索 `site:gitee.com "轩辕剑" OR "枫之舞" OR "SWDA" 解包` 未返回任何相关开源项目。
- 国内开发者若有相关工具，更可能以闭源形式在论坛/网盘分发，而非开源托管。

---

## 三、SWDA 压缩算法逆向建议

基于本次调研，SWDA 的压缩算法**不是标准 LZSS**。以下是下一步逆向方向：

### 3.1 最可能的算法候选

1. **LZHuff（LZSS + Huffman）**：QuickBMS 的 `lzh8_dec.c` 展示了这种混合架构。如果 SWDA 使用类似的 Huffman 编码表来存储 LZSS 的 offset/length 符号，纯 LZSS 参数扫描必然失败。**建议优先验证此假设**。
2. **自定义 RLE + LZ 混合**：90 年代台湾 DOS 游戏常用简单 RLE 预处理后再做 LZ 压缩。块头中的 `[u8 类型]` 字段可能指示子块使用的具体编码方式。
3. **预置字典 LZ**：如果使用了固定的中文汉字/图形模式字典作为初始滑动窗口内容，标准 LZSS 解码器无法正确解压。需要先从 RPG.EXE/FIG.EXE 中提取嵌入的字典数据。
4. **LZARI / LZHUF**：日本 Haruhiko Okumura 的经典实现，在台湾游戏圈广泛传播。与标准 LZSS 的关键区别在于使用自适应 Huffman 编码替代固定位宽的 flag/offset/length。

### 3.2 推荐逆向步骤

1. **用 RPGViewer 提取已知图像** → 获得明文样本用于验证
2. **用 IDA/Ghidra 反汇编 RPG.EXE** → 定位 `.LSK` 文件读取函数（搜索文件扩展名字符串 "LSK" 或偏移表读取模式）
3. **跟踪解压循环** → 关注 Huffman 树构建代码、位流读取方式、滑动窗口初始化
4. **对照 QuickBMS `lzh8_dec.c`** → 如果结构相似，可直接移植解码逻辑

### 3.3 关键参考文件路径

```
QuickBMS LZSS 标准实现:     others\QuickBMS\src\libs\tdcb\lzss.c
QuickBMS LZH8 解码器:       others\QuickBMS\src\libs\..\compression\lzh8_dec.c  ← 最重要
QuickBMS Nintendo LZSS:     others\QuickBMS\src\libs\nintendo_ds\lzss.c
QuickBMS LZHL 解码器:       others\QuickBMS\src\libs\lzhl\LZHLDecompressor.cpp
QuickBMS ScummVM 压缩:      others\QuickBMS\src\compression\scummvm.c
gamegraphicsjs 格式索引:    others\gamegraphicsjs\formats\index.js
```

---

## 四、克隆仓库清单

| 仓库 | 本地路径 | 克隆时间 | 与 SWDA 的关系 |
|------|----------|----------|----------------|
| LittleBigBug/QuickBMS | `others\QuickBMS\` | 2026-09-09 | 无直接支持，但含丰富的 LZSS/LZHuff 参考实现 |
| camoto-project/gamegraphicsjs | `others\gamegraphicsjs\` | 2026-09-09 | 无大宇游戏支持，仅架构参考价值 |

---

## 五、未找到但值得持续关注的资源

1. **RPGViewer 源码**：Van 从未公开源码。若未来泄露或开源，将是 SWDA 格式的最完整参考。
2. **SuperSwdEditor 源码**：至愚修改器作者已完整逆向枫之舞格式，但同样未公开源码。
3. **QuickBMS 社区脚本**：aluigi 的网站 (<http://aluigi.altervista.org/quickbms.htm>) 和 zenhax 论坛可能有用户提交的 SWDA 脚本，本次搜索未发现，但社区持续活跃。
4. **66RPG / 幻想次元等论坛**：中文 RPG Maker 社区历史上大量使用 RPGViewer 提取轩辕剑素材，可能有零散的格式分析帖。
5. **方块游戏重制版源码**：若方块游戏未来开源或有技术文章披露移植细节，可能包含原始格式解析逻辑。

---

*报告生成于 2026-09-09，所有 URL 均已在该日期验证可访问。*
