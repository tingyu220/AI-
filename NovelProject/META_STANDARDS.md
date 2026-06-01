# META_STANDARDS.md — 全局 Frontmatter 规范

> 本文件定义了 NovelProject 仓库中所有 Markdown 笔记的 YAML Frontmatter 字段标准。
> 每部小说的笔记应根据用途，从下方模板中选择对应的 Frontmatter 结构。

---

## 1. 人物档案 Frontmatter

用于 `01_Characters/` 下的每个人物 `.md` 文件。

```yaml
---
type: character
novel: "<小说名>"
name: "<人物全名>"
aliases: ["<别名1>", "<别名2>"]
role: "<主角|配角|反派|背景>"
gender: "<男|女|其他|未知>"
age: "<年龄或年龄段>"
faction: "<所属势力/组织>"
first_appearance: "<首次登场章节编号, 例如 Ch03>"
status: "<活跃|已故|退场|待定>"
tags: ["<标签1>", "<标签2>"]
summary: "<一句话简介>"
created: "<创建日期 YYYY-MM-DD>"
updated: "<更新日期 YYYY-MM-DD>"
---
```

---

## 2. 章节正文 Frontmatter

用于 `03_Chapters/` 下的每个章节 `.md` 文件。

```yaml
---
type: chapter
novel: "<小说名>"
volume: <卷号, 整数>
chapter: <章号, 整数>
title: "<章节标题>"
pov: "<视角人物名>"
timeline: "<故事内时间, 例如 星历1427年·秋>"
location: "<主要场景>"
characters: ["<登场人物1>", "<登场人物2>"]
foreshadowing_ids: ["<关联伏笔ID>"]
word_count: <字数, 整数>
status: "<draft|revised|final>"
summary: "<本章概要, 不含剧透式行文>"
created: "<YYYY-MM-DD>"
updated: "<YYYY-MM-DD>"
---
```

---

## 3. 伏笔管理 Frontmatter

用于 `04_Foreshadowing/` 下每个伏笔 `.md` 文件。

```yaml
---
type: foreshadowing
novel: "<小说名>"
id: "<伏笔唯一ID, 如 FS-001>"
planted_in: "<埋设章节, 如 Ch05>"
resolved_in: "<回收章节, 留空表示未回收>"
status: "<planted|partial|resolved>"
description: "<伏笔简述>"
payoff: "<预计/实际的回收方式>"
created: "<YYYY-MM-DD>"
updated: "<YYYY-MM-DD>"
---
```

---

## 4. 世界观文档 Frontmatter

用于 `00_Worldview/` 下的设定文档。

```yaml
---
type: worldview
novel: "<小说名>"
category: "<地理|历史|政治|魔法体系|科技|种族|其他>"
title: "<文档标题>"
tags: ["<标签>"]
created: "<YYYY-MM-DD>"
updated: "<YYYY-MM-DD>"
---
```

---

## 5. 大纲文档 Frontmatter

用于 `02_Outline/` 下的大纲文件。

```yaml
---
type: outline
novel: "<小说名>"
title: "<大纲标题>"
scope: "<全书|分卷|章节>"
status: "<draft|final>"
created: "<YYYY-MM-DD>"
updated: "<YYYY-MM-DD>"
---
```

---

## 6. 上下文摘要 Frontmatter

用于 `05_Context/` 下的上下文快照文件。

```yaml
---
type: context
novel: "<小说名>"
title: "<上下文快照标题>"
last_chapter: "<最后完成章节>"
next_chapter: "<下一章计划>"
current_pov: "<当前视角人物>"
open_foreshadowing: ["<未回收伏笔ID列表>"]
created: "<YYYY-MM-DD>"
updated: "<YYYY-MM-DD>"
---
```

---

## 通用规则

- **日期格式**：统一使用 `YYYY-MM-DD`。
- **列表值**：多条内容使用 YAML 数组格式 `["值1", "值2"]`。
- **必填字段**：`type`、`novel`、`created` 在所有笔记中均为必填。
- **新增字段**：如需扩展，请在本文档末尾的「扩展字段登记」区域记录，避免冲突。

---

## 扩展字段登记

<!-- 如有自定义字段，在下方登记说明 -->
（暂无扩展）
