using System.Text.RegularExpressions;

using SwissArmyBench.Web.Api.Connections;

namespace SwissArmyBench.Web.Pages.Connections;

/// <summary>The Connections page's words and small rules, as the classic connectionsWindow.ts says them.</summary>
public static partial class ConnectionWords
{
    /// <summary>The lake and SharePoint kinds: a group of their own on the page.</summary>
    public const string LakeGroup = "Lakes and SharePoint";

    private static readonly HashSet<string> _lakeKinds = ["onelake", "datalake", "delta", "sharepoint", "sharepoint_docs"];

    /// <summary>The groups the cards are drawn in, in the classic order.</summary>
    public static readonly IReadOnlyList<(string Title, Func<ConnectionCard, bool> Belongs)> CardGroups =
    [
        ("Databases", c => c.Connection == "database" && !IsLake(c.TablesKind)),
        (LakeGroup, c => IsLake(c.TablesKind)),
        ("Files", c => c.Connection == "file"),
        ("Your own code", c => c.Connection == "python"),
    ];

    public static bool IsLake(string? kind) => kind is not null && _lakeKinds.Contains(kind);

    /// <summary>Those whose own code reads their tables: sab.read, and Test shows a table's first rows.</summary>
    public static bool ReadsByCode(string? dialect) => dialect == "dataverse" || IsLake(dialect);

    /// <summary>A starter's label as a type's name: "A CSV file" as "CSV file".</summary>
    public static string Plain(string label)
    {
        var bare = LeadingArticle().Replace(label, string.Empty);
        return bare.Length == 0 ? bare : char.ToUpperInvariant(bare[0]) + bare[1..];
    }

    /// <summary>A setting's name in words: "tenant_id" as "Tenant id".</summary>
    public static string Words(string name)
    {
        var words = name.Replace('_', ' ');
        return words.Length == 0 ? words : char.ToUpperInvariant(words[0]) + words[1..];
    }

    /// <summary>A card's type in words: its type, else its kind's.</summary>
    public static string TypeOf(string type, string connection) => type.Length > 0 ? Plain(type) : connection switch
    {
        "database" => "Database",
        "file" => "File",
        "vault" => "Key vault",
        "python" => "Python",
        _ => connection,
    };

    /// <summary>A connection's type icon: its own by its starter's id, else its group's.</summary>
    public static string IconOf(string? template, string connection) =>
        template is { Length: > 0 } && Components.IconSet.Paths.ContainsKey(template) ? template : connection switch
        {
            "file" => "folder",
            "vault" => "key",
            "python" => "code",
            _ => "sql",
        };

    public static string PasswordSource(PasswordPlace password) => password.From switch
    {
        "keyring" => "the system keyring",
        "vault" => password.Secret is null ? password.Vault ?? string.Empty : $"{password.Vault} ({password.Secret})",
        "environment" => "an environment variable",
        _ => "nowhere yet",
    };

    /// <summary>How code names a connection: a Power BI workspace's DAX cells, your own Python's sab.read, a key
    /// vault's sab.blade, a database's sab.connection and SQL cell.</summary>
    public static string InCode(string name, string connection, string dialect)
    {
        var cell = name.Any(char.IsWhiteSpace) ? $"\"{name}\"" : name;
        if (dialect == "dax")
        {
            return $"sab.dax(\"{name}/<dataset>\", …)  ·  %%dax {name}/<dataset>";
        }
        if (connection == "vault")
        {
            return $"sab.blade(\"{name}\")";
        }
        if (connection == "python" || ReadsByCode(dialect))
        {
            var sql = dialect is not "sharepoint" and not "sharepoint_docs" && connection != "python" ? $"  ·  %%sql {cell}" : string.Empty;
            return $"sab.connection(\"{name}\")  ·  sab.read(\"{name}\", table){sql}";
        }
        return $"sab.connection(\"{name}\")  ·  %%sql {cell}";
    }

    /// <summary>What a Test answers: a vault reads its variables; a connection makes something (a file: is there).</summary>
    public static string Worked(TestAnswer answer) =>
        answer.Tables is { } tables ? $"{Count(tables, "table")}, {Count(answer.Columns ?? 0, "column")}"
        : answer.Variables is { } variables ? $"read {string.Join(", ", variables)}"
        : answer.Found ?? (answer.Type == "PowerBI" ? "signed in and reached the dataset" : $"made a {answer.Type}");

    /// <summary>A path's file or folder name without its kind: /data/orders.csv as orders.</summary>
    public static string Stem(string path)
    {
        var last = path.Split('/', '\\', StringSplitOptions.RemoveEmptyEntries).LastOrDefault() ?? string.Empty;
        var dot = last.LastIndexOf('.');
        return dot > 0 ? last[..dot] : last;
    }

    /// <summary>"3 relationships"; "1 relationship".</summary>
    public static string Count(int n, string word) => $"{n:N0} {word}{(n == 1 ? string.Empty : "s")}";

    /// <summary>A cell's value as the preview shows it (nothing for a null).</summary>
    public static string Cell(System.Text.Json.JsonElement value) => value.ValueKind switch
    {
        System.Text.Json.JsonValueKind.Null or System.Text.Json.JsonValueKind.Undefined => string.Empty,
        System.Text.Json.JsonValueKind.String => value.GetString() ?? string.Empty,
        _ => value.GetRawText(),
    };

    [GeneratedRegex("^(an?|the) ", RegexOptions.IgnoreCase)]
    private static partial Regex LeadingArticle();
}
