// fileUtils.ts — Markdown 文件读写、Frontmatter 解析、人物/伏笔/章节更新
// 核心工具函数，被视图和 API 层使用

import { TFile, TFolder, Vault, normalizePath } from "obsidian";

// ============================================================
//  类型定义
// ============================================================

/** 小说目录结构信息 */
export interface NovelStructure {
    novelPath: string;
    worldviewDir: string;
    charactersDir: string;
    plotDir: string;
    hooksDir: string;
    chaptersDir: string;
    contextDir: string;
}

/** 人物信息 */
export interface CharacterInfo {
    name: string;
    status: string;
    lastChapter: string;
    coreAbility: string;
    file: TFile | null;
}

/** 伏笔信息 */
export interface HookInfo {
    id: string;
    description: string;
    plantedChapter: string;
    planChapter: string;
    status: string;
}

/** 章节元数据 */
export interface ChapterMetadata {
    title: string;
    chapterNum: number;
    wordCount: number;
    file: TFile;
    frontmatter: Record<string, any>;
    newCharacters: string[];
    newHooks: string[];
    resolvedHooks: string[];
}

/** 统计信息 */
export interface NovelStats {
    totalChapters: number;
    totalWords: number;
    avgLength: number;
    maxLength: number;
    recentWordCounts: number[];
}

// ============================================================
//  路径和目录工具
// ============================================================

/**
 * 获取小说的子文件夹路径结构
 */
export function getNovelStructure(novelsRoot: string, novelName: string): NovelStructure {
    const novelPath = normalizePath(`${novelsRoot}/${novelName}`);
    return {
        novelPath,
        worldviewDir: `${novelPath}/00_Worldview`,
        charactersDir: `${novelPath}/01_Characters`,
        plotDir: `${novelPath}/02_Plot`,
        hooksDir: `${novelPath}/03_Hooks`,
        chaptersDir: `${novelPath}/04_Chapters`,
        contextDir: `${novelPath}/05_Context`,
    };
}

/**
 * 从章节文件名提取编号：如 "第12章 旧方案点火.md" → 12
 */
export function extractChapterNumber(filename: string): number | null {
    const match = filename.match(/第(\d+)章/);
    return match ? parseInt(match[1], 10) : null;
}

/**
 * 获取小说目录下的所有小说名列表
 */
export async function getNovelList(vault: Vault, novelsRoot: string): Promise<string[]> {
    // 将输入的路径标准化：如果是绝对路径，提取 vault 相对路径；将反斜杠统一为斜杠
    let cleanPath = novelsRoot.replace(/\\/g, "/");

    // 常见情况：用户粘贴了绝对路径，尝试剥离 vault 前缀
    // vault.adapter 可以访问 basePath
    const vaultBasePath = (vault.adapter as any).basePath || "";
    if (vaultBasePath && cleanPath.toLowerCase().startsWith(vaultBasePath.toLowerCase())) {
        cleanPath = cleanPath.substring(vaultBasePath.length);
    }

    // 去掉首尾斜杠
    cleanPath = cleanPath.replace(/^\/+|\/+$/g, "");

    console.log("[AI小说工作室] 尝试目录: " + cleanPath + " (原始: " + novelsRoot + ", vaultBasePath: " + vaultBasePath + ")");

    const folder = vault.getAbstractFileByPath(cleanPath);
    if (!folder) {
        console.log("[AI小说工作室] 目录不存在: " + cleanPath);
        return [];
    }
    if (!(folder instanceof TFolder)) {
        console.log("[AI小说工作室] 路径不是文件夹: " + cleanPath);
        return [];
    }
    const novels = folder.children
        .filter((c): c is TFolder => c instanceof TFolder)
        .map(c => c.name);
    console.log("[AI小说工作室] 找到小说: " + JSON.stringify(novels));
    return novels;
}

// ============================================================
//  Frontmatter 解析
// ============================================================

/**
 * 解析 Markdown 文件的 YAML frontmatter
 * @returns [frontmatter对象, body字符串]
 */
