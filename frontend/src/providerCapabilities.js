export function providerCapabilityLabels(provider) {
  if (!provider.tested) return { image: "待检测", pdf: "待检测" };
  const caps = provider.capabilities || {};
  const formats = { "image/png": "PNG", "image/jpeg": "JPEG" };
  return {
    image: caps.image_input
      ? `已验证（${(caps.supported_image_mime_types || []).map((mime) => formats[mime] || mime).join("、")}）`
      : caps.image_input === false
        ? "检测未通过"
        : "未检测（请重新检测）",
    pdf:
      caps.file_input && caps.supported_mime_types?.includes("application/pdf")
        ? "已验证"
        : provider.provider_type === "openai_compatible"
          ? "当前连接未接入"
          : caps.file_error
            ? "检测未通过"
            : "未验证",
  };
}

export const imageProbeErrors = {
  provider_rejected: "接口拒绝图片输入，本地图片格式可能不受支持",
  provider_timeout: "图片检测超时，请重试",
  provider_unavailable: "图片服务暂时不可用",
  invalid_api_key: "凭证无效或无图片访问权限",
  rate_limited: "图片检测受到限流，请稍后重试",
  invalid_structured_output: "图片识别结果未通过格式校验",
  invalid_provider_response: "图片接口未返回完整有效响应",
  probe_content_mismatch: "未正确读出测试图片中的随机标识",
};
