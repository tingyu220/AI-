// settings.ts — 插件设置页
// 使用 Obsidian PluginSettingTab API 构建全局设置表单

import { App, PluginSettingTab, Setting } from "obsidian";
import type AINovelistPlugin from "./main";

/**
 * 插件设置数据结构
 */
export interface AINovelistSettings {
    apiKey: string;
    aiModel: string;
    novelsRootPath: string;
    temperature: number;
    enableContinuityCheck: boolean;
    maxContextChapters: number;
    maxTokens: number;
    sceneDiversity: number;
    autoUpdateOutline: boolean;
}

export const DEFAULT_SETTINGS: AINovelistSettings = {
    apiKey: "",
    aiModel: "deepseek-chat",
    novelsRootPath: "NovelProject/Novels",
    temperature: 0.7,
    enableContinuityCheck: true,
    maxContextChapters: 3,
    maxTokens: 4096,
    sceneDiversity: 0.5,
    autoUpdateOutline: true,
};

/** 可用的 DeepSeek 模型列表 */
const MODEL_OPTIONS: Record<string, string> = {
    "deepseek-chat": "DeepSeek Chat (通用)",
    "deepseek-reasoner": "DeepSeek Reasoner (推理增强)",
};

export class AINovelistSettingTab extends PluginSettingTab {
    plugin: AINovelistPlugin;

    constructor(app: App, plugin: AINovelistPlugin) {
        super(app, plugin);
        this.plugin = plugin;
    }

