using SwissArmyBench.Web.Api.Catalog;

namespace SwissArmyBench.Web.Pages.Catalog;

/// <summary>One line of the Catalog's tree (the classic dataBrowse.ts Node): a connection, a database or schema, a
/// table, a column, a section or another item; its words, icon, note and status; its children (null: none; a
/// connection's table loads its columns when it first opens).</summary>
public sealed class TreeNode
{
    public required string Key { get; init; }

    public required string Label { get; init; }

    public required string Icon { get; init; }

    /// <summary>connection, group, table, column, section or item.</summary>
    public required string Kind { get; init; }

    public SearchResult? Result { get; init; }

    public BrowseConnection? Connection { get; init; }

    public BrowseGroup? Group { get; init; }

    public string? Type { get; init; }

    public string? Note { get; init; }

    public string? Status { get; init; }

    public List<TreeNode>? Children { get; set; }

    /// <summary>A connection's table: its columns are read when it first opens.</summary>
    public bool Lazy { get; set; }

    /// <summary>Open unless the user closed it.</summary>
    public bool OpenAtFirst { get; init; }

    /// <summary>Open now (the user's choice, else its first state).</summary>
    public bool IsOpen(IReadOnlySet<string> opened) =>
        Children is not null && (opened.Contains(Key) || (OpenAtFirst && !opened.Contains($"!{Key}")));
}
