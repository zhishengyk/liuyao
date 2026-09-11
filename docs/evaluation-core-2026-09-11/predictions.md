# 六事件核心规则应用盲测：冻结预测

服务版本：`0.7.0.dev0`。本次只使用获准输入和调用桥、自己创建的 requests 与对应 records。未读取案例、作者原断或结果，未联网，未用全局插件，未委派。盘面事实、书中规则与当前推断分列。置信度是解释者的定性判断，不是工具概率。

实际 MCP 工具调用 75 次，成功 75、失败 0：build_chart 15、search_knowledge 37、get_source 23。另有初始化 7 次，不计工具调用。全部检索显式 kind=rule、retrieval_mode=bm25；全部原文 corrected、context_lines=0。

| 编号 | 主预测 | 弃断 |
| --- | --- | --- |
| C01 | 主断不看好长期稳定相守，偏向以后关系难以维持；短期仍有谈婚、订婚或成婚的机会，不能将婚事推进等同于长久幸福。 | 否 |
| C02 | 倾向官司难赢，难取得自己所期待的胜诉结果。 | 否 |
| C03 | 当前条件下难以顺利卖出，近期成交偏难；何时能够成交没有足够依据，明确弃断具体售出时间。 | 具体成交应期弃断 |
| C04 | 倾向侄子能够保住性命，并有苏醒、逐渐恢复的希望；不主断死亡。 | 否 |
| C05 | 以租店经营求财为问意，倾向这处店铺可以经营并有获利机会；过程有压力和阻滞，不能断轻松顺遂。 | 否 |
| C06 | 倾向去这所学校对学习和成绩有一定帮助，但不能保证立即或大幅提高。 | 否 |

## C01 · 占问事宜：测与男友将来发展如何

**主断不看好长期稳定相守，偏向以后关系难以维持；短期仍有谈婚、订婚或成婚的机会，不能将婚事推进等同于长久幸福。**

把握：中低。应期：null。弃断：否。

盘面事实：未月，丙寅日；离为火 → 火山旅；世6应3；动爻[1]；旬空戌、亥。本变卦均与输入一致。
年、时、公历日期继续保持未知，不补造。

| 位 | 六神 | 本卦六亲地支 | 世应 | 动变 | 伏神 |
| --- | --- | --- | --- | --- | --- |
| 6 | 青龙 | 兄弟巳火 | 世 | 静 | — |
| 5 | 玄武 | 子孙未土 | — | 静 | — |
| 4 | 白虎 | 妻财酉金 | — | 静 | — |
| 3 | 螣蛇 | 官鬼亥水 | 应 | 静 | — |
| 2 | 勾陈 | 子孙丑土 | — | 静 | — |
| 1 | 朱雀 | 父母卯木 | — | 子孙辰土 | — |

取用：

- 男友与长期关系的主用神：primary 层第3爻 官鬼亥。女性问现有男友，取唯一官鬼，恰居应位；不从空亡反推取用。 依据：`liuyao_zixiu_dxj.full.l2140.rule`、`liuyao_zixiu_dxj.full.l2260.rule`、`liuyao_zixiu_dxj.full.l2212.rule`。
- 求测者自身：primary 层第6爻 兄弟巳。世爻定位自己，辅助判断双方关系。 依据：`liuyao_zixiu_dxj.full.l2212.rule`。
- 婚事推进的辅助象：primary 层第1爻 父母卯。只作交往未婚情境的婚事指标，不替代主用神。 依据：`liuyao_xiangfa_jinjie_shang.manual.p0188_parent_day_marriage`。

理法依据与当前推断：

- 条件：须核日月五行、动静和空爻生扶；静爻逢合在不同原文中有合起、合绊之别。 当前应用：官亥水受未月土克又旬空；寅日与亥合，五行却是亥水生寅木，不能误写成日生官。古法合起是有利反证，日合静爻合绊的另一解释也不直接解决月克与空。主用神不扎实，长期持续性偏弱。 依据：`liuyao_zixiu_dxj.full.l3072.rule`、`liuyao_zixiu_dxj.full.l3188.rule`、`liuyao_zixiu_dxj.full.l3536.rule`、`zengshan_buyi.manual.L02842C0000.rule`、`liuyao_lifa_jinjie.manual.p0143_day_combine_moving`。
- 条件：得日扶的动爻可生相关爻；变爻只回作用本位。 当前应用：父卯得寅日比扶，动生世巳，卯化辰无回头克，有助关系推进。辰土虽为子孙，不能越位克三爻亥官而直接断分手。 依据：`liuyao_zixiu_dxj.full.l3072.rule`、`liuyao_zixiu_dxj.full.l3188.rule`、`liuyao_zixiu_dxj.full.l2708.rule`、`zengshan_buyi.manual.L02382C0000.rule`。
- 条件：六冲变六合径断吉是古文特殊主张；取用总则和婚事象法又要求长期稳固看用神。 当前应用：离六冲变旅六合是和合反证，不能遗漏；不把这一特殊古说扩大成一律不看用神。短期推进与长期稳定分开，最终对长久相守取偏不利，降低把握。 依据：`zengshan_buyi.manual.L02922C0000.rule`、`liuyao_zixiu_dxj.full.l2700.rule`、`liuyao_xiangfa_jinjie_shang.manual.p0188_parent_day_marriage`。

