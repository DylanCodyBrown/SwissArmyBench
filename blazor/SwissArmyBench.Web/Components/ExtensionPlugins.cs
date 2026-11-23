using SwissArmyBench.Web.Pages.PowerBi;

namespace SwissArmyBench.Web.Components;

/// <summary>The extensions' plug-ins this front end draws, by the classic page's own ids. The page actions
/// (pageActions.ts registerPageAction) go into the shared registry (PagePlugins) at start-up; the extensions' other
/// pieces are reached their own way: the Code App and Source Control pages by their addresses (lazyPages.ts
/// registerLazyLayer), the Excel canvas as a tab kind on the Notebooks page (workbenchPage.ts), and the Team box's
/// sign-in step (scmPage.ts teamSignIn) inside Settings' Join and Start a team.</summary>
public static class ExtensionPlugins
{
    /// <summary>Register every page action's plug-in in <paramref name="plugins"/>.</summary>
    public static PagePlugins RegisterIn(PagePlugins plugins)
    {
        // The ERD's Export to Power BI… (the Power BI extension's PAGE_ACTIONS), its context the ERD's tables.
        plugins.Register<PowerBiExportDialog>("powerbi_export");
        // The same dialog opened on Use an existing report's pages (the Power BI page's panel).
        plugins.Register<PowerBiReportPages>("powerbi_report_pages");
        return plugins;
    }
}
