// view.ts — 主视图 (ItemView)，包含"写作"、"知识库"、"日志与统计"三个标签页
// 使用 Obsidian ItemView + 自定义 HTML/CSS 构建完整 UI

import {
    ItemView, WorkspaceLeaf, TFile, Notice, ButtonComponent,
    Setting, TextAreaComponent, TextComponent, ToggleComponent,
    SliderComponent
} from "obsidian";
import type AINovelistPlugin from "./main";
import {
    getNovelStructure, getNovelList, getChapterFiles,
    loadCharacters, loadHooks, readWorldview, saveWorldview,
    calculateStats, parseIdeas, readIdeas, readContext,
    buildAndSaveContext, parseChapterMetadataSection,
    extractChapterNumber, countChineseWords, parseFrontmatter,
    buildChapterPrompt, buildIdeasPrompt, parseGeneratedChapter,
    buildChapterFileContent, updateOutlineTitle, updateCharacterChapter,
    saveHooksTracker, CharacterInfo, HookInfo, NovelStats
} from "./fileUtils";
import { callDeepSeekAPI } from "./api";
import {
    IdeaPickerModal, CharacterEditModal, HookEditModal,
    ChapterMetadataModal, WorldviewEditModal
} from "./modals";

export const VIEW_TYPE = "ai-novelist-studio-view";

export class AINovelistView extends ItemView {
    plugin: AINovelistPlugin;
    // 日志
    logLines: string[] = [];
    // 当前选中小说
    currentNovel: string = "";

    constructor(leaf: WorkspaceLeaf, plugin: AINovelistPlugin) {
        super(leaf);
        this.plugin = plugin;
    }

    getViewType(): string {
        return VIEW_TYPE;
    }

    getDisplayText(): string {
        return "AI 小说工作室";
    }

    getIcon(): string {
        return "book";
    }

    // ============================================================
    //  View 渲染入口
    // ============================================================

    async onOpen() {
        const container = this.containerEl.children[1];
        container.empty();
        container.addClass("ai-ns-root");

        // === 顶部工具栏：小说选择 ===
        const toolbarEl = container.createDiv({ cls: "ai-ns-toolbar" });
        toolbarEl.createSpan({ text: "当前项目：", cls: "ai-ns-toolbar-label" });

        const novels = await getNovelList(this.plugin.app.vault, this.plugin.settings.novelsRootPath);
        console.log("[AI小说工作室] onOpen novelsRootPath: " + this.plugin.settings.novelsRootPath + ", found: " + novels.length + " novels");
        const selectEl = toolbarEl.createEl("select", { cls: "dropdown" });

        if (novels.length === 0) {
            selectEl.createEl("option", { text: "（未找到小说项目）", value: "" });
        }

        for (const novel of novels) {
            selectEl.createEl("option", { text: novel, value: novel });
        }

        // 设置当前选中项（只有目录列表非空且当前选中不在列表中时才切到第一项）
        if (novels.length > 0) {
            if (!this.currentNovel || !novels.includes(this.currentNovel)) {
                this.currentNovel = novels[0];
            }
        } else {
            this.currentNovel = "";
        }

        // 同步下拉框的显示值
        selectEl.value = this.currentNovel;

        // 下拉框切换事件：更新 currentNovel 并重新渲染标签页内容
        selectEl.addEventListener("change", async () => {
            this.currentNovel = selectEl.value;
            const tabContent = container.querySelector(".ai-ns-tab-content");
            if (tabContent) {
                await this.renderTabContent(tabContent as HTMLElement);
            }
        });

        // === 标签页导航 ===
        const tabBar = container.createDiv({ cls: "ai-ns-tab-bar" });
        const tabs = ["写作", "知识库", "日志与统计"];
        let currentTab = "写作";

        for (const tabName of tabs) {
            const tabBtn = tabBar.createDiv({ cls: "ai-ns-tab-btn", text: tabName });
            if (tabName === currentTab) tabBtn.addClass("is-active");

            tabBtn.addEventListener("click", async () => {
                tabBar.querySelectorAll(".ai-ns-tab-btn").forEach(b => b.removeClass("is-active"));
                tabBtn.addClass("is-active");
                currentTab = tabName;

                const tabContent = container.querySelector(".ai-ns-tab-content");
                if (tabContent) {
                    await this.renderTabContent(tabContent as HTMLElement);
                }
            });
        }

        // === 标签页内容区 ===
        const tabContent = container.createDiv({ cls: "ai-ns-tab-content" });
        await this.renderTabContent(tabContent);
    }

    // ============================================================
    //  标签页内容渲染分发
    // ============================================================