象法条件与当前推断：

- 条件：父母临日、合日或同五行；须已交往或谈婚论嫁且未婚，尚未见面的相亲不适用；婚后稳固仍看用神。必读导语要求结合具体事项。 当前应用：已知正在与男友交往，父卯与寅日同木，满足同五行及交往前提。以尚未结婚为条件，推婚事有推进机会；不把已订婚、已婚写成观测事实，不指定婚期。 依据：`liuyao_xiangfa_jinjie_shang.manual.p0188_parent_day_marriage`。

额外细节预测：

- 【预测，非观测】若双方尚未结婚，短期较可能谈及或推动婚事。 把握：中低。

不确定性：

- 年、时及公历日期缺失，保持未知，不推算绝对婚期。
- 未确认双方婚姻登记状态，婚事辅助象采用尚未结婚的条件。
- 六冲变六合、父动生世支持和合；官受月克旬空削弱长久关系，反向证据并存。
- 日合静爻合起与合绊的书际差异未被静默合并。

本例证据 ID：`liuyao_zixiu_dxj.full.l2140.rule`、`liuyao_zixiu_dxj.full.l2260.rule`、`liuyao_zixiu_dxj.full.l2212.rule`、`liuyao_xiangfa_jinjie_shang.manual.p0188_parent_day_marriage`、`liuyao_zixiu_dxj.full.l3072.rule`、`liuyao_zixiu_dxj.full.l3188.rule`、`liuyao_zixiu_dxj.full.l3536.rule`、`zengshan_buyi.manual.L02842C0000.rule`、`liuyao_lifa_jinjie.manual.p0143_day_combine_moving`、`liuyao_zixiu_dxj.full.l2708.rule`、`zengshan_buyi.manual.L02382C0000.rule`、`zengshan_buyi.manual.L02922C0000.rule`、`liuyao_zixiu_dxj.full.l2700.rule`。

排盘记录：predictor-astra-01-charts #1；predictor-astra-05-application #6。

## C02 · 占问事宜：官司能赢吗

**倾向官司难赢，难取得自己所期待的胜诉结果。**

把握：中低。应期：null。弃断：否。

盘面事实：亥月，丁未日；地水师 → 泽风大过；世3应6；动爻[3, 4, 5]；旬空寅、卯。本变卦均与输入一致。

| 位 | 六神 | 本卦六亲地支 | 世应 | 动变 | 伏神 |
| --- | --- | --- | --- | --- | --- |
| 6 | 青龙 | 父母酉金 | 应 | 静 | — |
| 5 | 玄武 | 兄弟亥水 | — | 父母酉金 | — |
| 4 | 白虎 | 官鬼丑土 | — | 兄弟亥水 | — |
| 3 | 螣蛇 | 妻财午火 | 世 | 父母酉金 | — |
| 2 | 勾陈 | 官鬼辰土 | — | 静 | — |
| 1 | 朱雀 | 子孙寅木 | — | 静 | — |

取用：

- 我方胜负的主用神：primary 层第3爻 妻财午。胜负看世爻所代表的我方；官鬼可表示官府诉讼，不把官鬼旺直接等同我方赢。 依据：`liuyao_zixiu_dxj.full.l2248.rule`、`liuyao_zixiu_dxj.full.l2212.rule`。
- 诉讼相对方：primary 层第6爻 父母酉。应爻作对方，比较受扶和生克。 依据：`liuyao_zixiu_dxj.full.l2212.rule`。

理法依据与当前推断：

