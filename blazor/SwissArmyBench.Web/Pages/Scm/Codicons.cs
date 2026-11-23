namespace SwissArmyBench.Web.Pages.Scm;

/// <summary>VS Code's codicons as the Source Control page draws them (Monaco's codicon font, loaded with the editor's
/// stylesheet): each name's code point.</summary>
public static class Codicons
{
    private static readonly IReadOnlyDictionary<string, int> _points = new Dictionary<string, int>
    {
        ["check"] = 0xeab2,
        ["refresh"] = 0xeb37,
        ["ellipsis"] = 0xea7c,
        ["list-tree"] = 0xeb86,
        ["list-flat"] = 0xeb84,
        ["go-to-file"] = 0xea94,
        ["discard"] = 0xeae2,
        ["add"] = 0xea60,
        ["remove"] = 0xeb3b,
        ["compare-changes"] = 0xeafd,
        ["diff-multiple"] = 0xec23,
        ["chevron-down"] = 0xeab4,
        ["chevron-right"] = 0xeab6,
        ["source-control"] = 0xea68,
        ["repo"] = 0xea62,
        ["repo-pull"] = 0xeb40,
        ["repo-push"] = 0xeb41,
        ["sync"] = 0xea77,
        ["git-commit"] = 0xeafc,
        ["git-branch"] = 0xea68,
        ["target"] = 0xebf8,
        ["cloud"] = 0xebaa,
        ["cloud-upload"] = 0xeac3,
        ["git-fetch"] = 0xecb2,
        ["arrow-up"] = 0xeaa1,
        ["arrow-down"] = 0xea9a,
        ["close"] = 0xea76,
        ["file"] = 0xea7b,
        ["warning"] = 0xea6c,
        ["whitespace"] = 0xeb7d,
        ["copy"] = 0xebcc,
        ["collapse-all"] = 0xeac5,
        ["github"] = 0xea84,
        ["folder"] = 0xea83,
        ["folder-opened"] = 0xeaf7,
        ["account"] = 0xeb99,
        ["sign-in"] = 0xea6f,
        ["sign-out"] = 0xea6e,
        ["link-external"] = 0xeb14,
        ["info"] = 0xea74,
        ["error"] = 0xea87,
        ["loading"] = 0xeb19,
        ["repo-clone"] = 0xeb3e,
        ["arrow-left"] = 0xea9b,
        ["arrow-right"] = 0xea9c,
    };

    /// <summary>A codicon's character (an unknown name: the file's).</summary>
    public static string Glyph(string name) => char.ConvertFromUtf32(_points.GetValueOrDefault(name, _points["file"]));
}