export function parseFrontmatter(text: string): [Record<string, any> | null, string] {
    const match = text.match(/^---\s*\n([\s\S]*?)\n---\s*\n/);
    if (!match) return [null, text];

    const yamlText = match[1];
    const frontmatter = parseSimpleYaml(yamlText);
    const body = text.substring(match[0].length);
    return [frontmatter, body];
}

/**
 * 简易 YAML 解析器（不依赖 gray-matter，减少依赖）
 * 支持字符串、数字、列表、嵌套对象
 */
function parseSimpleYaml(yamlText: string): Record<string, any> {
    const result: Record<string, any> = {};
    const lines = yamlText.split("\n");
    let currentKey = "";
    let currentIndent = 0;

    for (const line of lines) {
        if (line.trim() === "" || line.trim().startsWith("#")) continue;

        const indent = line.search(/\S/);
        const trimmed = line.trim();

        // 键值对
        const kvMatch = trimmed.match(/^([\w_]+)\s*:\s*(.*)/);
        if (kvMatch) {
            const key = kvMatch[1];
            let value: any = kvMatch[2].trim();

            // 去除引号
            if ((value.startsWith('"') && value.endsWith('"')) ||
                (value.startsWith("'") && value.endsWith("'"))) {
                value = value.slice(1, -1);
            }
            // 数字
            if (/^-?\d+(\.\d+)?$/.test(value)) {
                value = Number(value);
            }
            // 布尔
            if (value === "true") value = true;
            if (value === "false") value = false;
            // 空
            if (value === "" || value === "null" || value === "~") value = null;

            result[key] = value;
            currentKey = key;
            currentIndent = indent;
        }
        // 列表项
        else if (trimmed.startsWith("- ") && currentKey && indent > currentIndent) {
            const item = trimmed.substring(2).trim();
            if (!Array.isArray(result[currentKey])) {
                result[currentKey] = [];
            }
            result[currentKey].push(item);
        }
    }

    return result;
}

/**
 * 序列化对象为 YAML frontmatter 文本
 */
export function serializeFrontmatter(fm: Record<string, any>): string {
    const lines: string[] = ["---"];

    for (const [key, value] of Object.entries(fm)) {
        if (value === null || value === undefined) {
            lines.push(`${key}:`);
        } else if (typeof value === "boolean") {
            lines.push(`${key}: ${value}`);
        } else if (typeof value === "number") {
            lines.push(`${key}: ${value}`);
        } else if (Array.isArray(value)) {
            if (value.length === 0) {
                lines.push(`${key}: []`);
            } else {
                lines.push(`${key}:`);
                for (const item of value) {
                    lines.push(`  - "${item}"`);
                }
            }
        } else {
            const str = String(value);
            lines.push(`${key}: "${str}"`);
        }
    }

    lines.push("---\n");
    return lines.join("\n");
}

// ============================================================
//  章节文件操作
// ============================================================

/**
 * 获取指定目录下所有章节文件，按章号排序
 */
export function getChapterFiles(vault: Vault, chaptersDir: string): TFile[] {
    const folder = vault.getAbstractFileByPath(chaptersDir);
    if (!folder || !(folder instanceof TFolder)) return [];

    return folder.children
        .filter((f): f is TFile => f instanceof TFile && f.name.endsWith(".md"))
        .filter(f => extractChapterNumber(f.name) !== null)
        .sort((a, b) => {
            const na = extractChapterNumber(a.name) ?? 0;
            const nb = extractChapterNumber(b.name) ?? 0;
            return na - nb;
        });
}

/**
 * 读取章节文件的完整内容
 */
export async function readChapterContent(vault: Vault, file: TFile): Promise<string> {
    return await vault.read(file);
}

/**
 * 计算文本字数（中文字符 + 英文单词）
 */