- 条件：月克与日合分别判断；动逢合可绊住，后逢冲开仍可应吉凶。 当前应用：世午火受亥月水克，未日合午却不是生火。世动日合，主动争取亦有牵绊，不能以合担保胜诉。 依据：`liuyao_zixiu_dxj.full.l3072.rule`、`liuyao_zixiu_dxj.full.l3188.rule`、`liuyao_lifa_jinjie.manual.p0143_day_combine_moving`、`zengshan_buyi.manual.L05806C0000.rule`。
- 条件：旺动忌神化回头生有力，须查制服与元神救应；变爻不越位。 当前应用：五爻亥兄临月发动化酉父回头生，直接克世午。酉变爻只回生本位亥水。寅子虽月合有气，仍静而旬空，不能当已成立的元忌双动。 依据：`zengshan_buyi.manual.L02382C0000.rule`、`liuyao_zixiu_dxj.full.l2708.rule`、`zengshan_buyi.manual.L02102C0000.rule`。
- 条件：日冲明动爻不是暗动，也不自动冲散；应比较相关动爻作用。 当前应用：丑官已明动，未日冲中同类，不排除其效力。它动克亥兄是救应反证，同时受世午所生并生应酉。世受月克和旺兄回头生克的压力更直接，暂判难赢；不将丑官动认定为法院必帮某一方。 依据：`liuyao_zixiu_dxj.full.l3188.rule`、`liuyao_zixiu_dxj.full.l4308.rule`、`zengshan_pingshi_dxj-l4206-day-moving-dispersal`、`liuyao_zixiu_dxj.full.l2248.rule`。

象法条件与当前推断：

- 条件：父财互化分财运交易和婚恋场景；六神单一类象须结合问事。 当前应用：世财午化父酉有结构，但未给交易或婚恋纠纷背景，不能据此推费用、婚史或败诉。螣蛇难缠类象至多与已知诉讼相容，不独立决定胜负。 依据：`liuyao_xiangfa_jinjie_shang.manual.p0191_parent_wealth_transform`、`liuyao_zixiu_dxj.full.l2200.rule`。

额外细节预测：

无。

不确定性：

- 未给原告被告、争点、诉求与审级，不预测判赔、刑罚或法官态度。
- 丑土动克亥兄支持我方，故不作高把握必败断语。
- 没有足以直接套用的本案诉讼专项条文，胜负是世应生克通则的当前解释。
- 玄武兄动等不可用象法引用未作为原文证据。

本例证据 ID：`liuyao_zixiu_dxj.full.l2248.rule`、`liuyao_zixiu_dxj.full.l2212.rule`、`liuyao_zixiu_dxj.full.l3072.rule`、`liuyao_zixiu_dxj.full.l3188.rule`、`liuyao_lifa_jinjie.manual.p0143_day_combine_moving`、`zengshan_buyi.manual.L05806C0000.rule`、`zengshan_buyi.manual.L02382C0000.rule`、`liuyao_zixiu_dxj.full.l2708.rule`、`zengshan_buyi.manual.L02102C0000.rule`、`liuyao_zixiu_dxj.full.l4308.rule`、`zengshan_pingshi_dxj-l4206-day-moving-dispersal`、`liuyao_xiangfa_jinjie_shang.manual.p0191_parent_wealth_transform`、`liuyao_zixiu_dxj.full.l2200.rule`。

排盘记录：predictor-astra-01-charts #2；predictor-astra-05-application #7。

## C03 · 占问事宜：房子何时卖出去

**当前条件下难以顺利卖出，近期成交偏难；何时能够成交没有足够依据，明确弃断具体售出时间。**

把握：方向中低；应期不足。应期：null。弃断：具体成交应期。

盘面事实：寅月，丙申日；地风升 → 离为火；世4应1；动爻[1, 2, 4, 6]；旬空辰、巳。本变卦均与输入一致。

| 位 | 六神 | 本卦六亲地支 | 世应 | 动变 | 伏神 |
| --- | --- | --- | --- | --- | --- |
| 6 | 青龙 | 官鬼酉金 | — | 子孙巳火 | — |
| 5 | 玄武 | 父母亥水 | — | 静 | — |
| 4 | 白虎 | 妻财丑土 | 世 | 官鬼酉金 | 子孙午火 |
| 3 | 螣蛇 | 官鬼酉金 | — | 静 | — |
| 2 | 勾陈 | 父母亥水 | — | 妻财丑土 | 兄弟寅木 |
| 1 | 朱雀 | 妻财丑土 | 应 | 兄弟卯木 | — |

取用：

