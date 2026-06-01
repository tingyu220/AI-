// api.ts — DeepSeek API 调用封装
// 负责与 DeepSeek Chat Completions API 交互，包含重试和错误处理

import { requestUrl } from "obsidian";

const DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions";

/**
 * 调用 DeepSeek Chat API 发送提示词并返回 AI 回复文本。
 * @param prompt - 用户提示词
 * @param apiKey - DeepSeek API Key
 * @param model - 模型名（默认 deepseek-chat）
 * @param temperature - 生成温度（0-2，默认 0.7）
 * @param maxTokens - 最大返回 token 数（默认 4096）
 * @param maxRetries - 最大重试次数（默认 2）
 * @returns AI 返回的文本内容，失败返回 null
 */
export async function callDeepSeekAPI(
    prompt: string,
    apiKey: string,
    model: string = "deepseek-chat",
    temperature: number = 0.7,
    maxTokens: number = 4096,
    maxRetries: number = 2
): Promise<string | null> {
    const headers = {
        "Authorization": `Bearer ${apiKey}`,
        "Content-Type": "application/json",
    };

    const body = {
        model: model,
        messages: [
            { role: "user", content: prompt }
        ],
        temperature: temperature,
        max_tokens: maxTokens,
    };

    let lastError: Error | null = null;

    for (let attempt = 0; attempt <= maxRetries; attempt++) {
        try {
            const response = await requestUrl({
                url: DEEPSEEK_API_URL,
                method: "POST",
                headers: headers,
                body: JSON.stringify(body),
                throw: true,
            });

            const data = response.json;

            if (!data || !data.choices || data.choices.length === 0) {
                throw new Error("API 返回的 choices 为空");
            }

            const content = data.choices[0]?.message?.content;
            if (!content) {
                throw new Error("API 返回内容为空");
            }

            return content as string;
        } catch (error) {
            lastError = error instanceof Error ? error : new Error(String(error));
            console.error(`DeepSeek API 调用失败 (第 ${attempt + 1} 次):`, lastError.message);

            if (attempt < maxRetries) {
                // 等待后重试（指数退避）
                await sleep(1000 * Math.pow(2, attempt));
            }
        }
    }

    console.error("DeepSeek API 调用最终失败:", lastError?.message);
    return null;
}

function sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
}
