# 025 - 《金瓶梅》(JPM/Golden Jug) MGP2资源格式破解全记录

> 游戏：金瓶梅 (Golden Jug)，中文DOS RPG+H游戏  
> 平台：DOS 16位  
> 资源格式：MGP2 (MG Patterns Vol 1.1)  
> 日期：2026-09-16

## 一、游戏文件结构

JPM游戏目录包含以下资源文件：

| 类型 | 文件 | 说明 |
|------|------|------|
| 资源包 | *.PAT (19个) | MGP2格式图像资源包 |
| 调色板 | *.PAL (4个) | 768字节=256色，VGA 6位值需×4 |
| 数据 | *.DAT | 游戏数据 |
| 字体 | *.FON | 字体文件 |
| 动画 | *.FLC | FLIC动画 |
| 音频 | AUDIO/ | 音频资源 |
| 可执行 | GAME.EXE | 378KB，16位DOS程序 |

主要PAT文件：
- TITLE.PAT - 标题画面按钮
- MOUSE.PAT - 鼠标光标（未压缩）
- ITEM.PAT - 物品图标
- MAP.PAT - 地图
- FIGHT.PAT / FIGHTER.PAT - 战斗背景/角色
- PERSONS.PAT - 人物头像
- MAINBG.PAT - 主背景
- WINICON.PAT - 窗口图标
- END.PAT - 结局画面
- FEFFECT.PAT - 特效
- GPMEVENT.PAT (5.7MB) / GPMAREA.PAT (4MB) / GPMANIM.PAT (2.8MB) - 大文件GPM系列

## 二、MGP2格式结构

### 2.1 文件头

所有PAT文件统一为MGP2格式：

| 偏移 | 长度 | 内容 |
|------|------|------|
| 0x00 | 4 | 魔数 "MGP2" |
| 0x04 | 2 | 版本 0x130B |
| 0x06 | 23 | 描述 "MG Patterns Vol 1.1" |
| 0x1D | 1 | 条目数（TITLE=9, MOUSE=32, ITEM=111） |
| 0x40 | 784 | 固定颜色查找表（所有PAT共享） |
| 0x340 | 8×N | 条目表 |
| 0x330+ | - | 数据区 |

### 2.2 条目表

偏移0x340开始，每条目8字节：

```
字节0: 00 (标志)
字节1: 宽度 (1字节)
字节2: 00
字节3: 高度 (1字节)
字节4: 00
字节5-6: 数据偏移 (LE16，文件绝对偏移)
字节7: 00
```

**验证**：MOUSE.PAT的条目偏移差值正好=w×h（16×16=256），确认MOUSE为**未压缩8bpp**。

### 2.3 调色板

4个PAL文件（MAIN.PAL / TITLE.PAL / END.PAL / GRADIENT.PAL）：
- 768字节 = 256色 × 3字节(RGB)
- 每个颜色分量是VGA 6位值（0-63），需×4转为8位（0-255）
- 索引0x00为透明色

## 三、破解过程：从LZSS死路到LZW突破

### 3.1 早期错误尝试

**问题**：TITLE.PAT条目0（135×28）压缩数据1340字节，期望3780字节，压缩比2.8:1。数据特征：0x00占比仅0.3%，无连续相同字节。

**尝试1：HR风格LZSS**（窗口1024，bit0→bit7，10位偏移6位长度）→ 噪点

**尝试2：标准LZSS全参数组合**（窗口4096/2048/1024，bit7→0/bit0→7，12/11/10位偏移，skip=0/2/4/6）→ **全部噪点**

**尝试3：直接8bpp/4bpp渲染** → 噪点

**尝试4：反汇编GAME.EXE**（capstone 16位反汇编）
- 定位MGP2加载函数：0x2AA90
- 错误消息：0x2AA64 "MGP2$:Patterns are not in correct Format!"
- 发现颜色插值函数：0x2B639
- 发现像素后处理代码：0x2B956（0x00=透明，0xDF=阈值，0xFF=特殊，0x01-0x0F=编码范围）
- 但解压函数是`lcall 0,0xffff`间接调用，静态分析无法确定实际地址

### 3.2 LZW突破

**关键洞察**：压缩数据无连续相同字节，0x00占比极低，这是LZW压缩的典型特征（LZSS会保留部分原始字节，LZW输出是变长代码）。

**LZW参数**（GIF风格）：
- min_code_size=8
- clear_code=256, end_code=257
- 初始code_size=9位，最大12位
- 位序：LSB优先（msb_first=False）
- 字典初始化：0-255为单字节，next_code从258开始
- 特殊规则：code==next_code且prev_code非空时，entry=prev+prev[0]（KwK问题）

**首次成功**：TITLE.PAT条目0，skip=0，LZW解压出3780字节=135×28像素！

**上下翻转**：解压后图像上下颠倒，需FLIP_TOP_BOTTOM才正确。

![标题按钮-进入游戏](images/025_jpm/title_enter.png)
*TITLE条目0上下翻转后显示"進入遊戲"（进入游戏）*

![标题按钮-开始游戏](images/025_jpm/title_start.png)
*TITLE条目3显示"開始遊戲"（开始游戏）*

