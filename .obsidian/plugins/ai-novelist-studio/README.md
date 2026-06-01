# AI 小说工作室

AI 驱动的长篇小说写作助手 Obsidian 插件，可在 Obsidian 侧边栏内一键生成章节、管理人物档案、追踪伏笔。

## 功能

- **一键写作**：自动构建上下文 → 调用 DeepSeek AI → 生成章节 → 更新人物/伏笔
- **连续性保障**：自动读取上一章结尾，确保情节和情绪无缝衔接
- **场景多样性**：避免连续章节类型重复
- **大纲同步**：生成后自动更新 Plot_Outline.md
- **人物追踪**：自动提取新增人物并维护档案
- **伏笔管理**：自动扫描元数据并更新 Hooks_Tracker.md

## 安装

### BRAT 测试
1. 安装 [BRAT](https://github.com/TfTHacker/obsidian42-brat) 插件
2. 在 BRAT 设置中添加 `tingyu220/AI-`
3. 在「第三方插件」中启用「AI 小说工作室」

### 手动安装
1. 从 [Releases](https://github.com/tingyu220/AI-/releases) 下载最新版
2. 解压到 `<vault>/.obsidian/plugins/ai-novelist-studio/`
3. 在 Obsidian 设置中启用

## 配置

1. 在插件设置填入 [DeepSeek API Key](https://platform.deepseek.com/api_keys)
2. 设置小说根目录路径（默认 `NovelProject/Novels`）
3. 其余选项按需调整

## 使用

- 点击左侧 Ribbon 的书本图标打开写作面板
- 或 `Ctrl+P` → 搜索「AI 小说工作室」
- 选择小说 → 点击「一键写下一章」
- 内容将保存为 Markdown 到 Vault

## 搭配命令行

```powershell
cd NovelProject
pip install requests pyyaml
python auto_write.py --novel "文明升阶" --goal "写作目标" --update-characters --update-hooks
```