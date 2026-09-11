# 机械格局引用审计

审计范围：`patterns.py` 的 35 个旧引用；已实际阅读自修 `4305-6300.json` 的三合、反吟、伏吟规则，以及象法上 `0186-0194.json`、`0195-0202.json`、`0202-0208.json` 的共享导语和前八个组合规则。象法取证使用当前有效 canonical 正文及已批准切片，不沿用旧 OCR 边界。

`rule_references.json` 将每个旧 ID 显式别名到稳定概念 ref，并逐项列出 `pattern_ids`、原书章节、可直接支撑的范围和算法边界。35 个 ref 中，10 个已绑定人工规则，25 个 `unresolved`。这不是全书引用完成率，也不表示相应检测已检查全部原文条件。本轮只将组合04–08从未绑定改为已绑定，原先5个绑定及其余引用内容保留。

## 已绑定的核心规则

| 稳定引用 | 已批准的新目标单元 |
| --- | --- |
| `lifa.three_harmony_branches` | `liuyao_zixiu_dxj.full.l4520.rule` |
| `lifa.fanyin_fuyin` | `liuyao_zixiu_dxj.full.l4784.rule`、`liuyao_zixiu_dxj.full.l4844.rule` |
| `xiangfa.combination.01` | `liuyao_xiangfa_jinjie_shang.manual.p0186_tiger_parent_accident` |
| `xiangfa.combination.02` | `liuyao_xiangfa_jinjie_shang.manual.p0188_parent_day_marriage` |
| `xiangfa.combination.03` | `liuyao_xiangfa_jinjie_shang.manual.p0191_parent_wealth_transform` |
| `xiangfa.combination.04` | `liuyao_xiangfa_jinjie_shang.manual.p0195_dragon_child_pride` |
| `xiangfa.combination.05` | `liuyao_xiangfa_jinjie_shang.manual.p0198_tiger_child_broken_pregnancy` |
| `xiangfa.combination.06` | `liuyao_xiangfa_jinjie_shang.manual.p0200_snake_child_skill` |
| `xiangfa.combination.07` | `liuyao_xiangfa_jinjie_shang.manual.p0202_dragon_official_position` |
| `xiangfa.combination.08` | `liuyao_xiangfa_jinjie_shang.manual.p0205_black_tortoise_official_private_worry` |

三合改绑完整条件规则。正文明确允许日月、动爻、变爻和暗动参加，排除静爻；又明确二动且一为中支可借日月、半局须含中支，以及缺支、空破、入墓的待时条件。这些现在有直接文字支持，不再笼统标为算法约定。完整规则已包含四支组定义，因此不再把 `l1010.rule` 支表设为必需目标。当前检测仍未纳入暗动、未严格核二动一中借日月和空破墓待时，命中只是结构候选。

反吟、伏吟分别绑定实际定义。`l4784.rule` 明载先天及后天对冲方位互化、动变地支对冲；`l4844.rule` 明载动爻变同爻。原文同时说明反吟也可最后吉、伏吟要以用神衰旺为主。因此引用可用不等于事件确定或终局凶；内外卦仅聚合已动爻仍是实现层汇总。

组合01保留五爻增强和其他六神可对应其他事情的限制，不由父母白虎动克世直接认定车祸。组合02只在已有交往或谈婚论嫁、尚未结婚而问婚的语境适用；尚未见面相亲不能套用，也不能据此确定婚期或婚姻长久。

组合03必须分财运／姻缘场景和财→父／父→财方向。当前无序六亲集合只检出互化存在，解释前须回读该位置主爻及 `transformation`；不能把父化财也解释为已有婚约。求测人与对象的性别、关系、取用和婚史归属不明确时保留未知，不能由「妻财」名称、卦图标题或该结构默认女方有婚。原文的已婚、订婚、将婚也只是条件下的可能。

组合04、07的世爻或用神限定有直接正文支持；代码使用的仍是调用方待核实的用神候选，吉凶、问事和实际对象未判定。04完整保留理想精神追求与不切实际等两面，07完整保留正职不限定公务员、也可指单位管理等，以及其他六亲／墓库／爻位分支。

组合05只检出主卦显爻白虎子孙月破；原文限定胎孕问事并写「逢破」，还包括胎爻、胎位，因此月破不是全部条件、未命中不能排除，命中也不能认定胎孕结果。组合06保留跨页的技艺与偏激空想等多种取象，正文未限世用，但任一主卦爻不自动归属卦主人格、能力或健康；投资例不成为一般规则。

组合08正文先说玄武持世，官鬼为增强条件，所以代码不必为迎合「玄鬼」标题补官鬼限制。原文首先指卦主，代问不自动转移给被问人；困难委屈、疑虑、私事等多种情境不能机械归结为犯罪、品行或精神疾病。五条都只是结构前提有可回查依据，不等于事件或人物状态已证实。

