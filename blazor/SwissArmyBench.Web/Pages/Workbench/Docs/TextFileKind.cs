namespace SwissArmyBench.Web.Pages.Workbench.Docs;

/// <summary>One kind of text document (domain/text_documents.py KINDS): its ending, its editor's language, the
/// preview its tab's toggle draws ("" none: markdown, html, svg, mermaid, vega), the view a tab opens in, its
/// tab's icon.</summary>
public sealed record TextFileKind(string Ending, string Language, string Preview, string First, string Icon)
{
    public bool HasPreview => Preview.Length > 0;
}
