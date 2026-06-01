# AI 写作助手

AI 驱动的长篇小说写作工作台，包含 **Obsidian 插件** + **Python 脚本** 两套工具链。

## 项目结构

```
AI写作助手/
├── NovelProject/                  # Python 脚本 + 小说项目
│   ├── auto_write.py              # 一键编排器
│   ├── generate_chapter.py        # 核心章节生成器
│   ├── build_context.py           # 生成写作上下文
│   ├── build_characters.py        # 人物笔记管理
│   ├── update_hooks.py            # 伏笔追踪表
│   ├── analyze_scene_type.py      # 场景分析
│   ├── generate_ideas.py          # AI 灵感生成
│   ├── update_plot_outline.py     # 章节规划表维护
│   ├── Novels/                    # 小说存放目录
│   │   └── 文明升阶/               # 示例小说
│   ├── Templates/                 # Markdown 模板
│   └── 操作手册.md                 # 详细操作文档
│
└── .obsidian/plugins/
    └── ai-novelist-studio/        # Obsidian 插件（TypeScript）
        ├── main.ts                # 插件入口
        ├── view.ts                # 主视图 UI
        ├── fileUtils.ts           # 文件操作工具
        ├── api.ts                 # DeepSeek API 封装
        ├── settings.ts            # 设置面板
        └── modals.ts              # 模态框组件
```

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+（仅插件开发需要）
- DeepSeek API Key

### 1. 安装 Python 依赖

```powershell
cd NovelProject
pip install requests pyyaml
```

### 2. 配置 API Key

复制 `.env.example` 为 `.env`，填入你的 Key：

```
DEEPSEEK_API_KEY=sk-你的key
```

### 3. 一键写下一章

```powershell
python auto_write.py --novel "文明升阶" --goal "你的写作目标" --update-characters --update-hooks
```

详细命令见 [操作手册](NovelProject/操作手册.md)。

### 4. Obsidian 插件

将 `.obsidian/plugins/ai-novelist-studio/` 复制到你的 Obsidian Vault 的 `.obsidian/plugins/` 目录下，在 Obsidian 设置中启用。

插件配置模板：`data.json.example` → 复制为 `data.json` 并填入 Key。

## 功能特性

- **一键写作**：自动生成上下文 → 调用 AI 写章节 → 更新人物/伏笔/大纲
- **连续性保障**：读取上一章结尾，确保情节和情绪无缝衔接
- **场景多样性**：自动分析场景类型，避免连续章节类型重复
- **大纲同步**：生成章节后自动更新 Plot_Outline.md（章节表、伏笔表、衔接说明）
- **人物追踪**：自动提取新增人物，维护出现章节列表
- **伏笔管理**：扫描元数据区块，更新 Hooks_Tracker.md
- **双向链接**：Obsidian `[[wiki-link]]` 格式，支持关系图谱

## 技术栈

| 层 | 技术 |
|----|------|
| Python 脚本 | pathlib, argparse, yaml, requests, subprocess |
| Obsidian 插件 | TypeScript, Obsidian API, esbuild |
| AI 接口 | DeepSeek Chat API |
| 数据格式 | Markdown + YAML Frontmatter |