    async renderTabContent(container: HTMLElement) {
        container.style.display = "block";
        const activeBtn = this.containerEl.querySelector(".ai-ns-tab-btn.is-active");
        const tabName = activeBtn?.textContent?.trim() || "写作";

        container.empty();

        if (!this.currentNovel) {
            container.createEl("p", {
                text: "请先在顶部选择一部小说项目。",
                cls: "ai-ns-empty-hint"
            });
            return;
        }

        if (tabName === "写作") {
            await this.renderWritingTab(container);
        } else if (tabName === "知识库") {
            await this.renderKnowledgeTab(container);
        } else if (tabName === "日志与统计") {
            await this.renderStatsTab(container);
        }
    }

    // ============================================================
    //  标签页 1: 写作
    // ============================================================

    async renderWritingTab(container: HTMLElement) {
        const struct = getNovelStructure(
            this.plugin.settings.novelsRootPath, this.currentNovel
        );

        // ---- 信息卡片区 ----
        const cardsRow = container.createDiv({ cls: "ai-ns-card-row" });
        const stats = await calculateStats(this.plugin.app.vault, struct.chaptersDir);
        const hooks = await loadHooks(this.plugin.app.vault, struct.hooksDir);
        const characters = await loadCharacters(
            this.plugin.app.vault, struct.charactersDir, struct.chaptersDir
        );

        const unresolvedHooks = hooks.filter(h => !h.status.startsWith("resolved")).length;
        const activeChars = characters.filter(c => c.status === "活跃").length;

        this.createStatCard(cardsRow, "总章节数", String(stats.totalChapters));
        this.createStatCard(cardsRow, "待填坑", String(unresolvedHooks));
        this.createStatCard(cardsRow, "活跃人物", String(activeChars));
        this.createStatCard(cardsRow, "总字数", stats.totalWords.toLocaleString());

        // ---- 写作目标区 ----
        const goalSection = container.createDiv({ cls: "ai-ns-section" });
        goalSection.createEl("h4", { text: "写作目标" });

        const goalRow = goalSection.createDiv({ cls: "ai-ns-goal-row" });
        const goalTextarea = goalRow.createEl("textarea", {
            placeholder: "本章写作目标（可选）",
            cls: "ai-ns-goal-textarea",
        });
        goalTextarea.rows = 3;

        const ideaBtn = goalRow.createDiv({ cls: "ai-ns-idea-btn" });
        ideaBtn.createSpan({ text: "💡", cls: "ai-ns-idea-icon" });
        ideaBtn.createSpan({ text: "从灵感库选择" });
        ideaBtn.addEventListener("click", async () => {
            const ideasContent = await readIdeas(this.plugin.app.vault, struct.contextDir);
            const ideas = parseIdeas(ideasContent);
            new IdeaPickerModal(
                this.plugin.app, this.plugin, ideas,
                (title, content) => {
                    goalTextarea.value = `## ${title}\n\n${content}`;
                }
            ).open();
        });

        // ---- 高级选项（折叠） ----
        const advancedSection = container.createDiv({ cls: "ai-ns-section" });
        const advancedHeader = advancedSection.createDiv({ cls: "ai-ns-advanced-header" });
        advancedHeader.createSpan({ text: "▶ 高级选项", cls: "ai-ns-advanced-toggle" });
        const advancedBody = advancedSection.createDiv({ cls: "ai-ns-advanced-body", attr: { style: "display:none" } });

        // 复选框组
        let withIdeas = false;
        let updateCharacters = true;
        let updateHooks = true;
        let sceneDiversity = 0.5;

        const cb1 = new Setting(advancedBody)
            .setName("先生成灵感")
            .addToggle(toggle => toggle.setValue(false).onChange(v => withIdeas = v));
        const cb2 = new Setting(advancedBody)
            .setName("生成后自动更新人物笔记")
            .addToggle(toggle => toggle.setValue(true).onChange(v => updateCharacters = v));
        const cb3 = new Setting(advancedBody)
            .setName("生成后自动更新伏笔表")
            .addToggle(toggle => toggle.setValue(true).onChange(v => updateHooks = v));

        // 场景多样性滑块
        new Setting(advancedBody)
            .setName("场景多样性强度")
            .addSlider(slider => {
                slider.setLimits(0, 1, 0.1)
                    .setValue(0.5)
                    .setDynamicTooltip()
                    .onChange(v => sceneDiversity = v);
            });

        advancedHeader.addEventListener("click", () => {
            const visible = advancedBody.style.display !== "none";
            advancedBody.style.display = visible ? "none" : "block";
            const toggle = advancedHeader.querySelector(".ai-ns-advanced-toggle");
            if (toggle) toggle.textContent = visible ? "▶ 高级选项" : "▼ 高级选项";
        });

        // ---- 操作按钮区 ----
        const actionsDiv = container.createDiv({ cls: "ai-ns-actions" });

        const writeBtn = actionsDiv.createDiv({ cls: "ai-ns-btn ai-ns-btn-primary", text: "⚡ 一键写下一章" });
        const updateBtn = actionsDiv.createDiv({ cls: "ai-ns-btn", text: "✏ 单独更新当前章节" });
        const metaBtn = actionsDiv.createDiv({ cls: "ai-ns-btn", text: "📋 手动编辑章节元数据" });

        // 按钮事件
        writeBtn.addEventListener("click", async () => {
            await this.executeOneClickWrite(
                goalTextarea.value, withIdeas, updateCharacters, updateHooks, sceneDiversity
            );
        });

        updateBtn.addEventListener("click", async () => {
            await this.executeSingleUpdate();
        });

        metaBtn.addEventListener("click", async () => {
            await this.executeEditMetadata();
        });

        // ---- 实时进度日志区 ----
        const logSection = container.createDiv({ cls: "ai-ns-section" });
        logSection.createEl("h4", { text: "实时进度" });

        const logArea = logSection.createDiv({ cls: "ai-ns-log-area" });
        logArea.id = "ai-ns-log";
        // 初始日志行
        if (this.logLines.length === 0) {
            this.logLines = ["[等待开始]"];
        }
        logArea.createEl("pre", {
            text: this.logLines.join("\n"),
            cls: "ai-ns-log-text",
        });

        // 清空日志按钮
        const clearLogBtn = logSection.createDiv({ cls: "ai-ns-btn ai-ns-btn-small", text: "清空日志" });
        clearLogBtn.addEventListener("click", () => {
            this.logLines = [];
            const logPre = logArea.querySelector(".ai-ns-log-text");
            if (logPre) logPre.textContent = "";
        });
    }

