/* GitHub Actions 觸發憑證（僅用於按鈕觸發 update-data 工作流）
 * 此 token 為 fine-grained PAT，僅授權 ai_investment_tool_aliu 的 Actions 寫入權限，
 * 無法改動倉庫內容，洩露風險僅限於觸發重建。
 * 本文件由站長手動維護，build_site.py 不會覆蓋。 */
window.GH_TRIGGER_TOKEN = "";
