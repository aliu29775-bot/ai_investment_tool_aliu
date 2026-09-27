/* GitHub Actions 觸發憑證（可選）
 * 留空 = 免憑證模式：點「更新數據」按鈕會打開 GitHub Actions 頁面，
 *        手動點 Run workflow 觸發重建（無需在頁面嵌入任何憑證）。
 * 若填入僅授權 ai_investment_tool_aliu Actions 寫入的 fine-grained PAT，
 *        按鈕會直接 API 觸發並自動輪詢運行狀態。
 * 本文件由站長手動維護，build_site.py 不會覆蓋。 */
window.GH_TRIGGER_TOKEN = "";
