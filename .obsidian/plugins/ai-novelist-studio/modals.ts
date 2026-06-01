// modals.ts — 所有模态框组件
// 包括: 灵感选择、编辑人物、编辑伏笔、编辑元数据、编辑世界观

import {
    App, Modal, Setting, TextAreaComponent, TextComponent,
    ButtonComponent, TFile, Notice
} from "obsidian";
import type AINovelistPlugin from "./main";
import {
    CharacterInfo, HookInfo, parseFrontmatter,
    serializeFrontmatter, parseChapterMetadataSection
} from "./fileUtils";

// ============================================================
//  灵感选择模态框
// ============================================================

/**
 * 从 Ideas.md 中解析灵感列表，让用户选择填充到写作目标框
 */
export class IdeaPickerModal extends Modal {
    plugin: AINovelistPlugin;
    onSelect: (title: string, content: string) => void;
    ideas: { title: string; content: string }[];

    constructor(
        app: App,
        plugin: AINovelistPlugin,
        ideas: { title: string; content: string }[],
        onSelect: (title: string, content: string) => void
    ) {
        super(app);
        this.plugin = plugin;
        this.ideas = ideas;
        this.onSelect = onSelect;
    }

    onOpen() {
        const { contentEl } = this;
        contentEl.empty();

        contentEl.createEl("h3", { text: "从灵感库选择" });

        if (this.ideas.length === 0) {
            contentEl.createEl("p", {
                text: "暂无灵感记录。请在写作标签页中先点击「生成灵感」。",
                cls: "ai-ns-empty-hint"
            });
            return;
        }

        for (const idea of this.ideas) {
            const card = contentEl.createDiv({ cls: "ai-ns-idea-card" });

            // 标题
            const titleEl = card.createEl("div", {
                text: idea.title,
                cls: "ai-ns-idea-title"
            });

            // 内容预览（截取前200字）
            const preview = idea.content.substring(0, 200) + (idea.content.length > 200 ? "..." : "");
            card.createEl("div", {
                text: preview,
                cls: "ai-ns-idea-preview"
            });

            // 点击选择
            card.addEventListener("click", () => {
                this.onSelect(idea.title, idea.content);
                this.close();
            });
        }
    }

    onClose() {
        const { contentEl } = this;
        contentEl.empty();
    }
}

// ============================================================
//  人物编辑模态框
// ============================================================

/**
 * 编辑或新建人物档案
 */
export class CharacterEditModal extends Modal {
    plugin: AINovelistPlugin;
    character: CharacterInfo | null;
    content: string;
    onSave: (name: string, content: string) => void;
    nameField: TextComponent;
    contentField: TextAreaComponent;

    constructor(
        app: App,
        plugin: AINovelistPlugin,
        character: CharacterInfo | null,
        content: string,
        onSave: (name: string, content: string) => void
    ) {
        super(app);
        this.plugin = plugin;
        this.character = character;
        this.content = content;
        this.onSave = onSave;
    }

    onOpen() {
        const { contentEl } = this;
        contentEl.empty();

        const isNew = !this.character;
        contentEl.createEl("h3", {
            text: isNew ? "+ 新建人物" : `编辑人物 — ${this.character?.name}`
        });

        // 姓名（新建时可编辑，编辑时固定）
        new Setting(contentEl)
            .setName("姓名")
            .addText(text => {
                this.nameField = text;
                text.setValue(this.character?.name || "")
                    .setPlaceholder("人物姓名");

                if (this.character) {
                    text.setDisabled(true);
                }
            });

        // 内容编辑区
        new Setting(contentEl)
            .setName("人物档案 (Markdown)")
            .setDesc("支持完整的 Markdown 语法。可使用 ## 出现章节, ## 核心能力, ## 人际关系 等段落。");

        this.contentField = new TextAreaComponent(contentEl);
        this.contentField.setValue(this.content)
            .setPlaceholder(
                `---\nname: "人物名"\nstatus: "活跃"\n---\n\n` +
                `# 人物名\n\n## 基本设定\n...\n`
            );
        this.contentField.inputEl.rows = 20;
        this.contentField.inputEl.style.width = "100%";
        this.contentField.inputEl.style.minHeight = "400px";

        // 按钮区
        const buttonRow = contentEl.createDiv({ cls: "ai-ns-modal-buttons" });

        new ButtonComponent(buttonRow)
            .setButtonText("保存")
            .setCta()
            .onClick(async () => {
                const name = this.nameField.getValue().trim();
                if (!name) {
                    new Notice("请输入人物姓名");
                    return;
                }
                const content = this.contentField.getValue();
                this.onSave(name, content);
                this.close();
            });

        new ButtonComponent(buttonRow)
            .setButtonText("取消")
            .onClick(() => this.close());
    }

