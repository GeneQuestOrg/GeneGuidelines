import type { Tool, RequestedTool, ImplementedTool } from "../types";

export const INITIAL_TOOLS: Tool[] = [
  { name: "list_available_tools", category: "System", auto: true, scope: "operational" },
  { name: "set_ai_summary", category: "System", auto: true, scope: "operational" },
  { name: "pubmed_search_articles", category: "Medical", auto: true, scope: "operational" },
  { name: "pubmed_fetch_article_details", category: "Medical", auto: true, scope: "operational" },
  { name: "pubmed_browser_search", category: "Medical", auto: true, scope: "operational" },
  { name: "update_ticket_status", category: "System", auto: true, scope: "operational" },
  { name: "request_missing_tool", category: "System", auto: true, scope: "operational" },
];

export const INITIAL_REQUESTED: RequestedTool[] = [];

export const INITIAL_IMPLEMENTED: ImplementedTool[] = [];