export function countChineseWords(text: string): number {
    // 去除 frontmatter
    const [, body] = parseFrontmatter(text);
    // 去除元数据区块
    const mainBody = body.split("## 本章元数据")[0] || body;
    // 去除标题
    const clean = mainBody.replace(/^#\s+.*$/gm, "").replace(/^##\s+.*$/gm, "");
    // 中文字符数
    const chineseChars = (clean.match(/[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]/g) || []).length;
    // 英文单词数（粗略估算）
    const englishWords = clean.replace(/[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]/g, " ")
        .split(/\s+/)
        .filter(w => w.length > 0).length;
    return chineseChars + englishWords;
}

/**
 * 从章节文件中解析元数据区块
 */
export function parseChapterMetadataSection(text: string): Record<string, string[]> {
    const result: Record<string, string[]> = {};
    const metaMatch = text.match(/\n##\s+本章元数据\s*\n([\s\S]*?)(?=\n#|$)/);
    if (!metaMatch) return result;

    const metaText = metaMatch[1];
    let currentKey: string | null = null;

    for (const line of metaText.split("\n")) {
        const h3Match = line.trim().match(/^###\s+(.+)/);
        if (h3Match) {
            currentKey = h3Match[1].trim();
            if (!result[currentKey]) result[currentKey] = [];
        } else if (currentKey && line.trim().startsWith("- ")) {
            const item = line.trim().substring(2).trim();
            if (item && item !== "无" && item !== "None" && item !== "未识别") {
                result[currentKey].push(item);
            }
        } else if (line.trim().startsWith("## ")) {
            break;
        }
    }

    return result;
}

// ============================================================
//  人物文件操作
// ============================================================

/**
 * 读取指定小说目录下的所有人物信息
 */
export async function loadCharacters(
    vault: Vault,
    charactersDir: string,
    chaptersDir: string
): Promise<CharacterInfo[]> {
    const folder = vault.getAbstractFileByPath(charactersDir);
    if (!folder || !(folder instanceof TFolder)) return [];

    const chapterFiles = getChapterFiles(vault, chaptersDir);
    const maxChapter = chapterFiles.length > 0
        ? extractChapterNumber(chapterFiles[chapterFiles.length - 1].name) ?? 0
        : 0;

    const characters: CharacterInfo[] = [];

    for (const child of folder.children) {
        if (!(child instanceof TFile) || !child.name.endsWith(".md")) continue;

        const name = child.name.replace(/\.md$/, "");
        const content = await vault.read(child);
        const [fm] = parseFrontmatter(content);

        // 从正文提取状态和最后出现章节
        let status = "活跃";
        let lastChapter = "";

        // 查找 "出现章节" 列表
        const chapterSection = content.match(/##\s+出现章节\s*\n([\s\S]*?)(?=\n##|$)/);
        if (chapterSection) {
            const chLines = chapterSection[1].trim().split("\n");
            const chNums = chLines
                .map(l => extractChapterNumber(l))
                .filter((n): n is number => n !== null);

            if (chNums.length > 0) {
                lastChapter = `第${Math.max(...chNums)}章`;
                if (Math.max(...chNums) < maxChapter - 2) {
                    status = "暂离";
                } else if (Math.max(...chNums) <= maxChapter - 5) {
                    status = "退场";
                }
            }
        }

        // 提取核心能力
        let coreAbility = "";
        const abilitySection = content.match(/##\s+(?:核心能力|能力|技能)\s*\n([\s\S]*?)(?=\n##|$)/);
        if (abilitySection) {
            const abilityText = abilitySection[1].trim();
            const firstLine = abilityText.split("\n")[0].replace(/^[-*]\s*/, "");
            coreAbility = firstLine.substring(0, 50);
        }

        characters.push({
            name,
            status: fm?.status || status,
            lastChapter: fm?.last_appearance || lastChapter,
            coreAbility: coreAbility || fm?.ability || "",
            file: child,
        });
    }

    return characters;
}

/**
 * 保存人物信息（创建/更新人物Markdown文件）
 */
export async function saveCharacter(
    vault: Vault,
    charactersDir: string,
    name: string,
    content: string
): Promise<void> {
    const path = normalizePath(`${charactersDir}/${name}.md`);
    const existing = vault.getAbstractFileByPath(path);

    if (existing instanceof TFile) {
        await vault.modify(existing, content);
    } else {
        await vault.create(path, content);
    }
}

/**
 * 更新人物的出现章节列表
 */
export async function updateCharacterChapter(
    vault: Vault,
    charFile: TFile,
    chapterLabel: string
): Promise<void> {
    let content = await vault.read(charFile);
    const sectionMatch = content.match(/##\s+出现章节\s*\n([\s\S]*?)(?=\n##|$)/);

    if (sectionMatch) {
        const existing = sectionMatch[1].trim();
        const lines = existing.split("\n").map(l => l.trim()).filter(l => l);
        const newLine = `- [[${chapterLabel}]]`;

        if (!lines.includes(newLine) && !lines.some(l => l.includes(chapterLabel))) {
            lines.push(newLine);
            // 排序
            lines.sort((a, b) => {
                const na = extractChapterNumber(a) ?? 0;
                const nb = extractChapterNumber(b) ?? 0;
                return na - nb;
            });
            const newSection = `## 出现章节\n\n${lines.join("\n")}`;
            content = content.replace(sectionMatch[0], newSection);
            await vault.modify(charFile, content);
        }
    } else {
        // 无出现章节section，追加
        const newSection = `\n\n## 出现章节\n\n- [[${chapterLabel}]]\n`;
        await vault.modify(charFile, content + newSection);
    }
}

// ============================================================
//  伏笔文件操作
// ============================================================

/**
 * 从 Hooks_Tracker.md 解析伏笔表格
 */
export async function loadHooks(vault: Vault, hooksDir: string): Promise<HookInfo[]> {
    const trackerPath = normalizePath(`${hooksDir}/Hooks_Tracker.md`);
    const file = vault.getAbstractFileByPath(trackerPath);
    if (!(file instanceof TFile)) return [];

    const content = await vault.read(file);
    const hooks: HookInfo[] = [];

    for (const line of content.split("\n")) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("| H-")) continue;

        const cols = trimmed.replace(/^\||\|$/g, "").split("|").map(c => c.trim());
        if (cols.length < 5) continue;

        hooks.push({
            id: cols[0],
            description: cols[1] || "",
            plantedChapter: cols[2] || "",
            planChapter: cols[3] || "",
            status: cols[4] || "unresolved",
        });
    }

    return hooks;
}

/**
 * 写入伏笔追踪表
 */
export async function saveHooksTracker(
    vault: Vault,
    hooksDir: string,
    hooks: HookInfo[]
): Promise<void> {
    const trackerPath = normalizePath(`${hooksDir}/Hooks_Tracker.md`);

    const lines: string[] = [
        "---",
        'type: "hooks_tracker"',
        `updated: "${new Date().toISOString().split("T")[0]}"`,
        "---",
        "",
        "# 伏笔追踪表",
        "",
        "| ID | 描述 | 埋坑章节 | 计划填坑 | 状态 |",
        "|----|------|----------|----------|------|",
    ];

    for (const hook of hooks) {
        lines.push(
            `| ${hook.id} | ${hook.description} | ${hook.plantedChapter} | ${hook.planChapter} | ${hook.status} |`
        );
    }

    lines.push("");

    const file = vault.getAbstractFileByPath(trackerPath);
    if (file instanceof TFile) {
        await vault.modify(file, lines.join("\n"));
    } else {
        await vault.create(trackerPath, lines.join("\n"));
    }
}

// ============================================================
//  世界观文件操作
// ============================================================

/**
 * 读取世界观主文件
 */
export async function readWorldview(vault: Vault, worldviewDir: string): Promise<string> {
    const path = normalizePath(`${worldviewDir}/Main_Worldview.md`);
    const file = vault.getAbstractFileByPath(path);
    if (file instanceof TFile) {
        return await vault.read(file);
    }
    return "# 世界观设定\n\n（尚未创建世界观设定文件）\n";
}

/**
 * 保存世界观文件
 */
export async function saveWorldview(vault: Vault, worldviewDir: string, content: string): Promise<void> {
    const path = normalizePath(`${worldviewDir}/Main_Worldview.md`);
    const file = vault.getAbstractFileByPath(path);
    if (file instanceof TFile) {
        await vault.modify(file, content);
    } else {
        await vault.create(path, content);
    }
}

// ============================================================
//  Plot_Outline 操作
// ============================================================

/**
 * 从 Plot_Outline.md 读取指定章节的标题
 */
export async function getOutlineTitle(
    vault: Vault,
    plotDir: string,
    chapterNum: number
): Promise<string | null> {
    const path = normalizePath(`${plotDir}/Plot_Outline.md`);
    const file = vault.getAbstractFileByPath(path);
    if (!(file instanceof TFile)) return null;

    const content = await vault.read(file);

    // 表格格式
    for (const line of content.split("\n")) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("|")) continue;

        const cols = trimmed.replace(/^\||\|$/g, "").split("|").map(c => c.trim());
        if (cols.length < 2) continue;

        // 第二个字段通常是章节号
        for (const col of cols) {
            if (parseInt(col) === chapterNum && cols.length >= 3) {
                const title = cols[2]; // 标题通常在第三列
                if (title && title !== "标题" && title !== "---" && title !== "未命名") {
                    return title;
                }
            }
        }
    }

    // 列表格式：- 第X章：标题
    for (const line of content.split("\n")) {
        const match = line.trim().match(new RegExp(`-\\s*第${chapterNum}章[：:]\\s*(.+)`));
        if (match) return match[1].trim();
    }

    return null;
}

/**
 * 更新 Plot_Outline.md 中指定章节的标题、伏笔和衔接说明
 */
export async function updateOutlineTitle(
    vault: Vault,
    plotDir: string,
    chapterNum: number,
    title: string,
    fullLine?: string,
    hooksLines?: string,
    continuityText?: string
): Promise<void> {
    const targetPath = normalizePath(plotDir + "/Plot_Outline.md");
    const file = vault.getAbstractFileByPath(targetPath);
    if (!(file instanceof TFile)) return;

    let content = await vault.read(file);
    let fileLines = content.split("\n");
    let updated = false;

    for (let i = 0; i < fileLines.length; i++) {
        const trimmed = fileLines[i].trim();
        if (!trimmed.startsWith("|")) continue;
        if (/^\|[\s\-:|]+\|$/.test(trimmed)) continue;
        const cols = trimmed.replace(/^\||\|$/g, "").split("|").map((c: string) => c.trim());
        if (cols.length < 2) continue;
        const chCol = parseInt(cols[1]);
        if (chCol === chapterNum) {
            if (fullLine) { fileLines[i] = fullLine; }
            else if (cols.length >= 3) { cols[2] = title; fileLines[i] = "| " + cols.join(" | ") + " |"; }
            updated = true;
            break;
        }
    }
    if (!updated) {
        const newLine = fullLine || ("| 1 | " + chapterNum + " | " + title + " | 待写 | 待定 | 无 | 待定 | 待定 |");
        fileLines.push(newLine);
    }

    if (hooksLines && hooksLines.trim() && hooksLines.trim() !== "无") {
        let hooksIdx = -1;
        for (let i = 0; i < fileLines.length; i++) {
            if (/^##\s+伏笔填坑规划/.test(fileLines[i].trim())) { hooksIdx = i; break; }
        }
        if (hooksIdx >= 0) {
            const newRows = hooksLines.split("\n").filter((l: string) => l.trim().startsWith("|") && !l.includes("伏笔") && !l.includes("---"));
            for (const row of newRows) { fileLines.splice(hooksIdx + 2, 0, row); hooksIdx++; }
        }
    }

    if (continuityText && continuityText.trim()) {
        let contIdx = -1;
        for (let i = 0; i < fileLines.length; i++) {
            if (/^##\s+已写章节与后续衔接说明/.test(fileLines[i].trim())) { contIdx = i; break; }
        }
        if (contIdx >= 0) {
            fileLines.push("");
            fileLines.push(continuityText.trim());
        } else {
            fileLines.push("");
            fileLines.push("## 已写章节与后续衔接说明");
            fileLines.push("");
            fileLines.push(continuityText.trim());
        }
    }

    while (fileLines.length > 0 && fileLines[fileLines.length - 1].trim() === "") { fileLines.pop(); }
    fileLines.push("");
    await vault.modify(file, fileLines.join("\n"));
}


export async function readIdeas(vault: Vault, contextDir: string): Promise<string> {
    const path = normalizePath(`${contextDir}/Ideas.md`);
    const file = vault.getAbstractFileByPath(path);
    if (file instanceof TFile) {
        return await vault.read(file);
    }
    return "# 灵感列表\n\n暂无灵感记录。\n";
}

/**
 * 从 Ideas.md 文本中解析灵感条目
 */
export function parseIdeas(text: string): { title: string; content: string }[] {
    const ideas: { title: string; content: string }[] = [];
    const sections = text.split(/^###\s+/m);

    for (const section of sections) {
        if (!section.trim()) continue;
        const lines = section.split("\n");
        const title = lines[0].trim();
        const content = lines.slice(1).join("\n").trim();
        if (title) {
            ideas.push({ title, content });
        }
    }

    return ideas;
}

// ============================================================
//  上下文操作
// ============================================================

/**
 * 读取当前上下文文件
 */
export async function readContext(vault: Vault, contextDir: string): Promise<string> {
    const path = normalizePath(`${contextDir}/Current_Context.md`);
    const file = vault.getAbstractFileByPath(path);
    if (file instanceof TFile) {
        return await vault.read(file);
    }
    return "";
}

/**
 * 生成并保存当前写作上下文
 */
export async function buildAndSaveContext(
    vault: Vault,
    structure: NovelStructure,
    novelName: string
): Promise<string> {
    const chapters = getChapterFiles(vault, structure.chaptersDir);
    const now = new Date().toISOString().split("T")[0];

    const lines: string[] = [
        "---",
        "type: context",
        `novel: "${novelName}"`,
        'title: "当前写作上下文"',
        `last_chapter: "${chapters.length > 0 ? `第${extractChapterNumber(chapters[chapters.length - 1].name)}章` : ''}"`,
        'next_chapter: ""',
        `created: ${now}`,
        `updated: ${now}`,
        "---",
        "",
        "# 当前写作上下文",
        "",
    ];

    // 汇总各章节内容
    const summaries: string[] = [];
    for (let i = Math.max(0, chapters.length - 3); i < chapters.length; i++) {
        const ch = chapters[i];
        const content = await vault.read(ch);
        const [, body] = parseFrontmatter(content);
        const firstPara = body.replace(/^#.*\n/, "").trim().substring(0, 200);
        summaries.push(`- 第${extractChapterNumber(ch.name)}章：${firstPara}...`);
    }

    lines.push("## 最近剧情摘要", "");
    lines.push(...summaries, "");

    // 世界观摘要
    const worldview = await readWorldview(vault, structure.worldviewDir);
    const worldviewShort = worldview
        .replace(/^---[\s\S]*?---\n/, "")
        .replace(/^#.*\n/gm, "")
        .trim()
        .substring(0, 500);
    lines.push("## 世界观核心规则", "", worldviewShort || "（暂无）", "");

    // 写作目标
    lines.push("## 本章写作目标（请用户填写）", "", "（在此填写本章的写作目标和关键情节要点）", "");

    const contextPath = normalizePath(`${structure.contextDir}/Current_Context.md`);
    const existing = vault.getAbstractFileByPath(contextPath);

    const content = lines.join("\n");
    if (existing instanceof TFile) {
        await vault.modify(existing, content);
    } else {
        await vault.create(contextPath, content);
    }

    return content;
}

// ============================================================
//  统计计算
// ============================================================

/**
 * 计算小说统计数据
 */
export async function calculateStats(vault: Vault, chaptersDir: string): Promise<NovelStats> {
    const chapters = getChapterFiles(vault, chaptersDir);
    const wordCounts: number[] = [];
    let totalChars = 0;
    let maxChars = 0;

    for (const ch of chapters) {
        const content = await vault.read(ch);
        const chars = countChineseWords(content);
        wordCounts.push(chars);
        totalChars += chars;
        if (chars > maxChars) maxChars = chars;
    }

    const recentCounts = wordCounts.slice(-5);

    return {
        totalChapters: chapters.length,
        totalWords: totalChars,
        avgLength: chapters.length > 0 ? Math.round(totalChars / chapters.length) : 0,
        maxLength: maxChars,
        recentWordCounts: recentCounts,
    };
}

// ============================================================
//  构建提示词
// ============================================================

/**
 * 构建章节生成提示词
 */
export function buildChapterPrompt(
    chapterNum: number,
    title: string,
    prevChapterInfo: string,
    contextText: string,
    goal: string,
    sceneDiversity: number,
    aiGenerateTitle: boolean
): string {
    const titleInstruction = aiGenerateTitle
        ? `请根据剧情发展自拟一个引人入胜的章节标题。`
        : `本章标题为《${title}》。`;

    return `你是一位专业的小说作家，正在创作一部长篇小说的下一章。

## 写作规则
1. 保持与前文的连贯性和一致性
2. 场景多样性强度：${sceneDiversity.toFixed(1)}（0=完全线性叙事，1=最大限度场景切换）
3. 保持人物性格和行为模式的一致性
4. 自然推进剧情，避免节奏过快或过慢

## 当前写作目标
${goal}

## 上一章信息
${prevChapterInfo}

## 当前故事上下文
${contextText}

## 章节信息
- 章节号：第${chapterNum}章
- ${titleInstruction}

请直接输出完整的章节正文。

输出格式要求：
1. 章节标题使用 # 第${chapterNum}章 [标题]
2. 正文内容以自然段落呈现
3. 在末尾添加 ## 本章元数据 区块，包含：
   - ### 新人物：（列出本章首次出现的角色名，无则填"无"）
   - ### 新伏笔/坑：（列出本章埋下的新悬念，无则填"无"）
   - ### 已填旧坑：（列出本章回收的已有伏笔，无则填"无"）
   - ### 场景类型：（对话/战斗/探索/情感/日常/悬疑/高潮/铺垫/回忆/群像）
   - ### 情绪基调：（如 紧张、温馨、悲伤、激昂 等）

请严格遵循以上格式输出，不要添加额外解释。`;
}

/**
 * 构建灵感生成提示词
 */
export function buildIdeasPrompt(contextText: string, plotText: string): string {
    const ctxSnippet = contextText.slice(-8000);
    const plotSnippet = plotText.slice(-8000);

    return `你是一个专业的小说策划专家。以下是当前故事状态和章节规划表。

---

## 当前故事状态

${ctxSnippet}

---

## 章节规划表

${plotSnippet}

---

请根据以上信息，为下一章生成 3 个不同的剧情灵感。每个灵感格式如下：

### 灵感1：[标题]
- **核心冲突**：（一句话描述本章的核心矛盾或冲突）
- **视角人物**：（建议从哪个角色的视角来写）
- **可填伏笔**：（本章可以回收哪些已有伏笔）
- **新悬念**：（本章可以埋下什么新的悬念）

### 灵感2：[标题]
- **核心冲突**：...
- **视角人物**：...
- **可填伏笔**：...
- **新悬念**：...

### 灵感3：[标题]
- **核心冲突**：...
- **视角人物**：...
- **可填伏笔**：...
- **新悬念**：...

请直接输出灵感，不要添加额外解释或开场白。`;
}

// ============================================================
//  解析 AI 返回的章节内容
// ============================================================

/**
 * 从 AI 生成的文本中提取章节正文和元数据
 */
export function parseGeneratedChapter(
    generatedText: string,
    chapterNum: number,
    defaultTitle: string,
    params: {
        rhythm: string;
        conflict_type: string;
        pov: string;
        time_gap: string;
        has_cliffhanger: boolean;
    }
): {
    title: string;
    body: string;
    metadata: string;
    newCharacters: string[];
    newHooks: string[];
    resolvedHooks: string[];
} {
    let text = generatedText.trim();

    // 提取标题
    let title = defaultTitle;
    const titleMatch = text.match(/^#\s+第\d+章\s+(.+)/m);
    if (titleMatch) {
        title = titleMatch[1].trim();
    } else {
        // 尝试提取第一行作为标题
        const firstLine = text.split("\n")[0].replace(/^#+\s*/, "");
        if (firstLine && firstLine.length < 50) {
            title = firstLine;
        }
    }

    // 分离正文和元数据
    const metaSplit = text.split(/##\s+本章元数据/);
    let body = (metaSplit[0] || text)
        .replace(/^#\s+第\d+章.+\n?/m, "")
        .trim();
    const metadataSection = metaSplit.length > 1 ? metaSplit.slice(1).join("## 本章元数据") : "";

    // 解析元数据
    const metadata: Record<string, string[]> = {};
    if (metadataSection) {
        let currentKey = "";
        for (const line of metadataSection.split("\n")) {
            const h3Match = line.trim().match(/^###\s+(.+)/);
            if (h3Match) {
                currentKey = h3Match[1].trim();
                if (!metadata[currentKey]) metadata[currentKey] = [];
            } else if (currentKey && line.trim().startsWith("- ")) {
                const item = line.trim().substring(2).trim();
                if (item && item !== "无") {
                    metadata[currentKey].push(item);
                }
            }
        }
    }

    // 构建完整的元数据区块
    const metadataLines: string[] = [];
    metadataLines.push(`### 新人物`);
    for (const c of (metadata["新人物"] || [])) metadataLines.push(`- ${c}`);
    if ((metadata["新人物"] || []).length === 0) metadataLines.push("- 无");

    metadataLines.push(`### 新伏笔/坑`);
    for (const h of (metadata["新伏笔/坑"] || [])) metadataLines.push(`- ${h}`);
    if ((metadata["新伏笔/坑"] || []).length === 0) metadataLines.push("- 无");

    metadataLines.push(`### 已填旧坑`);
    for (const r of (metadata["已填旧坑"] || [])) metadataLines.push(`- ${r}`);
    if ((metadata["已填旧坑"] || []).length === 0) metadataLines.push("- 无");

    metadataLines.push(`### 场景类型`);
    metadataLines.push(`- ${metadata["场景类型"]?.[0] || "未识别"}`);

    metadataLines.push(`### 情绪基调`);
    metadataLines.push(`- ${metadata["情绪基调"]?.[0] || "未识别"}`);

    return {
        title,
        body,
        metadata: metadataLines.join("\n"),
        newCharacters: metadata["新人物"] || [],
        newHooks: metadata["新伏笔/坑"] || [],
        resolvedHooks: metadata["已填旧坑"] || [],
    };
}

/**
 * 将解析后的章节内容组装成完整的 Markdown
 */
export function buildChapterFileContent(
    chapterNum: number,
    title: string,
    body: string,
    metadataText: string,
    params: {
        rhythm: string;
        conflict_type: string;
        pov: string;
        time_gap: string;
        has_cliffhanger: boolean;
    }
): string {
    const lines: string[] = [
        "---",
        `chapter: ${chapterNum}`,
        `title: "${title}"`,
        `rhythm: "${params.rhythm}"`,
        `conflict_type: "${params.conflict_type}"`,
        `pov: "${params.pov}"`,
        `time_gap: "${params.time_gap}"`,
        `has_cliffhanger: ${params.has_cliffhanger}`,
        `status: "draft"`,
        `word_count: ${countChineseWords(body)}`,
        `created: "${new Date().toISOString().split("T")[0]}"`,
        "---",
        "",
        `# 第${chapterNum}章 ${title}`,
        "",
        body,
        "",
        "## 本章元数据",
        "",
        metadataText,
    ];

    return lines.join("\n");
}