    onClose() {
        const { contentEl } = this;
        contentEl.empty();
    }
}

// ============================================================
//  伏笔编辑模态框
// ============================================================

/**
 * 新建或编辑伏笔条目
 */
export class HookEditModal extends Modal {
    plugin: AINovelistPlugin;
    hook: HookInfo | null;
    onSave: (hook: HookInfo) => void;
    idField: TextComponent;
    descField: TextAreaComponent;
    plantedField: TextComponent;
    planField: TextComponent;
    statusField: TextComponent;

    constructor(
        app: App,
        plugin: AINovelistPlugin,
        hook: HookInfo | null,
        onSave: (hook: HookInfo) => void
    ) {
        super(app);
        this.plugin = plugin;
        this.hook = hook;
        this.onSave = onSave;
    }

    onOpen() {
        const { contentEl } = this;
        contentEl.empty();

        const isNew = !this.hook;
        contentEl.createEl("h3", {
            text: isNew ? "+ 新建伏笔" : `编辑伏笔 — ${this.hook?.id}`
        });

        // ID
        new Setting(contentEl)
            .setName("ID")
            .addText(text => {
                this.idField = text;
                text.setValue(this.hook?.id || "H-")
                    .setPlaceholder("H-001");
                if (this.hook) text.setDisabled(true);
            });

        // 描述
        new Setting(contentEl)
            .setName("描述")
            .setDesc("伏笔的具体内容描述");

        this.descField = new TextAreaComponent(contentEl);
        this.descField.setValue(this.hook?.description || "")
            .setPlaceholder("描述伏笔/悬念内容...");
        this.descField.inputEl.rows = 4;
        this.descField.inputEl.style.width = "100%";

        // 埋坑章节
        new Setting(contentEl)
            .setName("埋坑章节")
            .addText(text => {
                this.plantedField = text;
                text.setValue(this.hook?.plantedChapter || "")
                    .setPlaceholder("如 第3章");
            });

        // 计划填坑章节
        new Setting(contentEl)
            .setName("计划填坑章节")
            .addText(text => {
                this.planField = text;
                text.setValue(this.hook?.planChapter || "")
                    .setPlaceholder("如 第8章");
            });

        // 状态
        new Setting(contentEl)
            .setName("状态")
            .addText(text => {
                this.statusField = text;
                text.setValue(this.hook?.status || "unresolved")
                    .setPlaceholder("unresolved / resolved (第X章)");
            });

        // 按钮区
        const buttonRow = contentEl.createDiv({ cls: "ai-ns-modal-buttons" });

        new ButtonComponent(buttonRow)
            .setButtonText("保存")
            .setCta()
            .onClick(() => {
                const hookInfo: HookInfo = {
                    id: this.idField.getValue().trim(),
                    description: this.descField.getValue().trim(),
                    plantedChapter: this.plantedField.getValue().trim(),
                    planChapter: this.planField.getValue().trim(),
                    status: this.statusField.getValue().trim(),
                };

                if (!hookInfo.id || !hookInfo.description) {
                    new Notice("请填写 ID 和描述");
                    return;
                }

                this.onSave(hookInfo);
                this.close();
            });

        new ButtonComponent(buttonRow)
            .setButtonText("取消")
            .onClick(() => this.close());
    }

    onClose() {
        const { contentEl } = this;
        contentEl.empty();
    }
}

// ============================================================
//  章节元数据编辑模态框
// ============================================================

/**
 * 手动编辑当前章节的 frontmatter 和元数据区块
 */
export class ChapterMetadataModal extends Modal {
    plugin: AINovelistPlugin;
    file: TFile;
    originalContent: string;
    frontmatterField: TextAreaComponent;
    metadataField: TextAreaComponent;
    onSave: (newContent: string) => Promise<void>;

    constructor(
        app: App,
        plugin: AINovelistPlugin,
        file: TFile,
        originalContent: string,
        onSave: (newContent: string) => Promise<void>
    ) {
        super(app);
        this.plugin = plugin;
        this.file = file;
        this.originalContent = originalContent;
        this.onSave = onSave;
    }