- 出售交易及到手款项的主用神：primary 层第4爻 妻财丑。买卖成败取财；两丑财均动，四爻持世对应卖方所得，初爻应财另看买方。 依据：`liuyao_zixiu_dxj.full.l2260.rule`、`liuyao_zixiu_dxj.full.l2212.rule`。
- 房屋与出售手续：primary 层第2爻 父母亥。两父同支，二动五静，按两现择动取二爻。 依据：`liuyao_zixiu_dxj.full.l2136.rule`、`zengshan_pingshi_dxj-l2198-parents-selection`。
- 买方状态：primary 层第1爻 妻财丑。初爻居应位，不与持世财混为一爻。 依据：`liuyao_zixiu_dxj.full.l2212.rule`。

理法依据与当前推断：

- 条件：财主买卖，父母辅助房屋；须区分本位动变和他爻。 当前应用：世财丑受寅月克，申日不直接生土；应财丑动化卯回头克。父亥虽月合日生，却化丑回头克。卖方财弱，买方与手续有阻，不宜断快速顺利成交。 依据：`liuyao_zixiu_dxj.full.l3072.rule`、`liuyao_zixiu_dxj.full.l3188.rule`、`zengshan_buyi.manual.L02382C0000.rule`。
- 条件：巳酉丑成局须核动变、空破填实及合局作用，候选不等于成立。 当前应用：四、上爻动变形成巳酉丑支组，但所化巳火旬空。即使后来填实，仍须判断金局生父、泄财与其他动爻的综合影响，不看到巳字就定巳月必售出。 依据：`liuyao_zixiu_dxj.full.l4520.rule`、`zengshan_buyi.manual.L02382C0000.rule`。
- 条件：应期先定吉凶条件并分远近，结合空合和克神受制，不以多个候选日期代替预测。 当前应用：现有规则不能排除互相冲突的应期，也无预期出售期限。保留当前成交受阻方向，明确不给月份或日期。 依据：`zengshan_buyi.manual.L03722C0000.rule`、`liuyao_zixiu_dxj.full.l5320.rule`。

象法条件与当前推断：

- 条件：交易财运场景，父化财或财化父，可指价格难谈、预期难达或本金较高；导语要求按具体事情选分支。 当前应用：卖房且二爻父亥动化财丑，情境与变向成立。推议价或预期难协调；不用婚史分支，不断房价、折让比例或资金数额。 依据：`liuyao_xiangfa_jinjie_shang.manual.p0191_parent_wealth_transform`。

额外细节预测：

- 【预测，非观测】出售过程较可能遇到议价困难，或报价、成交条件难达到目前预期。 把握：中。

不确定性：

- 原问重在何时卖出，缺足够可审核应期依据，故将本例标记为具体应期弃断。
- 当前不顺不扩大为永久卖不出去。
- 巳酉丑支组存在而巳空，填实时点与作用不能直接等同成交。
- 未给售价、挂牌时长、买家或合同，不补造金额与买家身份。

本例证据 ID：`liuyao_zixiu_dxj.full.l2260.rule`、`liuyao_zixiu_dxj.full.l2212.rule`、`liuyao_zixiu_dxj.full.l2136.rule`、`zengshan_pingshi_dxj-l2198-parents-selection`、`liuyao_zixiu_dxj.full.l3072.rule`、`liuyao_zixiu_dxj.full.l3188.rule`、`zengshan_buyi.manual.L02382C0000.rule`、`liuyao_zixiu_dxj.full.l4520.rule`、`zengshan_buyi.manual.L03722C0000.rule`、`liuyao_zixiu_dxj.full.l5320.rule`、`liuyao_xiangfa_jinjie_shang.manual.p0191_parent_wealth_transform`。

排盘记录：predictor-astra-01-charts #3；predictor-astra-05-application #8；predictor-astra-07-source-audit #21。

## C04 · 占问事宜：测侄子车祸昏迷吉凶

**倾向侄子能够保住性命，并有苏醒、逐渐恢复的希望；不主断死亡。**

把握：中。应期：null。弃断：否。

盘面事实：酉月，丙辰日；天泽履 → 天水讼；世5应2；动爻[1]；旬空子、丑。本变卦均与输入一致。

| 位 | 六神 | 本卦六亲地支 | 世应 | 动变 | 伏神 |
| --- | --- | --- | --- | --- | --- |
| 6 | 青龙 | 兄弟戌土 | — | 静 | — |
| 5 | 玄武 | 子孙申金 | 世 | 静 | 妻财子水 |
| 4 | 白虎 | 父母午火 | — | 静 | — |
| 3 | 螣蛇 | 兄弟丑土 | — | 静 | — |
| 2 | 勾陈 | 官鬼卯木 | 应 | 静 | — |
| 1 | 朱雀 | 父母巳火 | — | 官鬼寅木 | — |