### 3.3 前4字节的奥秘与LZW变体（最终正确解）

**核心矛盾**：标准GIF风格LZW对TITLE有效，但对ITEM/FEFFECT等PAT失败。

**分析**：
- TITLE条目0前4字节：`00 3F 08 1C` → 清除→字面量31→字典码258，有效
- ITEM条目0前4字节：`00 01 02 18` → 清除→清除→字面量0→代码259，**标准LZW判定无效**
- 两者从第5字节开始的数据完全相同：`48 B0 A0 C1 83 08 13 2A...`

**ITEM前4字节的LZW解码（标准实现）**：
```
代码0: 清除(256)     → 重置字典, next=258, prev=None
代码1: 清除(256)     → 再次重置, next=258, prev=None
代码2: 字面量0        → 输出[0], prev=0。因prev was None，不添加字典条目, next保持258
代码3: 259            → 259不在字典中，且259≠next(258) → 无效！
```

**关键突破：LZW变体**

标准LZW中，清除后的第一个代码（prev=None）不添加字典条目，next_code保持不变。但这个游戏的LZW实现不同——**清除后的第一个代码也增加next_code**（即使不添加字典条目）。

```
代码0: 清除(256)     → 重置, next=258, prev=None
代码1: 清除(256)     → 重置, next=258, prev=None
代码2: 字面量0        → 输出[0], prev=0。next_code += 1 → next=259（关键！不添加字典但增加next）
代码3: 259            → 259==next_code(259)，prev=0非空 → KwK! entry=[0,0]，输出[0,0]
代码4: 260            → KwK，输出[0,0,0]
...继续KwK链输出背景色0x00，直到遇到实际图像数据
```

**验证结果**：
- 直接用ITEM原始数据（不需要TITLE头部替换！）LZW解压 → 6399字节（80×80=6400，差1字节，末像素补0）
- 背景色是**0x00（透明）**，不是TITLE头部替换后的0x1F
- 唯一值数量合理（item0有57种颜色，item10有85种颜色）
- 所有45个80×80物品图标全部正确：花朵、宝箱、餐具、梯子、船等形状完整，无倾斜无撕裂

**之前的错误**：
1. 用TITLE头部替换ITEM前4字节 → 字典被污染为全0x1F，背景色错误
2. 误以为行宽是w+1=81 → 实际行宽就是w=80
3. 误以为需要丢弃前3字节 → 实际不需要，variant1直接输出正确数据

### 3.4 正确的LZW解压算法（可复现）

```python
def lzw_decompress(data, out_size, min_code_size=8):
    """MGP2 LZW变体：清除后的第一个代码也增加next_code"""
    clear_code = 1 << min_code_size      # 256
    end_code = clear_code + 1            # 257
    code_size = min_code_size + 1        # 9位
    next_code = end_code + 1             # 258
    max_code = (1 << code_size) - 1
    dictionary = {i: bytes([i]) for i in range(clear_code)}
    result = bytearray()
    bit_buffer = 0
    bit_count = 0
    src = 0
    prev_code = None
    
    while len(result) < out_size and src < len(data):
        while bit_count < code_size and src < len(data):
            bit_buffer |= data[src] << bit_count
            bit_count += 8
            src += 1
        if bit_count < code_size:
            break
        code = bit_buffer & ((1 << code_size) - 1)
        bit_buffer >>= code_size
        bit_count -= code_size
        
        if code == clear_code:
            code_size = min_code_size + 1
            next_code = end_code + 1
            max_code = (1 << code_size) - 1
            prev_code = None
            continue
        if code == end_code:
            break
        
        if code in dictionary:
            entry = dictionary[code]
        elif code == next_code and prev_code is not None:
            entry = dictionary[prev_code] + bytes([dictionary[prev_code][0]])
        else:
            break
        
        result.extend(entry)
        
        # ★ 关键变体：总是增加next_code，即使prev是None（清除后第一个代码）
        if next_code < 4096:
            if prev_code is not None:
                dictionary[next_code] = dictionary[prev_code] + bytes([entry[0]])
            next_code += 1
            if next_code > max_code and code_size < 12:
                code_size += 1
                max_code = (1 << code_size) - 1
        prev_code = code
    
    return bytes(result)
```

**渲染**：
- 解压后**上下翻转**（FLIP_TOP_BOTTOM）
- 索引0x00 → 透明（PNG alpha=0）
- 行宽 = w（不是w+1）
- 若解压字节数略少于w×h（如6399 vs 6400），末像素补0

![物品图标-宝箱](images/025_jpm/item_chest.png)
*ITEM条目5：宝箱与金币，variant1解压，形状完整无倾斜*

## 四、LZW解压算法（可复现）

