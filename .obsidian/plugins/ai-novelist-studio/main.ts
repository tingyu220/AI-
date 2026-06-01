// main.ts — 插件入口
// 注册 ItemView、Ribbon 图标、命令和设置 Tab

import { Plugin, WorkspaceLeaf } from "obsidian";
import { AINovelistView, VIEW_TYPE } from "./view";
import { AINovelistSettingTab, AINovelistSettings, DEFAULT_SETTINGS } from "./settings";

export default class AINovelistPlugin extends Plugin {
    settings: AINovelistSettings;

    async onload() {
        console.log("AI 小说工作室 插件加载中...");

        // 加载设置
        await this.loadSettings();

        // 注册自定义视图
        this.registerView(
            VIEW_TYPE,
            (leaf: WorkspaceLeaf) => new AINovelistView(leaf, this)
        );

        // 添加 Ribbon 图标（左侧边栏书本图标）
        this.addRibbonIcon("book", "AI 小说工作室", () => {
            this.activateView();
        });

        // 注册命令：打开视图
        this.addCommand({
            id: "open-novelist-view",
            name: "AI 小说工作室：打开视图",
            callback: () => {
                this.activateView();
            },
        });

        // 注册命令：一键写下一章
        this.addCommand({
            id: "one-click-write",
            name: "AI 小说工作室：一键写下一章",
            callback: async () => {
                // 先打开视图，再触发写作
                await this.activateView();
                // 延迟确保视图已加载
                setTimeout(async () => {
                    const view = this.getView();
                    if (view && view.currentNovel) {
                        // 使用默认参数触发写作
                        await view.executeOneClickWrite(
                            "",     // goal
                            false,  // withIdeas
                            true,   // updateCharacters
                            true,   // updateHooks
                            0.5     // sceneDiversity
                        );
                    }
                }, 500);
            },
        });

        // 添加设置 Tab
        this.addSettingTab(new AINovelistSettingTab(this.app, this));

        // 如果启动时已有活跃视图布局，自动打开
        if (this.app.workspace.layoutReady) {
            // 不自动打开，用户通过命令或 ribbon 主动触发
        }

        console.log("AI 小说工作室 插件已就绪");
    }

    onunload() {
        console.log("AI 小说工作室 插件已卸载");
        // 注销视图
        this.app.workspace.detachLeavesOfType(VIEW_TYPE);
    }

    /** 加载插件设置 */
    async loadSettings() {
        this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
    }

    /** 保存插件设置 */
    async saveSettings() {
        await this.saveData(this.settings);
    }

    /** 激活或聚焦视图 */
    async activateView() {
        const { workspace } = this.app;

        // 检查是否已存在视图
        let leaf: WorkspaceLeaf | null = workspace.getLeavesOfType(VIEW_TYPE)[0];

        if (!leaf) {
            // 在右侧边栏创建新视图
            leaf = workspace.getRightLeaf(false);
            if (leaf) {
                await leaf.setViewState({
                    type: VIEW_TYPE,
                    active: true,
                });
            }
        }

        // 聚焦对应视图
        if (leaf) {
            workspace.revealLeaf(leaf);
        }
    }

    /** 获取当前视图实例 */
    getView(): AINovelistView | null {
        const leaves = this.app.workspace.getLeavesOfType(VIEW_TYPE);
        if (leaves.length > 0 && leaves[0].view instanceof AINovelistView) {
            return leaves[0].view;
        }
        return null;
    }
}