取用：

- 侄子安危的主用神：primary 层第5爻 子孙申。侄子明确属于晚辈，取唯一子孙申；其持世仍指侄子，不偷换为叔叔身体。 依据：`zengshan_buyi.manual.L02014.rule`、`liuyao_zixiu_dxj.full.l2152.rule`。
- 生子孙之元神候选：primary 层第6爻 兄弟戌。土生申金，静戌日冲且得动火生助，须审核暗动。 依据：`liuyao_zixiu_dxj.full.l2708.rule`。

理法依据与当前推断：

- 条件：用神有根有日月生扶，仍须查动克与救应。 当前应用：申金得酉月同类扶、辰日生，不空不破，是旺用。父巳动化寅回头生，有克子孙的不利方向，不能只凭申旺忽略。 依据：`liuyao_zixiu_dxj.full.l3072.rule`、`liuyao_zixiu_dxj.full.l3188.rule`、`liuyao_zixiu_dxj.full.l2708.rule`。
- 条件：日冲静爻须月扶或动爻生助等才论暗动；元忌同动转生还须元神有效、用神有根。 当前应用：戌土受辰日同类冲，虽不得酉月生扶，但有巳火明动生助，倾向论元神戌暗动。火生土、土生申可转移火克金的压力，旺用有根，支持凶中有救。暗动是按条件作的人工解释，不是程序已定事实。 依据：`liuyao_zixiu_dxj.full.l4308.rule`、`zengshan_pingshi_dxj-l5786-hidden-strength`、`zengshan_buyi.manual.L05862C0000.rule`、`liuyao_zixiu_dxj.full.l2708.rule`、`zengshan_pingshi_dxj-l2902-ineffective-jishen`。
- 条件：伏、变不能任意当主卦明动；变爻只回作用本位。 当前应用：寅是初爻所化，不越位冲五爻申另加凶；申下伏子水妻财旬空，也不偷换成侄子或已发动的救应。 依据：`zengshan_buyi.manual.L02382C0000.rule`、`liuyao_zixiu_dxj.full.l3188.rule`。

象法条件与当前推断：

- 条件：父母白虎动克世为典型，其他六神父母动克世也可能伤身，五爻道路可增强；必读导语要求情境综合。 当前应用：车祸昏迷是输入事实，不是本轮发现。白虎父午静，未满足白虎父动条件；实际动者是朱雀父巳，对五爻申有克，与广义父母动克世伤身条文相容。只解释已知背景，不据白虎、五爻或车祸象直接断死亡。 依据：`liuyao_xiangfa_jinjie_shang.manual.p0186_tiger_parent_accident`。

额外细节预测：

无。

不确定性：

- 戌土能否有效暗动转生是关键解释，已列条件，但不是确定事实。
- 未给昏迷持续时间和治疗进程，不套近病久病空合规则。
- 不预测苏醒日期、完全康复、后遗症种类或医学指标。

本例证据 ID：`zengshan_buyi.manual.L02014.rule`、`liuyao_zixiu_dxj.full.l2152.rule`、`liuyao_zixiu_dxj.full.l2708.rule`、`liuyao_zixiu_dxj.full.l3072.rule`、`liuyao_zixiu_dxj.full.l3188.rule`、`liuyao_zixiu_dxj.full.l4308.rule`、`zengshan_pingshi_dxj-l5786-hidden-strength`、`zengshan_buyi.manual.L05862C0000.rule`、`zengshan_pingshi_dxj-l2902-ineffective-jishen`、`zengshan_buyi.manual.L02382C0000.rule`、`liuyao_xiangfa_jinjie_shang.manual.p0186_tiger_parent_accident`。

排盘记录：predictor-astra-01-charts #4；predictor-astra-05-application #9。

## C05 · 占问事宜：租这个店铺好吗

**以租店经营求财为问意，倾向这处店铺可以经营并有获利机会；过程有压力和阻滞，不能断轻松顺遂。**

把握：低。应期：null。弃断：否。

盘面事实：丑月，甲寅日；火风鼎 → 火天大有；世2应5；动爻[1]；旬空子、丑。本变卦均与输入一致。