八个象法目标的 `context_spans` 已包含共享导语，组合02还保留作者对个案解释持保留意见的上下文；构建后作为 `required_contexts` 随正文读取，无需重复添加共享导语为同组目标。未把案例反馈或个案解释升级为通则。

前轮核验了3个 native 规则跨度及象法4个规则的10个正文／上下文跨度。本轮新增5条规则共12个正文／上下文跨度，其 `exact_text` 和声明 SHA256 均与有效 canonical 一致；5条的 source ID、来源PDF哈希及完整 approved review 也逐条确认。数据库尚未装入新映射或目标时，运行时仍应返回 `unavailable`。

本轮来源审计哈希：`0195-0202.json` 文件为 `c066c16211c38e0171fb2aa1a6408c019c3a72cec1ff6d9f7c2d03d34d322861`，`0202-0208.json` 文件为 `d7e4c5708da267e87d5620668b4d457c5657387cfbf87e84d5792675e15af59b`；均声明原PDF SHA256 `416fbadbc29af2d0ff7f5b4f36ade03605ec4a54e52f8c8475614b893d2400a1`。每条复用的共享导语正文哈希为 `733a2ba9d467b27947cf3b5a8f3e840b6c43836d361e23992f824cd346cb8fcd`。

| 新增组合 | 主正文跨度 SHA256（按原文顺序） |
| --- | --- |
| 04 | `1d052ddd19978b1e412b2851f413921d26a9a18055a7965dd68f19681d5c8f68` |
| 05 | `ff528ba67f7a9b994623051311a01b70340890f878997b951d5bcbbc2f4a3877` |
| 06 | `8ee99a84e24ac540d3f97b92f5623f62e37d7a0fa4af19974fae92cf6896e156`；`4245cb7d999b94642f63b17abee5d8b3421c65948696bbe321f74677809614a9` |
| 07 | `523b4cfbd18f6337ac08c1de9cbd3c5ac298d76446f75859ce559a30ec03dd4c`；`a812df14a8a2e19bc409bca34f1c219ec13ed8a3fddbccf47ccf7b03fe4b430c` |
| 08 | `c7e6fb9318a0e904f492a197d0099af8d3780199e2f92dbec543e9136f7f2e38` |

## 待绑定的原书概念

下列页数是原目录印刷页，仅供导航；没有复用旧 OCR 行号作为新正文坐标。

| 旧引用 | 对应概念／章节及印刷页 |
| --- | --- |
| `xf_shang_c02_u09`–`u12` | 玄武兄动 203；勾陈临宅 206；五爻君位 210；虎雀对立 213 |
| `xf_shang_c02_u13`–`u18` | 世应比合 216；虎马游魂 219；官伏财破 220；财子皆伏 222；世应同宫 224；婚恋进退 226 |
| `xf_shang_c03` | 长生十二宫之象 232 |
| `xf_xia_c04_s01`–`s05` | 子卯刑 2；寅巳申刑 12；丑未戌刑 27；双刑 33；自刑 51 |
| `xf_xia_c05` | 伏神之象 56 |
| `xf_xia_c07_u01`／`u02` | 上下反吟 104；方位相冲 106 |
| `xf_xia_c08`／`c09` | 进退位之象 115；隔山化爻 125 |
| `xf_xia_c10_u01`–`u04` | 生中带害 136；克中带害 145；纯相害 150；全化害 154 |

原目录标题不能当作事件结论的证据。前八个组合已有完整规则与上下文供回查，但全部 18 个组合的机械检测都没有验证完整的场景、对象、旺衰和例外，因此目前只能报告结构候选。当前三刑枚举所有主卦爻、统一作用边、进退位任取同六亲爻比较、隔山多级递归等，是另需原文支持的实现选择；详细限制逐项保存在映射里。

其余章节的只读比对没有升级为人工批准正文，也没有借其他书同主题段落替代本引用。

## 构建与查询

`store_mapping(db, root)` 将 JSON 编译进 SQLite 的 `rule_references` 表；安装运行只需数据库。`resolve(db, ref)` 接受稳定 ref 或显式 legacy alias，只有每个 target 都存在于规则表、来自声明的同一来源、标记为 `approved_manual_slices` 且 review 完整批准时，才返回 `available` 和新的 `source_rule_ids`。缺表、未映射、缺 target、自动切块、案例文本或未批准目标均明确 `unavailable`；不搜索替代正文。

下一步由人工切片审阅者定位对应正文单元、确认其确实支持所标概念后，才可填写 `target_ids` 并改为 `mapped`。可以绑定同一来源的多个规则单元，运行时要求全部通过；不得靠旧行号推导新边界。

验证：`tests/test_rule_references.py` 的 8 项测试通过，覆盖仅 SQLite 运行、legacy 别名、新规则 ID、目标集完整性、人工批准限制、缺引用、全部旧机械引用覆盖及API返回边界。本轮仅更新映射与审计，没有修改运行代码、数据库或冻结数据。