    onOpen() {
        const { contentEl } = this;
        contentEl.empty();

        contentEl.createEl("h3", { text: `编辑章节元数据 — ${this.file.name}` });

        // 解析现有 frontmatter 和元数据
        const [fm, body] = parseFrontmatter(this.originalContent);
        const fmText = fm ? serializeFrontmatter(fm).replace(/^---\n|(\n---\n?$)/g, "") : "";
        const metaData = parseChapterMetadataSection(this.originalContent);
        const metaText = Object.entries(metaData)
            .map(([key, items]) => `### ${key}\n${items.map(i => `- ${i}`).join("\n")}`)
            .join("\n\n");

        // Frontmatter 编辑区
        contentEl.createEl("h4", { text: "Frontmatter (YAML)" });
        this.frontmatterField = new TextAreaComponent(contentEl);
        this.frontmatterField.setValue(fmText);
        this.frontmatterField.inputEl.rows = 8;
        this.frontmatterField.inputEl.style.width = "100%";
        this.frontmatterField.inputEl.style.fontFamily = "monospace";
        this.frontmatterField.inputEl.style.fontSize = "13px";

        // 元数据编辑区
        contentEl.createEl("h4", { text: "本章元数据" });
        this.metadataField = new TextAreaComponent(contentEl);
        this.metadataField.setValue(metaText || "");
        this.metadataField.inputEl.rows = 10;
        this.metadataField.inputEl.style.width = "100%";
        this.metadataField.inputEl.style.fontFamily = "monospace";
        this.metadataField.inputEl.style.fontSize = "13px";

        // 按钮区
        const buttonRow = contentEl.createDiv({ cls: "ai-ns-modal-buttons" });

        new ButtonComponent(buttonRow)
            .setButtonText("保存")
            .setCta()
            .onClick(async () => {
                // 重建文件内容
                let newFm = this.frontmatterField.getValue().trim();
                if (newFm && !newFm.startsWith("---")) {
                    newFm = `---\n${newFm}\n---`;
                }

                const newMeta = this.metadataField.getValue().trim();

                // 替换原有 frontmatter
                let content = this.originalContent;
                const fmMatch = content.match(/^---\s*\n[\s\S]*?\n---\s*\n/);
                if (fmMatch) {
                    content = newFm + "\n" + content.substring(fmMatch[0].length);
                }

                // 替换元数据区块
                const metaMatch = content.match(/\n##\s+本章元数据\s*\n[\s\S]*?(?=\n#|$)/);
                if (metaMatch) {
                    const newMetaBlock = `\n\n## 本章元数据\n\n${newMeta}\n`;
                    content = content.replace(metaMatch[0], newMetaBlock);
                } else if (newMeta) {
                    content = content.trimEnd() + `\n\n## 本章元数据\n\n${newMeta}\n`;
                }

                await this.onSave(content);
                this.close();
            });

        new ButtonComponent(buttonRow)
            .setButtonText("取消")
            .onClick(() => this.close());
    }

    onClose() {
        const { contentEl } = this;
        contentEl.empty();
    }
}

// ============================================================
//  世界观编辑模态框
// ============================================================

/**
 * 编辑世界观主文件 Main_Worldview.md
 */
export class WorldviewEditModal extends Modal {
    plugin: AINovelistPlugin;
    content: string;
    onSave: (content: string) => void;
    editorField: TextAreaComponent;

    constructor(
        app: App,
        plugin: AINovelistPlugin,
        content: string,
        onSave: (content: string) => void
    ) {
        super(app);
        this.plugin = plugin;
        this.content = content;
        this.onSave = onSave;
    }

    onOpen() {
        const { contentEl } = this;
        contentEl.empty();

        contentEl.createEl("h3", { text: "编辑世界观设定" });

        this.editorField = new TextAreaComponent(contentEl);
        this.editorField.setValue(this.content);
        this.editorField.inputEl.rows = 25;
        this.editorField.inputEl.style.width = "100%";
        this.editorField.inputEl.style.minHeight = "500px";
        this.editorField.inputEl.style.fontFamily = "monospace";
        this.editorField.inputEl.style.fontSize = "14px";

        const buttonRow = contentEl.createDiv({ cls: "ai-ns-modal-buttons" });

        new ButtonComponent(buttonRow)
            .setButtonText("保存")
            .setCta()
            .onClick(() => {
                this.onSave(this.editorField.getValue());
                this.close();
            });

        new ButtonComponent(buttonRow)
            .setButtonText("取消")
            .onClick(() => this.close());
    }

    onClose() {
        const { contentEl } = this;
        contentEl.empty();
    }
}