| 位 | 六神 | 本卦六亲地支 | 世应 | 动变 | 伏神 |
| --- | --- | --- | --- | --- | --- |
| 6 | 玄武 | 兄弟巳火 | — | 静 | — |
| 5 | 白虎 | 子孙未土 | 应 | 静 | — |
| 4 | 螣蛇 | 妻财酉金 | — | 静 | — |
| 3 | 勾陈 | 妻财酉金 | — | 静 | — |
| 2 | 朱雀 | 官鬼亥水 | 世 | 静 | — |
| 1 | 青龙 | 子孙丑土 | — | 官鬼子水 | 父母卯木 |

取用：

- 经营收益主用候选：primary 层第3爻 妻财酉。默认租店为经营求财；三四静酉财日月空破相同，不强行唯一化。 依据：`liuyao_zixiu_dxj.full.l2260.rule`、`zengshan_buyi.manual.L05466C0000.rule`。
- 并列收益候选：primary 层第4爻 妻财酉。同支同层两财不自动代表两份收益或两个店铺。 依据：`liuyao_zixiu_dxj.full.l2260.rule`、`zengshan_buyi.manual.L05466C0000.rule`。
- 求测者承受与处境：primary 层第2爻 官鬼亥。世爻定位自己，不由官鬼持世自动断灾。 依据：`liuyao_zixiu_dxj.full.l2212.rule`。
- 店铺、租约辅助对象：hidden 层第1爻 父母卯。主卦父不现，取初爻伏父；moving=null，不当明动。 依据：`liuyao_zixiu_dxj.full.l2136.rule`、`zengshan_buyi.manual.L04014C0000.rule`。

理法依据与当前推断：

- 条件：经营求财须主财有根、元神能生，不只凭持世六亲。 当前应用：酉财得丑月生；寅日不是克酉金的方向。初爻子孙丑临月动生财，是收益的主要正向依据。财有根又得旺元生，倾向有获利机会。 依据：`liuyao_zixiu_dxj.full.l3072.rule`、`liuyao_zixiu_dxj.full.l3188.rule`、`liuyao_zixiu_dxj.full.l2708.rule`、`liuyao_zixiu_dxj.full.l2260.rule`。
- 条件：旺动空、动化空非永久无用；旬内仍可等待，动化合与回头克不同。 当前应用：元丑旬空且化子亦空，但临月明动，不作一空到底。丑化子为动化合，没有回头克。可有等待牵绊，不断永久无财源或出空当天必盈利。 依据：`liuyao_zixiu_dxj.full.l3536.rule`、`zengshan_buyi.manual.L02842C0000.rule`、`zengshan_buyi.manual.L05790C0000.rule`、`zengshan_buyi.manual.L02430C0000.rule`。
- 条件：世受克与财生扶须兼看；元忌同动条件不能放宽为静爻都已参与。 当前应用：世亥受月土克、寅日合，动丑亦有克世方向，是强反证。酉财静，不宣称元忌双动通关已成立。主方向按财有根且得旺元生取低把握偏吉，不许诺轻松或确定净利。 依据：`liuyao_zixiu_dxj.full.l2212.rule`、`liuyao_lifa_jinjie.manual.p0143_day_combine_moving`、`zengshan_buyi.manual.L05862C0000.rule`、`zengshan_pingshi_dxj-l3586-moving-over-static`、`zengshan_pingshi_dxj-l1926-wealth-shiyao-critique`。

象法条件与当前推断：

- 条件：子孙取财源须经营问事；其他组合须有可用原文及对象条件。 当前应用：子孙丑动与财源角色相关，已纳入理法。应位白虎子孙未月破不能借胎产标题断生意；虎雀、反吟、进退位无可用完整象法依据，不另造店铺凶事、装修或房东信息。 依据：`liuyao_zixiu_dxj.full.l2152.rule`。

额外细节预测：

无。

不确定性：

- 行业、租金、租期及是否只问签约未知，本断采用经营收益为主的假设。
- 财得旺元生是正向依据，世受动土克是强反证，综合把握低。
- 两静财同支同层不能唯一选定，未当成两个独立财源。
- 无具体收入费用，不给净利润或签约日期。

本例证据 ID：`liuyao_zixiu_dxj.full.l2260.rule`、`zengshan_buyi.manual.L05466C0000.rule`、`liuyao_zixiu_dxj.full.l2212.rule`、`liuyao_zixiu_dxj.full.l2136.rule`、`zengshan_buyi.manual.L04014C0000.rule`、`liuyao_zixiu_dxj.full.l3072.rule`、`liuyao_zixiu_dxj.full.l3188.rule`、`liuyao_zixiu_dxj.full.l2708.rule`、`liuyao_zixiu_dxj.full.l3536.rule`、`zengshan_buyi.manual.L02842C0000.rule`、`zengshan_buyi.manual.L05790C0000.rule`、`zengshan_buyi.manual.L02430C0000.rule`、`liuyao_lifa_jinjie.manual.p0143_day_combine_moving`、`zengshan_buyi.manual.L05862C0000.rule`、`zengshan_pingshi_dxj-l3586-moving-over-static`、`zengshan_pingshi_dxj-l1926-wealth-shiyao-critique`、`liuyao_zixiu_dxj.full.l2152.rule`。

