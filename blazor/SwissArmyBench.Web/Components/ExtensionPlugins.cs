using SwissArmyBench.Web.Pages.Accounting;
using SwissArmyBench.Web.Pages.CodeApp;
using SwissArmyBench.Web.Pages.PowerBi;
using SwissArmyBench.Web.Pages.Scm;

namespace SwissArmyBench.Web.Components;

/// <summary>The extensions' plug-ins this front end draws, by the classic page's own ids, for the shared plug-in
/// registry: a page action's dialog (pageActions.ts registerPageAction), a rail page that loads when first opened
/// (lazyPages.ts registerLazyLayer), a Workbench tab kind (workbenchPage.ts) and a piece another page borrows
/// (scmPage.ts teamSignIn). Each is an ordinary component; PluginDialog draws the page actions today.</summary>
public static class ExtensionPlugins
{
    public static readonly IReadOnlyList<ExtensionPlugin> All =
    [
        // The ERD's Export to Power BI… (the Power BI extension's PAGE_ACTIONS), its context the ERD's tables.
        new("powerbi_export", "page_action", typeof(PowerBiExportDialog), "Export to Power BI…", null),
        // The same dialog opened on Use an existing report's pages (the Power BI page's panel).
        new("powerbi_report_pages", "page_action", typeof(PowerBiExportDialog), "Use an existing report's pages", "ReportFirst"),
        // The Power Apps extension's Code App page (lazyPages.ts CODE_APP_TYPE).
        new("codeapp", "rail_page", typeof(CodeAppPage), "Code App", "/codeapp"),
        // The Git extension's Source Control page (lazyPages.ts SCM_KEY; GET /app/areas names its area).
        new("scm", "rail_page", typeof(ScmPage), "Source Control", "/x-scm"),
        // The Accounting extension's Excel canvas (a Notebooks tab of kind workbook in the classic page).
        new("workbook", "tab_kind", typeof(WorkbookPage), "Workbook", "/workbook"),
        // Settings' Team box's sign-in step, borrowed from the Source Control page.
        new("teamSignIn", "piece", typeof(TeamSignIn), "Sign in to GitHub", null),
    ];

    public static ExtensionPlugin? Find(string id) => All.FirstOrDefault(p => p.Id == id);
}
