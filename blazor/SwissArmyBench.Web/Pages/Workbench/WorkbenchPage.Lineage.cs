using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api.Workbench;

namespace SwissArmyBench.Web.Pages.Workbench;

// Lineage (the classic workbenchPage.ts showLineage and workbenchLineage.ts): a cell of the notebook or script in
// front traced back to the data with its values, in the overlay; a node's cell gone to (its file opened when it is
// another document of this page's kind).
public partial class WorkbenchPage
{
    private (OpenDocument Doc, int Cell)? _lineage;

    [Inject]
    private LineageClient LineageApi { get; set; } = default!;

    private Task ShowLineageAsync(OpenDocument doc, int cell)
    {
        _lineage = (doc, cell);
        return Task.CompletedTask;
    }

    /// <summary>The lineage request for a document's cell, with its cells or text as held now and its kernel.</summary>
    private Task<LineageGraph> TraceAsync(OpenDocument doc, int cell) => doc.NotebookView is { } nb
        ? LineageApi.TraceAsync(doc.Path ?? doc.Title, cell, nb.ToSave().Cells, null, Session.Kernel)
        : LineageApi.TraceAsync(doc.Path ?? doc.Title, cell, null, doc.ScriptText, Session.Kernel);

    private async Task GoToNodeAsync(LineageNode node)
    {
        _lineage = null;
        if (node.Cell is not { } number)
        {
            return;
        }
        var doc = node.Document is { } path
            ? _documents.FirstOrDefault(d => string.Equals(d.Path, path, StringComparison.OrdinalIgnoreCase) || d.Title == path)
            : Front;
        if (doc is null && node.Document is { } file)
        {
            await OpenPathAsync(file);
            doc = _documents.FirstOrDefault(d => string.Equals(d.Path, file, StringComparison.OrdinalIgnoreCase));
        }
        if (doc is null)
        {
            return;
        }
        _layout.Show(doc.Key);
        if (doc.NotebookView is { } notebook)
        {
            await notebook.GoToCellNumberAsync(number);
        }
        else
        {
            await (doc.ScriptView?.RevealCellAsync(number) ?? Task.CompletedTask);
        }
    }

    /// <summary>The palette's cell.lineage: the selected cell (a notebook) or the cell at the cursor (a script).</summary>
    private async Task LineageOfFrontAsync()
    {
        if (Front is { NotebookView.Selected: { } cell } doc)
        {
            await ShowLineageAsync(doc, cell.Number);
        }
        else if (Front is { ScriptView: { } script } scriptDoc && ScriptCells.CellAt(scriptDoc.ScriptText, await script.CursorLineAsync()) is { } number)
        {
            await ShowLineageAsync(scriptDoc, number);
        }
    }
}