排盘记录：predictor-astra-01-charts #5；predictor-astra-05-application #10；predictor-astra-07-source-audit #22。

## C06 · 占问事宜：去这所学校上学对自己成绩有帮助吗

**倾向去这所学校对学习和成绩有一定帮助，但不能保证立即或大幅提高。**

把握：中低。应期：null。弃断：否。

盘面事实：亥月，丁未日；地水师 → 地风升；世3应6；动爻[3]；旬空寅、卯。本变卦均与输入一致。

| 位 | 六神 | 本卦六亲地支 | 世应 | 动变 | 伏神 |
| --- | --- | --- | --- | --- | --- |
| 6 | 青龙 | 父母酉金 | 应 | 静 | — |
| 5 | 玄武 | 兄弟亥水 | — | 静 | — |
| 4 | 白虎 | 官鬼丑土 | — | 静 | — |
| 3 | 螣蛇 | 妻财午火 | 世 | 父母酉金 | — |
| 2 | 勾陈 | 官鬼辰土 | — | 静 | — |
| 1 | 朱雀 | 子孙寅木 | — | 静 | — |

取用：

- 学校、学习及成绩表现的主用神：primary 层第6爻 父母酉。问特定学校对学习是否有帮助，取学校、师长、文书学习的父母，恰居应位；映射成绩是本次解释，不声称条文直接给分数。 依据：`liuyao_zixiu_dxj.full.l2136.rule`、`zengshan_buyi.manual.L01994.rule`、`liuyao_zixiu_dxj.full.l2212.rule`。
- 世爻所化的学习结果候选：changed 层第3爻 父母酉。三爻明动所化才是实际变爻，同上爻父酉不等于学校已经移动爻位。 依据：`zengshan_buyi.manual.L06254C0000.rule`、`liuyao_zixiu_dxj.full.l6236.rule`。
- 求测者及克父之忌神：primary 层第3爻 妻财午。火克金，须结合日月、动变及元神救应。 依据：`liuyao_zixiu_dxj.full.l2212.rule`、`liuyao_zixiu_dxj.full.l2156.rule`。

理法依据与当前推断：

- 条件：父母主用须与忌神同看；日合不直接等同生扶。 当前应用：父酉得未日生，亥月虽泄气而非得令，仍有根。忌世午受亥月克又合未日，不是旺而无制的忌神，不只因财持世就断无益。 依据：`liuyao_zixiu_dxj.full.l3188.rule`、`liuyao_zixiu_dxj.full.l3072.rule`、`liuyao_lifa_jinjie.manual.p0143_day_combine_moving`。
- 条件：丑日冲须查动生条件；暗动有强弱，元忌共同作用须用神有根。 当前应用：丑官静逢未冲，得午火明动生助，倾向较弱暗动，可承火生父酉，构成火土金连续相生的救应。午同时日合，实际力度仍不确定，不写作必然。 依据：`liuyao_zixiu_dxj.full.l4308.rule`、`zengshan_pingshi_dxj-l5786-hidden-strength`、`liuyao_zixiu_dxj.full.l2708.rule`、`zengshan_pingshi_dxj-l2902-ineffective-jishen`。
- 条件：忌神持世化用有例外，应期条文本身不证成败；变爻只回作用本位。 当前应用：世财午实际化父酉，有从忌转成所问对象的方向，可辅助学习事项落实。财化父见父不能径等同分数必升；综合主父生扶与元神救应，取有一定帮助。 依据：`zengshan_buyi.manual.L06254C0000.rule`、`liuyao_zixiu_dxj.full.l6236.rule`、`zengshan_buyi.manual.L02382C0000.rule`。
- 条件：死地规则要分测病、旺衰及作者范围；独发不能替代主用。 当前应用：午化酉被软件标作化死，实际不是父母主用神化死，本问也非疾病。各书十二状态取舍不同，不用单个化死或独发标签断学业失败。 依据：`liuyao_zixiu_dxj.full.l4076.rule`、`zengshan_pingshi_dxj-l6730-life-states`、`zengshan_buyi.manual.L05262C0000.rule`。