    /** 创建统计卡片 */
    private createStatCard(parent: HTMLElement, label: string, value: string) {
        const card = parent.createDiv({ cls: "ai-ns-stat-card" });
        card.createDiv({ text: value, cls: "ai-ns-stat-value" });
        card.createDiv({ text: label, cls: "ai-ns-stat-label" });
    }

    // ============================================================
    //  核心业务：一键写下一章
    // ============================================================

    async executeOneClickWrite(
        goal: string, withIdeas: boolean, updateCharacters: boolean,
        updateHooks: boolean, sceneDiversity: number
    ) {
        if (!this.plugin.settings.apiKey) {
            new Notice("请先在设置中配置 DeepSeek API Key");
            return;
        }

        this.logLines = [];
        const log = (msg: string) => {
            const now = new Date().toLocaleTimeString("zh-CN", { hour12: false });
            this.logLines.push(`[${now}] ${msg}`);
            this.updateLogDisplay();
        };

        log("开始一键写作流程...");

        const struct = getNovelStructure(
            this.plugin.settings.novelsRootPath, this.currentNovel
        );

        try {
            // 步骤 1: 生成当前上下文
            log("步骤 1/6: 生成当前上下文...");
            const contextText = await buildAndSaveContext(
                this.plugin.app.vault, struct, this.currentNovel
            );
            log("  ✓ 上下文已生成");

            // 步骤 2: 可选生成灵感
            if (withIdeas) {
                log("步骤 2/6: 调用 AI 生成灵感...");
                await this.generateIdeas(struct, contextText);
                log("  ✓ 灵感已生成");
            } else {
                log("步骤 2/6: 跳过灵感生成");
            }

            // 步骤 3: 确定章节号和标题
            log("步骤 3/6: 确定章节信息...");
            const chapters = getChapterFiles(this.plugin.app.vault, struct.chaptersDir);
            const nextCh = chapters.length > 0
                ? (extractChapterNumber(chapters[chapters.length - 1].name) ?? 0) + 1
                : 1;

            let outlineTitle = await this.getOutlineTitleSafe(struct.plotDir, nextCh);
            let aiGenerateTitle = !outlineTitle;
            let title = outlineTitle || "未命名";

            log(`  章节号: 第${nextCh}章`);
            log(`  标题: ${title}${aiGenerateTitle ? " (AI 自拟)" : ""}`);

            // 步骤 4: 构造提示词并调用 API
            log("步骤 4/6: 构造提示词，调用 DeepSeek API...");
            const prevInfo = await this.getPreviousChapterInfo(chapters);
            const prompt = buildChapterPrompt(
                nextCh, title, prevInfo, contextText,
                goal || "自然推进剧情", sceneDiversity, aiGenerateTitle
            );
            log(`  提示词长度: ${prompt.length} 字符`);
            log("  等待 API 响应...");

            const result = await callDeepSeekAPI(
                prompt, this.plugin.settings.apiKey,
                this.plugin.settings.aiModel,
                this.plugin.settings.temperature,
                this.plugin.settings.maxTokens
            );

            if (!result) {
                log("  ✗ API 调用失败，请检查网络和 API Key");
                return;
            }
            log(`  ✓ API 返回 ${result.length} 字符`);

            // 步骤 5: 解析并保存章节
            log("步骤 5/6: 解析并保存章节文件...");
            const chapterParams = {
                rhythm: "中",
                conflict_type: "人与人",
                pov: "未知",
                time_gap: "",
                has_cliffhanger: true,
            };

            const parsed = parseGeneratedChapter(result, nextCh, title, chapterParams);
            const chapterContent = buildChapterFileContent(
                nextCh, parsed.title, parsed.body, parsed.metadata, chapterParams
            );

            const chapterPath = `${struct.chaptersDir}/第${nextCh}章 ${parsed.title}.md`;
            await this.plugin.app.vault.create(chapterPath, chapterContent);
            log(`  ✓ 已保存: 第${nextCh}章 ${parsed.title}`);

            // 更新大纲标题
            await updateOutlineTitle(
                this.plugin.app.vault, struct.plotDir, nextCh, parsed.title
            );
            log("  ✓ 已更新大纲标题");

            // 步骤 6: 可选更新人物和伏笔
            let step = 6;
            if (updateCharacters) {
                log(`步骤 ${step}/6: 更新人物笔记...`);
                await this.updateCharactersFromChapter(
                    struct, nextCh, parsed.newCharacters
                );
                log("  ✓ 人物笔记已更新");
                step++;
            }
            if (updateHooks) {
                log(`步骤 ${step}/6: 更新伏笔表...`);
                await this.updateHooksFromChapter(
                    struct, nextCh, parsed.newHooks, parsed.resolvedHooks
                );
                log("  ✓ 伏笔表已更新");
            }

            log("🎉 一键写作完成！");
        } catch (error) {
            const msg = error instanceof Error ? error.message : String(error);
            log(`✗ 错误: ${msg}`);
            console.error(error);
            new Notice(`写作出错: ${msg}`);
        }
    }