    display(): void {
        const { containerEl } = this;
        containerEl.empty();

        // ---- 标题 ----
        containerEl.createEl("h2", { text: "AI 小说工作室 — 全局设置" });

        // ---- API Key ----
        new Setting(containerEl)
            .setName("DeepSeek API Key")
            .setDesc("用于调用 DeepSeek API 生成章节内容。Key 以安全方式本地存储。")
            .addText(text => {
                text.setPlaceholder("sk-xxxxxxxxxxxxxxxxxxxx")
                    .setValue(this.plugin.settings.apiKey)
                    .onChange(async (value) => {
                        this.plugin.settings.apiKey = value.trim();
                        await this.plugin.saveSettings();
                    });
                // 密码输入框遮罩
                text.inputEl.type = "password";
            });

        // ---- AI 模型选择 ----
        new Setting(containerEl)
            .setName("AI 模型")
            .setDesc("选择用于生成内容的 DeepSeek 模型。推荐 deepseek-chat。")
            .addDropdown(dropdown => {
                for (const [value, label] of Object.entries(MODEL_OPTIONS)) {
                    dropdown.addOption(value, label);
                }
                dropdown.setValue(this.plugin.settings.aiModel)
                    .onChange(async (value) => {
                        this.plugin.settings.aiModel = value;
                        await this.plugin.saveSettings();
                    });
            });

        // ---- 小说根目录路径 ----
        new Setting(containerEl)
            .setName("小说根目录路径")
            .setDesc("Vault 中的小说文件夹路径（相对路径）。例如: NovelProject/Novels。支持 Windows 绝对路径自动转换。")
            .addText(text => {
                text.setPlaceholder("NovelProject/Novels")
                    .setValue(this.plugin.settings.novelsRootPath)
                    .onChange(async (value) => {
                        // 自动修正：去除首尾多余空格和斜杠，统一为相对路径格式
                        let cleanValue = value.trim().replace(/\\/g, "/");
                        cleanValue = cleanValue.replace(/^\/+|\/+$/g, "");
                        // 如果是绝对路径（如 D:/xxx），尝试提取 vault 相对部分保留原样
                        // getNovelList 会自动处理
                        this.plugin.settings.novelsRootPath = cleanValue || "NovelProject/Novels";
                        text.setValue(this.plugin.settings.novelsRootPath);
                        await this.plugin.saveSettings();
                    });
            });

        // ---- 生成温度 ----
        new Setting(containerEl)
            .setName("生成温度")
            .setDesc(`控制 AI 生成内容的随机性和创造性。当前值: ${this.plugin.settings.temperature}`)
            .addSlider(slider => {
                slider.setLimits(0, 2.0, 0.1)
                    .setValue(this.plugin.settings.temperature)
                    .setDynamicTooltip()
                    .onChange(async (value) => {
                        this.plugin.settings.temperature = value;
                        // 更新描述中的当前值显示
                        const descEl = containerEl.querySelector(
                            `.setting-item:nth-child(${this.getSettingIndex(containerEl, "生成温度") + 1}) .setting-item-description`
                        );
                        if (descEl) {
                            descEl.textContent = `控制 AI 生成内容的随机性和创造性。当前值: ${value}`;
                        }
                        await this.plugin.saveSettings();
                    });
            });

        // ---- 参考章节数 ----
        new Setting(containerEl)
            .setName("上下文参考章节数")
            .setDesc("生成新章节时参考最近 N 章的内容。默认 3 章。")
            .addSlider(slider => {
                slider.setLimits(1, 10, 1)
                    .setValue(this.plugin.settings.maxContextChapters)
                    .setDynamicTooltip()
                    .onChange(async (value) => {
                        this.plugin.settings.maxContextChapters = value;
                        await this.plugin.saveSettings();
                    });
            });

        // ---- 最大 Token 数 ----
        new Setting(containerEl)
            .setName("最大生成 Token 数")
            .setDesc("每次 API 调用允许返回的最大 token 数。默认 4096。")
            .addSlider(slider => {
                slider.setLimits(512, 8192, 256)
                    .setValue(this.plugin.settings.maxTokens)
                    .setDynamicTooltip()
                    .onChange(async (value) => {
                        this.plugin.settings.maxTokens = value;
                        await this.plugin.saveSettings();
                    });
            });

        // ---- 连续性检查 ----
        new Setting(containerEl)
            .setName("启用连续性检查")
            .setDesc("生成章节前自动比较上一章结尾与本章开头的连贯性。")
            .addToggle(toggle => {
                toggle.setValue(this.plugin.settings.enableContinuityCheck)
                    .onChange(async (value) => {
                        this.plugin.settings.enableContinuityCheck = value;
                        await this.plugin.saveSettings();
                    });
            });

        // ---- 场景多样性 ----
        new Setting(containerEl)
            .setName("场景多样性")
            .setDesc("控制连续章节之间的场景类型变化程度。0=保持相似，1=最大化差异。当前值: " + this.plugin.settings.sceneDiversity)
            .addSlider(slider => {
                slider.setLimits(0, 1.0, 0.1)
                    .setValue(this.plugin.settings.sceneDiversity)
                    .setDynamicTooltip()
                    .onChange(async (value) => {
                        this.plugin.settings.sceneDiversity = value;
                        await this.plugin.saveSettings();
                    });
            });

        // ---- 自动更新大纲 ----
        new Setting(containerEl)
            .setName("自动更新章节规划表")
            .setDesc("生成章节后自动将标题、伏笔、衔接说明同步到 Plot_Outline.md。")
            .addToggle(toggle => {
                toggle.setValue(this.plugin.settings.autoUpdateOutline)
                    .onChange(async (value) => {
                        this.plugin.settings.autoUpdateOutline = value;
                        await this.plugin.saveSettings();
                    });
            });

        // ---- 底部提示 ----
        containerEl.createEl("hr");
        const tipDiv = containerEl.createDiv({ cls: "setting-item-description" });
        tipDiv.createEl("p", {
            text: "提示：API Key 保存在插件本地数据中，请勿分享给他人。"
        });
    }

    /** 辅助：获取指定名称的 setting 索引 */
    private getSettingIndex(containerEl: HTMLElement, name: string): number {
        const items = containerEl.querySelectorAll(".setting-item");
        for (let i = 0; i < items.length; i++) {
            if (items[i].textContent?.includes(name)) return i;
        }
        return 0;
    }
}