象法条件与当前推断：

- 条件：父财互化价格条文限财运交易，婚恋分支另有对象条件，必读导语强调随事项取象。 当前应用：世财化父结构虽有，问的是成绩帮助，不能套价格条文断学费高，更不能套婚史。没有足够专项象法断学校层次、教师性格或进步幅度。 依据：`liuyao_xiangfa_jinjie_shang.manual.p0191_parent_wealth_transform`。

额外细节预测：

无。

不确定性：

- 成绩映射来自学校、师长、文书文章通则，未检出直接针对分数提升的规则。
- 升学名次可取官鬼，但本问不是录取，不为改变题意另换主用。
- 丑暗动与午被合的力度有争议，是主要不确定处。
- 没有原成绩、考试日期和入学计划，不给分数、名次、比例或应期。

本例证据 ID：`liuyao_zixiu_dxj.full.l2136.rule`、`zengshan_buyi.manual.L01994.rule`、`liuyao_zixiu_dxj.full.l2212.rule`、`zengshan_buyi.manual.L06254C0000.rule`、`liuyao_zixiu_dxj.full.l6236.rule`、`liuyao_zixiu_dxj.full.l2156.rule`、`liuyao_zixiu_dxj.full.l3188.rule`、`liuyao_zixiu_dxj.full.l3072.rule`、`liuyao_lifa_jinjie.manual.p0143_day_combine_moving`、`liuyao_zixiu_dxj.full.l4308.rule`、`zengshan_pingshi_dxj-l5786-hidden-strength`、`liuyao_zixiu_dxj.full.l2708.rule`、`zengshan_pingshi_dxj-l2902-ineffective-jishen`、`zengshan_buyi.manual.L02382C0000.rule`、`liuyao_zixiu_dxj.full.l4076.rule`、`zengshan_pingshi_dxj-l6730-life-states`、`zengshan_buyi.manual.L05262C0000.rule`、`liuyao_xiangfa_jinjie_shang.manual.p0191_parent_wealth_transform`。

排盘记录：predictor-astra-01-charts #6；predictor-astra-05-application #11；predictor-astra-07-source-audit #23。

## 必读上下文与证据保全

三条已回查组合象法均带下列完整 required_contexts 共享导语。具体婚恋、交易、伤身限制分别保留于各例。JSON 的 evidence_records 保存每条证据的实际批次、调用序号、原文文本哈希（经 get_source 者）及完整 required_contexts；正文与坐标保留在本任务 records 原始返回中。

> 在预测中，取象并不像我们上一章所讲那样，仅仅从单一的六神入手，往往需要结合六神，六亲，爻位，卦象，地支，五行，十二长生和具体所测的事情进行综合分析，得出完整的卦象。在写本书前，很多学员都要求将六亲六神爻位等组合之象进行详细论述，然而，这种组合在占验不同的事情时，其所表现出来的寓意各不相同，想要完整的进行归纳整理并不现实，只能选择一些有代表性的组合，尽量归纳其大致规律，再根据所测具体事情加以推理运用。本章大致罗列部分应验度较高的组合之象，供读者参考。

导语返回的 quote_sha256：`733a2ba9d467b27947cf3b5a8f3e840b6c43836d361e23992f824cd346cb8fcd`。本轮婚事规则实际返回只有此 required_context，未补读已移除或不可用上下文。

规则库范围有限，未检出不等于书中没有。unavailable 的结构引用未作已查证原文。三条象法直接用排盘返回的真实规则 ID 回查；本轮未调用规则引用解析接口，不存在返回 targets 后漏读的问题。

## 调用批次

| 批次 | build_chart | search_knowledge | get_source | 成功 | 失败 |
| --- | ---: | ---: | ---: | ---: | ---: |
| predictor-astra-01-charts | 6 | 0 | 0 | 6 | 0 |
| predictor-astra-02-rules | 0 | 9 | 0 | 9 | 0 |
| predictor-astra-03-targeted | 0 | 8 | 5 | 13 | 0 |
| predictor-astra-04-conditions | 0 | 8 | 0 | 8 | 0 |
| predictor-astra-05-application | 6 | 5 | 0 | 11 | 0 |
| predictor-astra-06-final-gaps | 0 | 5 | 0 | 5 | 0 |
| predictor-astra-07-source-audit | 3 | 2 | 18 | 23 | 0 |

七个批次全部完成。零检索结果仍属成功调用，不表示找到专项依据。工具成功与预测正确性分开统计。预测锁定后不再修改，揭晓与评分不属于本文件。