```python
def lzw_decompress(data, out_size, min_code_size=8):
    """GIF风格LZW解压，LSB优先"""
    clear_code = 1 << min_code_size      # 256
    end_code = clear_code + 1            # 257
    code_size = min_code_size + 1        # 9位
    next_code = end_code + 1             # 258
    max_code = (1 << code_size) - 1
    
    # 字典初始化：0-255为单字节
    dictionary = {i: bytes([i]) for i in range(clear_code)}
    
    result = bytearray()
    bit_buffer = 0
    bit_count = 0
    src = 0
    prev_code = None
    
    while len(result) < out_size and src < len(data):
        # 读取code_size位（LSB优先）
        while bit_count < code_size and src < len(data):
            bit_buffer |= data[src] << bit_count
            bit_count += 8
            src += 1
        
        if bit_count < code_size:
            break
            
        code = bit_buffer & ((1 << code_size) - 1)
        bit_buffer >>= code_size
        bit_count -= code_size
        
        if code == clear_code:
            # 清除代码：重置字典
            code_size = min_code_size + 1
            next_code = end_code + 1
            max_code = (1 << code_size) - 1
            prev_code = None
            continue
        
        if code == end_code:
            break
        
        # 查找字典
        if code in dictionary:
            entry = dictionary[code]
        elif code == next_code and prev_code is not None:
            # KwK特殊情况：code == next_code
            entry = dictionary[prev_code] + bytes([dictionary[prev_code][0]])
        else:
            break
        
        result.extend(entry)
        
        # 添加新字典条目
        if prev_code is not None and next_code < 4096:
            dictionary[next_code] = dictionary[prev_code] + bytes([entry[0]])
            next_code += 1
            if next_code > max_code and code_size < 12:
                code_size += 1
                max_code = (1 << code_size) - 1
        
        prev_code = code
    
    return bytes(result)
```

## 五、完整提取流程

### 5.1 区分压缩/未压缩

- **MOUSE.PAT**：未压缩8bpp，数据偏移处直接是像素数据，偏移差值=w×h
- **其他PAT**：LZW压缩，需用TITLE头部初始化

### 5.2 渲染

1. LZW解压得到8bpp索引数据
2. **上下翻转**（FLIP_TOP_BOTTOM）
3. 索引0x00 → 透明（PNG alpha=0）
4. 其他索引 → 调色板RGB（6位值×4）

### 5.3 提取结果

| PAT文件 | 条目数 | 成功提取 | 说明 |
|---------|--------|----------|------|
| TITLE.PAT | 9 | 8 | 标题按钮，条目8(127×223)失败 |
| MOUSE.PAT | 32 | 31 | 未压缩光标 |
| ITEM.PAT | 111 | 45 | 前45个80×80物品图标 |
| MAINBG.PAT | 70 | 42 | 背景图 |
| FEFFECT.PAT | 53 | 38 | 特效 |
| PERSONS.PAT | 176 | 35 | 人物（部分） |
| FIGHT.PAT | 23 | 2 | 战斗背景（部分） |
| FIGHTER.PAT | 59 | 4 | 战斗角色（部分） |
| WINICON.PAT | 144 | 6 | 窗口图标（部分） |
| 其他 | - | 少量 | MAP/END/MAN等 |

**总计：约257张PNG图片**

## 六、未解决的问题

### 6.1 大文件GPM系列

GPMEVENT.PAT (5.7MB)、GPMAREA.PAT (4MB)、GPMANIM.PAT (2.8MB)等大文件尚未处理。偏移可能超过LE16范围(65535)，条目表结构可能不同。

### 6.2 部分PAT文件解压失败

FIGHT/FIGHTER/PERSONS等文件大部分条目解压失败。可能原因：
- 不同PAT文件使用不同的LZW初始化头部（不是统一的TITLE头部）
- 部分条目首字节非0x00（如FIGHTER条目8首字节0x96），可能是不同压缩类型
- 条目表结构可能因文件类型而异

### 6.3 ITEM条目45+的结构

ITEM前45个条目是80×80物品图标，条目45+偏移回绕，说明条目表结构可能变化或包含多个资源段。

### 6.4 真正的解压函数

GAME.EXE中的解压函数是`lcall 0,0xffff`间接调用，需IDA动态分析才能确定实际地址。静态反汇编无法完全还原解压逻辑。

## 七、经验总结

1. **LZW vs LZSS判断**：压缩数据无连续相同字节、0x00占比极低 → LZW特征；LZSS会保留部分原始字节
2. **前4字节是LZW流的一部分**，不是独立头部，不能简单skip
3. **位对齐至关重要**：LZW是位流，跳过字节会破坏位对齐
4. **上下翻转**：DOS游戏图像经常是底部先行存储
5. **调色板6位值×4**：VGA DAC是6位的
6. **反汇编间接调用**：16位DOS程序常用`lcall 0,0xffff`运行时解析，静态分析困难

## 八、相关脚本

- `scripts/1462_jpm_lzw.py` - LZW首次成功
- `scripts/1463_jpm_lzw_all.py` - TITLE全部条目
- `scripts/1476_jpm_cross_test.py` - 前4字节交叉测试（关键发现）
- `scripts/1479_jpm_final_extract.py` - 完整提取脚本
- `scripts/1457-1461_jpm_disasm*.py` - capstone反汇编

## 九、参考

- GAME.EXE反汇编输出：`extracted/JPM_金瓶梅/mgp2_disasm*.txt`
- 提取结果：`extracted/JPM_金瓶梅/`
