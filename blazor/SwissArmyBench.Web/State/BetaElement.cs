namespace SwissArmyBench.Web.State;

/// <summary>The element a beta note is about (the classic betaNotes.ts ElementInfo): its tag, role, accessible name,
/// a button's own words (never a cell's or an editor's text), its CSS path and its box on the page.</summary>
public sealed record BetaElement(string Tag, string Role, string Name, string Text, string Path, BetaBox? Box = null)
{
    /// <summary>The place in a few words: "Button: Save", "Menu: Orders" (the classic shortName).</summary>
    public string Words
    {
        get
        {
            var what = Role.Length > 0 ? char.ToUpperInvariant(Role[0]) + Role[1..] : Tag;
            var words = Name.Length > 0 ? Name : Text;
            return words.Length > 0 ? $"{what}: {words}" : what;
        }
    }

    /// <summary>A place named in words only (the status bar's Beta mark, a menu with nothing right-clicked).</summary>
    public static BetaElement Named(string role, string name) => new("div", role, name, string.Empty, string.Empty);
}
