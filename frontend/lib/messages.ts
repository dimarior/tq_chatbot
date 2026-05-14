export type Role = "user" | "assistant";

export function flattenContent(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .map((part) => {
      if (typeof part === "string") return part;
      if (part && typeof part === "object" && (part as any).type === "text") {
        return String((part as any).text ?? "");
      }
      return "";
    })
    .join("");
}
