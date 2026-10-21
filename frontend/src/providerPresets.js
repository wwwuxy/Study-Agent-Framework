// Endpoints and model IDs checked against the linked official documentation on 2026-10-19.
// Presets configure the existing chat adapter; capabilities still require a live connection test.
export const providerPresets = [
  {
    id: "deepseek",
    name: "DeepSeek",
    description: "DeepSeek 官方接口",
    baseUrl: "https://api.deepseek.com",
    model: "deepseek-flash",
    docsUrl: "https://api-docs.deepseek.com/",
  },
  {
    id: "qwen-cn",
    name: "Qwen · 北京",
    description: "阿里云百炼 · 北京 Key",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model: "qwen-plus",
    docsUrl: "https://help.aliyun.com/zh/model-studio/base-url",
  },
  {
    id: "qwen-intl",
    name: "Qwen · 新加坡",
    description: "阿里云百炼 · 新加坡 Key",
    baseUrl: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    model: "qwen-plus",
    docsUrl: "https://help.aliyun.com/zh/model-studio/base-url",
  },
  {
    id: "siliconflow",
    name: "硅基流动",
    description: "SiliconFlow 国内接口",
    baseUrl: "https://api.siliconflow.cn/v1",
    model: "Qwen/Qwen3.5-397B-A17B",
    docsUrl: "https://docs.siliconflow.cn/docs/userguide/quickstart",
  },
];
