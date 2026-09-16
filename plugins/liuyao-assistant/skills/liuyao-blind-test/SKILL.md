---
name: liuyao-blind-test
description: 六爻助手大规模盲测、判定、根因归类、提示词规则化修复与 GitHub 发布改进循环。在需要评估六爻 MCP 提示词质量、修复断卦规则、发布新版本时使用；不用于单卦断现。
---

# 六爻盲测改进循环（Blind-Test → 归因 → 规则化修复 → 发布）

## 目标

用大规模外部卦例盲测 liuyao MCP 助手，量化基线一致率，定位系统性问题，**把教训提炼成通用规则写入提示词（而不是背具体案例）**，回归验证后发布新版本置 latest。

## 铁律

- 盲测 agent **只能读题包**（卦盘+日月+题干），**绝不能读判据层**（packets.json 的 feedback / all_answers / 语料）。
- 提示词修正**不得引用具体案号（DAxxx）/具体原句结局**——把案例提炼成"条件 → 判断"的通用规则；agent 学判断力，不背答案。
- 每轮修复都必须配套回归验证（重跑该批 WRONG/代表性的集），确认方向修正后才可发布。

## 工作流

1. **建语料**：收集外部真实卦例 → 匿名化题包（只含盘+题干）→ 作者结论单独存判据层（feedback）。
2. **盲测**：按域开独立 agent，强制 MCP 调用链：`build_chart` → `inspect_chart`（强制）→ ≥2× `search_knowledge`（UTF8 查询文件）→ ≥1 `get_source` 回查原文；全程默认审计 records，禁读判据层。
3. **判定**：判定 agent 逐例把 agent 主判与原文 feedback 比对 → CORRECT / WRONG / PARTIAL / NO_FEEDBACK。NO_FEEDBACK = 判据不可锚（截断/错配/纯理论），不是答错；对"疑似可恢复"（题面带结果词）要二次精判捞回。
4. **量化**：分域统计一致率（可判样本口径），与上个版本基线对比，标出弱领域。
5. **归因**：把 WRONG 案例聚类成机器可修的模式（A 来意/主题错失、B 规则方向相反、C 漏断吉凶、D 其他）。逐类给出"工作流缺陷"而不是"案例记忆"。
6. **修复（本质）**：
   - 无来意题 → 必须凭盘面反推最可能事类（ixé亲持世/动化/世应/最强前兆）直接给**主判+置信度**；**绝不只列分支或"来意未知"戛止**。
   - 教学/理论题 → 规则讲完后必须"落结论"（该例教什么+若实占你会断什么）。
   - 领域反例 → 写成通用规则（如"考学以父母官鬼旺衰为主"“子孙持世不克官反主有才”）并入 domain flow。
   - 全局高频反例（考学/失物/官进/用旺世衰/化退六冲）→ 放全局层。
7. **重建与验证**：`python scripts/build_skill_prompts.py --database data/knowledge.sqlite --output src/liuyao_mcp/_data/source-prompts`，确认生成产物里 **0 案例号残留**；`pytest tests/test_skill_prompt_export.py`（3 passed）。
8. **发布**：bump `__version__` + plugin.json + .mcp.json → CHANGELOG 写明本轮依据 → commit+push main → `git tag vX.Y.Z && git push origin vX.Y.Z` → 等 CI（全链路: ingest→测试→build release→冒烟） → 确认 Release 7 资产 + `/releases/latest` = 新版本。
9. **循环**：回第 1 步，用新版本重测全集或增量，对比新基线。

## 常见切入点

- 用户说"正确率多少/提升"→ 跑第 2-4 步出可判基线。
- 用户说"盲测、修复、还有没有毛病"→ 从第 5-6 步做归因修复。
- 用户说"装进流程/成 skill"→ 本文档即搬运起点。

## 参考

- 判断 Workflow: `plugins/liuyao-assistant/skills/interpret-liuyao/SKILL.md`（断卦执行）
- 领域规则真源 `scripts/skill_prompt_plan.json`；生成代码 scripts/build_skill_prompts.py
- 回归现场 C:\Users\duanshengxuan\Desktop\.working\liuyao-external-eval\（题包/答案/判定/回归目录）