    /** 获取上一章信息 */
    private async getPreviousChapterInfo(chapters: TFile[]): Promise<string> {
        if (chapters.length === 0) return "（这是第一章，无前文）";
        const lastChapter = chapters[chapters.length - 1];
        const content = await this.plugin.app.vault.read(lastChapter);
        const [, body] = parseFrontmatter(content);
        const excerpt = body.replace(/^#.*\n/m, "").trim().substring(0, 500);
        return `第${extractChapterNumber(lastChapter.name)}章结尾：\n${excerpt}`;
    }

    /** 安全获取大纲标题 */
    private async getOutlineTitleSafe(plotDir: string, chNum: number): Promise<string | null> {
        const { getOutlineTitle } = await import("./fileUtils");
        return getOutlineTitle(this.plugin.app.vault, plotDir, chNum);
    }

    /** 生成灵感 */
    private async generateIdeas(struct: ReturnType<typeof getNovelStructure>, contextText: string) {
        const { getOutlineTitle } = await import("./fileUtils");
        // 读取大纲
        let plotText = "";
        const plotFile = this.plugin.app.vault.getAbstractFileByPath(
            `${struct.plotDir}/Plot_Outline.md`
        );
        if (plotFile instanceof TFile) {
            plotText = await this.plugin.app.vault.read(plotFile);
        }
        const prompt = buildIdeasPrompt(contextText, plotText);
        const result = await callDeepSeekAPI(
            prompt, this.plugin.settings.apiKey,
            this.plugin.settings.aiModel, 0.8, 2048
        );
        if (result) {
            const ideasPath = `${struct.contextDir}/Ideas.md`;
            const existing = this.plugin.app.vault.getAbstractFileByPath(ideasPath);
            const timestamp = new Date().toISOString().replace("T", " ").substring(0, 19);
            const newEntry = `\n\n---\n\n> 生成时间：${timestamp}\n\n${result}`;
            if (existing instanceof TFile) {
                const old = await this.plugin.app.vault.read(existing);
                await this.plugin.app.vault.modify(existing, old + newEntry);
            } else {
                await this.plugin.app.vault.create(
                    ideasPath, `# 下一章灵感\n\n> 生成时间：${timestamp}\n\n${result}`
                );
            }
        }
    }

    /** 更新人物出现章节 */
    private async updateCharactersFromChapter(
        struct: ReturnType<typeof getNovelStructure>,
        chapterNum: number,
        newCharacters: string[]
    ) {
        for (const charName of newCharacters) {
            const charPath = `${struct.charactersDir}/${charName}.md`;
            const file = this.plugin.app.vault.getAbstractFileByPath(charPath);

            if (file instanceof TFile) {
                await updateCharacterChapter(
                    this.plugin.app.vault, file, `第${chapterNum}章`
                );
            } else {
                const content = `---\nname: "${charName}"\nstatus: "活跃"\nfirst_appearance: "第${chapterNum}章"\n---\n\n# ${charName}\n\n## 出现章节\n\n- [[第${chapterNum}章]]\n`;
                await this.plugin.app.vault.create(charPath, content);
            }
        }
    }

    /** 更新伏笔表 */
    private async updateHooksFromChapter(
        struct: ReturnType<typeof getNovelStructure>,
        chapterNum: number,
        newHooks: string[],
        resolvedHooks: string[]
    ) {
        const existingHooks = await loadHooks(this.plugin.app.vault, struct.hooksDir);

        // 找到最大 ID 数字
        let maxId = 0;
        for (const h of existingHooks) {
            const match = h.id.match(/H-(\d+)/);
            if (match) maxId = Math.max(maxId, parseInt(match[1]));
        }

        // 添加新伏笔
        for (const desc of newHooks) {
            const exists = existingHooks.some(h => h.description.includes(desc) || desc.includes(h.description));
            if (!exists) {
                maxId++;
                existingHooks.push({
                    id: `H-${String(maxId).padStart(3, "0")}`,
                    description: desc,
                    plantedChapter: `第${chapterNum}章`,
                    planChapter: "",
                    status: "unresolved",
                });
            }
        }

        // 标记已填坑（模糊匹配）
        for (const desc of resolvedHooks) {
            for (const hook of existingHooks) {
                if (!hook.status.startsWith("resolved") &&
                    (hook.description.includes(desc) || desc.includes(hook.description))) {
                    hook.status = `resolved (第${chapterNum}章)`;
                }
            }
        }

        await saveHooksTracker(this.plugin.app.vault, struct.hooksDir, existingHooks);
    }

    // ============================================================
    //  单独更新当前章节
    // ============================================================

    async executeSingleUpdate() {
        const activeFile = this.plugin.app.workspace.getActiveFile();
        if (!activeFile || !extractChapterNumber(activeFile.name)) {
            new Notice("请先打开一个章节文件");
            return;
        }

        const struct = getNovelStructure(
            this.plugin.settings.novelsRootPath, this.currentNovel
        );

        const content = await this.plugin.app.vault.read(activeFile);
        const metaData = parseChapterMetadataSection(content);
        const chNum = extractChapterNumber(activeFile.name) ?? 0;

        this.addLog(`单独更新: ${activeFile.name}`);
        this.addLog(`  新人物: ${(metaData["新人物"] || []).join(", ") || "无"}`);
        this.addLog(`  新伏笔: ${(metaData["新伏笔/坑"] || []).join(", ") || "无"}`);
        this.addLog(`  已填坑: ${(metaData["已填旧坑"] || []).join(", ") || "无"}`);

        // 更新人物
        for (const charName of (metaData["新人物"] || [])) {
            await this.updateCharactersFromChapter(struct, chNum, [charName]);
        }

        // 更新伏笔
        await this.updateHooksFromChapter(
            struct, chNum,
            metaData["新伏笔/坑"] || [],
            metaData["已填旧坑"] || []
        );

        this.addLog("✓ 当前章节人物和伏笔已更新");
        new Notice("当前章节已更新");
    }

    // ============================================================
    //  手动编辑章节元数据
    // ============================================================

    async executeEditMetadata() {
        const activeFile = this.plugin.app.workspace.getActiveFile();
        if (!activeFile || !extractChapterNumber(activeFile.name)) {
            new Notice("请先打开一个章节文件");
            return;
        }

        const content = await this.plugin.app.vault.read(activeFile);
        new ChapterMetadataModal(
            this.plugin.app, this.plugin, activeFile, content,
            async (newContent: string) => {
                await this.plugin.app.vault.modify(activeFile, newContent);
                this.addLog(`已更新元数据: ${activeFile.name}`);
                new Notice("元数据已保存");
            }
        ).open();
    }

    // ============================================================
    //  标签页 2: 知识库
    // ============================================================

    async renderKnowledgeTab(container: HTMLElement) {
        const struct = getNovelStructure(
            this.plugin.settings.novelsRootPath, this.currentNovel
        );

        // 子标签栏
        const subTabBar = container.createDiv({ cls: "ai-ns-subtab-bar" });
        const subTabs = ["人物管理", "伏笔/坑管理", "世界观/设定管理"];
        let activeSubTab = "人物管理";

        for (const tabName of subTabs) {
            const btn = subTabBar.createDiv({ cls: "ai-ns-subtab-btn", text: tabName });
            if (tabName === activeSubTab) btn.addClass("is-active");

            btn.addEventListener("click", async () => {
                subTabBar.querySelectorAll(".ai-ns-subtab-btn").forEach(b => b.removeClass("is-active"));
                btn.addClass("is-active");
                activeSubTab = tabName;

                const subContent = container.querySelector(".ai-ns-subtab-content");
                if (subContent) {
                    await this.renderSubTabContent(subContent as HTMLElement, activeSubTab, struct);
                }
            });
        }

        const subContent = container.createDiv({ cls: "ai-ns-subtab-content" });
        await this.renderSubTabContent(subContent, activeSubTab, struct);
    }

    async renderSubTabContent(
        container: HTMLElement, tabName: string,
        struct: ReturnType<typeof getNovelStructure>
    ) {
        container.empty();

        if (tabName === "人物管理") {
            await this.renderCharacterManagement(container, struct);
        } else if (tabName === "伏笔/坑管理") {
            await this.renderHookManagement(container, struct);
        } else if (tabName === "世界观/设定管理") {
            await this.renderWorldviewManagement(container, struct);
        }
    }

    // ---- 人物管理 ----
    async renderCharacterManagement(
        container: HTMLElement,
        struct: ReturnType<typeof getNovelStructure>
    ) {
        // 搜索和新建
        const toolbar = container.createDiv({ cls: "ai-ns-kb-toolbar" });

        const searchInput = toolbar.createEl("input", {
            type: "text",
            placeholder: "搜索人物...",
            cls: "ai-ns-search-input",
        });

        const newBtn = toolbar.createDiv({ cls: "ai-ns-btn ai-ns-btn-primary", text: "+ 新建人物" });
        newBtn.addEventListener("click", () => {
            const charTemplate = `---\nname: ""\nstatus: "活跃"\n---\n\n# 新人物\n\n## 基本设定\n\n\n## 核心能力\n\n\n## 人际关系\n\n`;
            new CharacterEditModal(
                this.plugin.app, this.plugin, null, charTemplate,
                async (name, content) => {
                    await this.plugin.app.vault.create(
                        `${struct.charactersDir}/${name}.md`, content
                    );
                    this.addLog(`新建人物: ${name}`);
                    new Notice(`人物「${name}」已创建`);
                    await this.renderKnowledgeTab(container.parentElement!);
                }
            ).open();
        });

        // 表格
        const characters = await loadCharacters(
            this.plugin.app.vault, struct.charactersDir, struct.chaptersDir
        );

        const table = container.createEl("table", { cls: "ai-ns-table" });
        const thead = table.createEl("thead");
        const headerRow = thead.createEl("tr");
        ["姓名", "状态", "最后出现章节", "核心能力", "操作"].forEach(h => {
            headerRow.createEl("th", { text: h });
        });

        const tbody = table.createEl("tbody");
        const searchTerm = (searchInput.value || "").toLowerCase();

        const renderTable = (filtered: typeof characters) => {
            tbody.empty();
            for (const char of filtered) {
                const row = tbody.createEl("tr");
                row.createEl("td", { text: char.name });
                row.createEl("td", { text: char.status });
                row.createEl("td", { text: char.lastChapter || "-" });
                row.createEl("td", { text: char.coreAbility || "-" });

                const actionTd = row.createEl("td");

                const editBtn = actionTd.createEl("button", { text: "编辑", cls: "ai-ns-table-btn" });
                editBtn.addEventListener("click", async () => {
                    const content = char.file
                        ? await this.plugin.app.vault.read(char.file)
                        : "";
                    new CharacterEditModal(
                        this.plugin.app, this.plugin, char, content,
                        async (name, newContent) => {
                            await this.plugin.app.vault.create(
                                `${struct.charactersDir}/${name}.md`, newContent
                            );
                            this.addLog(`编辑人物: ${name}`);
                            new Notice(`人物「${name}」已保存`);
                            await this.renderKnowledgeTab(container.parentElement!);
                        }
                    ).open();
                });

                const viewBtn = actionTd.createEl("button", { text: "查看", cls: "ai-ns-table-btn" });
                viewBtn.addEventListener("click", () => {
                    if (char.file) {
                        this.plugin.app.workspace.getLeaf().openFile(char.file);
                    }
                });
            }
        };

        renderTable(characters);

        searchInput.addEventListener("input", () => {
            const term = searchInput.value.toLowerCase();
            const filtered = characters.filter(c =>
                c.name.toLowerCase().includes(term) ||
                c.status.toLowerCase().includes(term) ||
                c.coreAbility.toLowerCase().includes(term)
            );
            renderTable(filtered);
        });
    }

    // ---- 伏笔管理 ----
    async renderHookManagement(
        container: HTMLElement,
        struct: ReturnType<typeof getNovelStructure>
    ) {
        const toolbar = container.createDiv({ cls: "ai-ns-kb-toolbar" });
        toolbar.createEl("strong", { text: "伏笔追踪表" });

        const newBtn = toolbar.createDiv({ cls: "ai-ns-btn ai-ns-btn-primary", text: "+ 新建伏笔" });
        newBtn.addEventListener("click", async () => {
            const hooks = await loadHooks(this.plugin.app.vault, struct.hooksDir);
            let maxId = 0;
            for (const h of hooks) {
                const m = h.id.match(/H-(\d+)/);
                if (m) maxId = Math.max(maxId, parseInt(m[1]));
            }
            const newId = `H-${String(maxId + 1).padStart(3, "0")}`;
            new HookEditModal(
                this.plugin.app, this.plugin,
                { id: newId, description: "", plantedChapter: "", planChapter: "", status: "unresolved" },
                async (hook) => {
                    hooks.push({ ...hook });
                    await saveHooksTracker(this.plugin.app.vault, struct.hooksDir, hooks);
                    this.addLog(`新建伏笔: ${hook.id}`);
                    new Notice(`伏笔 ${hook.id} 已创建`);
                    await this.renderKnowledgeTab(container.parentElement!);
                }
            ).open();
        });

        const hooks = await loadHooks(this.plugin.app.vault, struct.hooksDir);

        const table = container.createEl("table", { cls: "ai-ns-table" });
        const thead = table.createEl("thead");
        const headerRow = thead.createEl("tr");
        ["ID", "描述", "埋坑章节", "状态", "操作"].forEach(h => {
            headerRow.createEl("th", { text: h });
        });

        const tbody = table.createEl("tbody");
        for (const hook of hooks) {
            const row = tbody.createEl("tr");
            row.createEl("td", { text: hook.id });
            row.createEl("td", { text: hook.description });
            row.createEl("td", { text: hook.plantedChapter || "-" });

            const statusTd = row.createEl("td");
            const statusSpan = statusTd.createSpan({ text: hook.status });
            if (hook.status.startsWith("resolved")) {
                statusSpan.addClass("ai-ns-status-resolved");
            } else {
                statusSpan.addClass("ai-ns-status-pending");
            }

            const actionTd = row.createEl("td");

            const editBtn = actionTd.createEl("button", { text: "编辑", cls: "ai-ns-table-btn" });
            editBtn.addEventListener("click", () => {
                new HookEditModal(
                    this.plugin.app, this.plugin, hook,
                    async (updatedHook) => {
                        const allHooks = await loadHooks(
                            this.plugin.app.vault, struct.hooksDir
                        );
                        const idx = allHooks.findIndex(h => h.id === hook.id);
                        if (idx >= 0) allHooks[idx] = updatedHook;
                        await saveHooksTracker(
                            this.plugin.app.vault, struct.hooksDir, allHooks
                        );
                        this.addLog(`编辑伏笔: ${hook.id}`);
                        new Notice(`伏笔 ${hook.id} 已更新`);
                        await this.renderKnowledgeTab(container.parentElement!);
                    }
                ).open();
            });

            if (!hook.status.startsWith("resolved")) {
                const resolveBtn = actionTd.createEl("button", {
                    text: "填坑", cls: "ai-ns-table-btn ai-ns-btn-resolve"
                });
                resolveBtn.addEventListener("click", async () => {
                    const allHooks = await loadHooks(
                        this.plugin.app.vault, struct.hooksDir
                    );
                    const idx = allHooks.findIndex(h => h.id === hook.id);
                    if (idx >= 0) {
                        const chapters = getChapterFiles(
                            this.plugin.app.vault, struct.chaptersDir
                        );
                        const latestCh = chapters.length > 0
                            ? extractChapterNumber(chapters[chapters.length - 1].name) ?? 0
                            : 0;
                        allHooks[idx].status = `resolved (第${latestCh}章)`;
                        await saveHooksTracker(
                            this.plugin.app.vault, struct.hooksDir, allHooks
                        );
                        this.addLog(`填坑: ${hook.id}`);
                        new Notice(`伏笔 ${hook.id} 已标记为已填`);
                        await this.renderKnowledgeTab(container.parentElement!);
                    }
                });
            }
        }
    }

    // ---- 世界观管理 ----
    async renderWorldviewManagement(
        container: HTMLElement,
        struct: ReturnType<typeof getNovelStructure>
    ) {
        const toolbar = container.createDiv({ cls: "ai-ns-kb-toolbar" });
        toolbar.createEl("strong", { text: "世界观设定" });

        const editBtn = toolbar.createDiv({ cls: "ai-ns-btn ai-ns-btn-primary", text: "编辑" });
        const content = await readWorldview(this.plugin.app.vault, struct.worldviewDir);

        // Markdown 预览区
        const previewDiv = container.createDiv({ cls: "ai-ns-preview" });
        previewDiv.createEl("div", {
            cls: "ai-ns-markdown-preview",
        });
        // 简单渲染 Markdown（标题、段落、列表）
        const previewHtml = this.simpleMarkdownRender(content);
        const previewContent = previewDiv.querySelector(".ai-ns-markdown-preview");
        if (previewContent) previewContent.innerHTML = previewHtml;

        editBtn.addEventListener("click", () => {
            new WorldviewEditModal(
                this.plugin.app, this.plugin, content,
                async (newContent: string) => {
                    await saveWorldview(
                        this.plugin.app.vault, struct.worldviewDir, newContent
                    );
                    this.addLog("世界观设定已更新");
                    new Notice("世界观设定已保存");
                    await this.renderKnowledgeTab(container.parentElement!);
                }
            ).open();
        });
    }

    /** 简易 Markdown → HTML 渲染 */
    private simpleMarkdownRender(md: string): string {
        let html = md;
        // 代码块
        html = html.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
        // 标题
        html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>');
        html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>');
        html = html.replace(/^# (.+)$/gm, '<h2>$1</h2>');
        // 粗体
        html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        // 斜体
        html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
        // 列表
        html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
        html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');
        // 段落
        html = html.replace(/^(?!<[hup])(.+)$/gm, '<p>$1</p>');
        // 清除多余换行
        html = html.replace(/\n{2,}/g, '\n');

        return html;
    }

    // ============================================================
    //  标签页 3: 日志与统计
    // ============================================================

    async renderStatsTab(container: HTMLElement) {
        const struct = getNovelStructure(
            this.plugin.settings.novelsRootPath, this.currentNovel
        );

        // ---- 统计卡片 ----
        const cardsRow = container.createDiv({ cls: "ai-ns-card-row" });
        const stats = await calculateStats(this.plugin.app.vault, struct.chaptersDir);

        this.createStatCard(cardsRow, "总章节数", String(stats.totalChapters));
        this.createStatCard(cardsRow, "总字数", stats.totalWords.toLocaleString());
        this.createStatCard(cardsRow, "平均长度", stats.avgLength.toLocaleString());
        this.createStatCard(cardsRow, "最长章节", stats.maxLength.toLocaleString());

        // ---- CSS 条形图 ----
        const chartSection = container.createDiv({ cls: "ai-ns-section" });
        chartSection.createEl("h4", { text: "最近5章字数统计" });

        const chartDiv = chartSection.createDiv({ cls: "ai-ns-bar-chart" });

        if (stats.recentWordCounts.length > 0) {
            const maxVal = Math.max(...stats.recentWordCounts, 1);
            const chapters = getChapterFiles(this.plugin.app.vault, struct.chaptersDir);
            const recentChapters = chapters.slice(-5);

            for (let i = 0; i < stats.recentWordCounts.length; i++) {
                const barRow = chartDiv.createDiv({ cls: "ai-ns-bar-row" });
                const label = recentChapters[i]
                    ? `第${extractChapterNumber(recentChapters[i].name)}章`
                    : `#${i + 1}`;
                barRow.createDiv({ text: label, cls: "ai-ns-bar-label" });

                const barOuter = barRow.createDiv({ cls: "ai-ns-bar-outer" });
                const barInner = barOuter.createDiv({ cls: "ai-ns-bar-inner" });
                const percent = (stats.recentWordCounts[i] / maxVal) * 100;
                barInner.style.width = `${Math.max(percent, 2)}%`;

                const valSpan = barRow.createDiv({
                    text: stats.recentWordCounts[i].toLocaleString(),
                    cls: "ai-ns-bar-value"
                });
            }
        } else {
            chartDiv.createEl("p", { text: "暂无章节数据", cls: "ai-ns-empty-hint" });
        }

        // ---- 运行日志历史 ----
        const logSection = container.createDiv({ cls: "ai-ns-section" });
        const logHeader = logSection.createDiv({ cls: "ai-ns-log-header" });
        logHeader.createEl("h4", { text: "运行日志历史" });

        const clearBtn = logHeader.createDiv({ cls: "ai-ns-btn ai-ns-btn-small", text: "清空日志" });
        clearBtn.addEventListener("click", () => {
            this.logLines = [];
            const logPre = container.querySelector(".ai-ns-log-text");
            if (logPre) logPre.textContent = "";
        });

        const logArea = logSection.createDiv({ cls: "ai-ns-log-area" });
        logArea.createEl("pre", {
            text: this.logLines.length > 0 ? this.logLines.join("\n") : "暂无运行日志",
            cls: "ai-ns-log-text",
        });
    }

    // ============================================================
    //  日志工具
    // ============================================================

    addLog(msg: string) {
        const now = new Date().toLocaleTimeString("zh-CN", { hour12: false });
        this.logLines.push(`[${now}] ${msg}`);
        this.updateLogDisplay();
    }

    updateLogDisplay() {
        const logPre = this.containerEl.querySelector(".ai-ns-log-text") as HTMLElement;
        if (logPre) {
            logPre.textContent = this.logLines.join("\n");
            // 自动滚动到底部
            const logArea = logPre.parentElement;
            if (logArea) logArea.scrollTop = logArea.scrollHeight;
        }
    }

    async onClose() {
        // 清理
    }
}
