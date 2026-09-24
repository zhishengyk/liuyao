# 书籍语料归档

本分支是整理后的完整资料归档。原始快照保存在 `books-archive-raw-20260914`，第一版整理保存在 `books-archive-reorg-v1`。

## 目录规则

所有 canonical 正文统一使用：

`books/<学科>/<作者>/<资料性质>/<文档>.md`

六爻资料统一细分为核心著作、基础理论、理象、用神、旺衰、生克冲合、应期、分类占、卦例、答疑、讲义记录、趋吉避凶、他人整理、来源存疑。八字、风水、奇门、面相和易学综合使用各自对应的专题分类。

- `books/`: 258 份 canonical 正文，默认检索范围。
- `variants/`: 52 份同题完整版本。
- `collections/易学综合/南怀瑾/著作大全/`: CHM 合集页面，保持合集语境。
- `support/`: OCR 和图片附件。
- `quarantine/`: 软件、数据库、网页支持文件等非正文。
- `archive_meta/`: 压缩包入口、历史别名、旧索引和校验记录。
- `catalog/files.jsonl`: 全部原始文件迁移映射。
- `catalog/retrieval_manifest.jsonl`: canonical 检索白名单。
- `catalog/duplicate_groups.json`: canonical 与 variants 关系。
- `catalog/INDEX.md`: 全作者分类统计。

作者无法可靠确定时保留为“佚名”，不会猜测作者。